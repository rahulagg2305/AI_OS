"""RetrievalService against real Postgres+pgvector (ADR-0015 — no
mocking the database or either real searcher). Proves one real
``search()`` call genuinely drives the real
``SqlKeywordSearcher``/``SqlVectorSearcher`` and hands their real
results to the real ``fuse_rankings`` — not a hand-built fusion, and
not a passthrough of only one strategy.

Three real chunks are seeded so the fused result can only be correct
if both real searches genuinely ran:
- ``kw_chunk``: strong keyword match ("wombat" x4), far vector (rank
  last by distance) -- keyword-only signal would rank it #1; vector-
  only would rank it last.
- ``vec_chunk``: no keyword match at all ("giraffe habitat", so
  genuinely absent from the real keyword result set), nearest vector
  (rank #1 by distance) -- keyword-only signal would drop it entirely.
- ``both_chunk``: one weak keyword mention, mid-distance vector.

A service that only ran keyword search would never see ``vec_chunk``
at all; a service that only ran vector search would rank ``kw_chunk``
last. The real fused order below is only reachable by genuinely
running, and genuinely combining, both.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Generator
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from ai_os_kernel.llm_gateway.models import EmbeddingResponse, UsageRecord
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.knowledge_keyword_search import SqlKeywordSearcher
from ai_os_kernel.persistence.knowledge_writer import ChunkInput, SqlKnowledgeWriter
from ai_os_kernel.retrieval.embedding_writer import SqlEmbeddingWriter
from ai_os_kernel.retrieval.retrieval_service import RetrievalRequest, RetrievalService
from ai_os_kernel.retrieval.vector_search import SqlVectorSearcher
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"


@pytest.fixture(scope="module")
def database_url() -> Generator[str, None, None]:
    with postgres_container() as postgres:
        url = postgres.get_connection_url()
        previous = os.environ.get("AIOS_DATABASE_URL")
        os.environ["AIOS_DATABASE_URL"] = url
        try:
            command.upgrade(Config(str(ALEMBIC_INI)), "head")
            yield url
        finally:
            if previous is None:
                os.environ.pop("AIOS_DATABASE_URL", None)
            else:
                os.environ["AIOS_DATABASE_URL"] = previous


def _embedding_response(vector: list[float], *, model_id: str) -> EmbeddingResponse:
    return EmbeddingResponse(
        vectors=[vector],
        model_id=model_id,
        model_version="v1",
        dimensions=len(vector),
        usage=UsageRecord(
            input_tokens=1,
            output_tokens=0,
            cache_read_tokens=0,
            cache_write_tokens=0,
            cost_usd=Decimal("0"),
            latency_ms=1,
            provider="local",
            model_id=model_id,
            retries=0,
            fallback_used=False,
        ),
    )


async def _create_real_chunk(database_url: str, *, content: str) -> str:
    engine = build_engine(database_url)
    try:
        writer = SqlKnowledgeWriter(engine)
        record = await writer.write_document(
            source_uri=f"https://example.com/{content[:20].replace(' ', '-')}.md",
            content_hash="sha256:" + "b" * 64,
            media_type="text/markdown",
            trust="trusted",
            chunks=[
                ChunkInput(content=content, token_count=4, chunk_strategy_version="fixed-size-v1")
            ],
        )
        return record.chunks[0].chunk_id
    finally:
        await engine.dispose()


def test_search_returns_a_genuinely_fused_result_from_real_underlying_searches(
    database_url: str,
) -> None:
    model_id = "retrieval-service-test-model"

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            embedding_writer = SqlEmbeddingWriter(engine)

            kw_chunk = await _create_real_chunk(
                database_url, content="wombat wombat wombat wombat habitat notes"
            )
            vec_chunk = await _create_real_chunk(
                database_url, content="giraffe habitat notes with no matching term"
            )
            both_chunk = await _create_real_chunk(
                database_url, content="wombat sighting near the giraffe enclosure"
            )

            # Query = [1, 0, 0, 0]. Hand-computed real cosine distances:
            # kw_chunk   = [0, 0, 0, 1]      -> distance == 1.0    (farthest)
            # both_chunk = [0.5, 0.5, 0, 0]  -> distance ~= 0.2929 (mid)
            # vec_chunk  = [0.9, 0.1, 0, 0]  -> distance ~= 0.0061 (nearest)
            await embedding_writer.write_embedding(
                chunk_id=kw_chunk,
                response=_embedding_response([0.0, 0.0, 0.0, 1.0], model_id=model_id),
            )
            await embedding_writer.write_embedding(
                chunk_id=both_chunk,
                response=_embedding_response([0.5, 0.5, 0.0, 0.0], model_id=model_id),
            )
            await embedding_writer.write_embedding(
                chunk_id=vec_chunk,
                response=_embedding_response([0.9, 0.1, 0.0, 0.0], model_id=model_id),
            )

            service = RetrievalService(
                keyword_searcher=SqlKeywordSearcher(engine),
                vector_searcher=SqlVectorSearcher(engine),
            )

            request = RetrievalRequest(
                query_text="wombat",
                query_vector=[1.0, 0.0, 0.0, 0.0],
                embedding_model_id=model_id,
                embedding_model_version="v1",
                limit=10,
            )
            fused = await service.search(request)
            fused_by_id = {result.chunk_id: result for result in fused}

            # Real keyword search genuinely ran: vec_chunk has no "wombat"
            # at all, so it is genuinely absent from the real keyword
            # result set -- a keyword-only service could never surface it.
            assert fused_by_id[vec_chunk].keyword_rank is None
            assert fused_by_id[vec_chunk].vector_rank == 1

            # Real vector search genuinely ran: kw_chunk is farthest by
            # real cosine distance -- a vector-only service would rank
            # it last, not first.
            assert fused_by_id[kw_chunk].vector_rank == 3
            assert fused_by_id[kw_chunk].keyword_rank == 1

            assert fused_by_id[both_chunk].keyword_rank == 2
            assert fused_by_id[both_chunk].vector_rank == 2

            # Real fused order, hand-computed with RRF_K=60:
            # kw_chunk:   1/61 + 1/63 = 0.032266...
            # both_chunk: 1/62 + 1/62 = 0.032258...
            # vec_chunk:  0    + 1/61 = 0.016393...
            assert [result.chunk_id for result in fused] == [kw_chunk, both_chunk, vec_chunk]
            assert fused_by_id[kw_chunk].fused_score == pytest.approx(1 / 61 + 1 / 63)
            assert fused_by_id[both_chunk].fused_score == pytest.approx(1 / 62 + 1 / 62)
            assert fused_by_id[vec_chunk].fused_score == pytest.approx(1 / 61)
            assert fused_by_id[kw_chunk].fused_score > fused_by_id[both_chunk].fused_score
            assert fused_by_id[both_chunk].fused_score > fused_by_id[vec_chunk].fused_score

            # Genuinely differs from either individual real strategy alone.
            keyword_only = await SqlKeywordSearcher(engine).search(query="wombat", limit=10)
            vector_only = await SqlVectorSearcher(engine).search(
                query_vector=[1.0, 0.0, 0.0, 0.0],
                embedding_model_id=model_id,
                embedding_model_version="v1",
                limit=10,
            )
            keyword_only_order = [result.chunk_id for result in keyword_only]
            vector_only_order = [neighbor.chunk_id for neighbor in vector_only]
            fused_order = [result.chunk_id for result in fused]
            assert fused_order != keyword_only_order
            assert fused_order != vector_only_order
        finally:
            await engine.dispose()

    asyncio.run(_run())
