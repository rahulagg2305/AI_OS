"""SqlVectorSearcher against a real Postgres+pgvector container
(ADR-0015 — no mocking the database). Proves a genuine nearest-
neighbour ranking, not just "a query ran without error": real, hand-
chosen vectors with known, hand-computed cosine distances come back in
the mathematically correct order; a vector from a different embedding
model that would otherwise rank closest is genuinely excluded (search_
vector_search.md §4's "queries compare only vectors from the same
model and version"); and a real ``index_generation`` pin genuinely
narrows the result set.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Generator
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from ai_os_kernel.llm_gateway.models import EmbeddingResponse, UsageRecord
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.knowledge_schema import embeddings as embeddings_table
from ai_os_kernel.persistence.knowledge_writer import ChunkInput, SqlKnowledgeWriter
from ai_os_kernel.retrieval.embedding_writer import SqlEmbeddingWriter
from ai_os_kernel.retrieval.vector_search import SqlVectorSearcher, VectorSearchError
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
_MODEL_ID = "nomic-embed-text"
_MODEL_VERSION = "nomic-embed-text"


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


def _response(
    vector: list[float], *, model_id: str = _MODEL_ID, model_version: str = _MODEL_VERSION
) -> EmbeddingResponse:
    return EmbeddingResponse(
        vectors=[vector],
        model_id=model_id,
        model_version=model_version,
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
            source_uri=f"https://example.com/{content.replace(' ', '-')}.md",
            content_hash="sha256:" + "a" * 64,
            media_type="text/markdown",
            trust="trusted",
            chunks=[
                ChunkInput(content=content, token_count=4, chunk_strategy_version="fixed-size-v1")
            ],
        )
        return record.chunks[0].chunk_id
    finally:
        await engine.dispose()


def test_search_returns_real_neighbours_in_mathematically_correct_order(
    database_url: str,
) -> None:
    # A model id unique to this test -- the real Postgres container is
    # shared (module-scoped) across every test in this file, so
    # filtering by a model id no other test ever writes under is what
    # keeps each test's own rows genuinely isolated, the same "unique
    # identifier per test, not a flush between tests" fix already
    # established for the rate limiter's own real-Redis tests.
    model_id = "order-test-model"

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            writer = SqlEmbeddingWriter(engine)
            searcher = SqlVectorSearcher(engine)

            # Hand-computed real cosine distances from [1, 0, 0, 0]:
            # near  = [0.9, 0.1, 0, 0]  -> distance ~= 0.0061
            # mid   = [0.5, 0.5, 0, 0]  -> distance ~= 0.2929
            # far   = [0.0, 0.0, 0, 1]  -> distance == 1.0
            near_chunk = await _create_real_chunk(database_url, content="near neighbour chunk")
            mid_chunk = await _create_real_chunk(database_url, content="mid neighbour chunk")
            far_chunk = await _create_real_chunk(database_url, content="far neighbour chunk")

            await writer.write_embedding(
                chunk_id=far_chunk,
                response=_response([0.0, 0.0, 0.0, 1.0], model_id=model_id, model_version="v1"),
            )
            await writer.write_embedding(
                chunk_id=near_chunk,
                response=_response([0.9, 0.1, 0.0, 0.0], model_id=model_id, model_version="v1"),
            )
            await writer.write_embedding(
                chunk_id=mid_chunk,
                response=_response([0.5, 0.5, 0.0, 0.0], model_id=model_id, model_version="v1"),
            )

            results = await searcher.search(
                query_vector=[1.0, 0.0, 0.0, 0.0],
                embedding_model_id=model_id,
                embedding_model_version="v1",
                limit=10,
            )

            ranked_chunk_ids = [neighbor.chunk_id for neighbor in results]
            assert ranked_chunk_ids == [near_chunk, mid_chunk, far_chunk]
            assert results[0].distance < results[1].distance < results[2].distance
            assert results[0].distance == pytest.approx(0.0061, abs=1e-3)
            assert results[1].distance == pytest.approx(0.2929, abs=1e-3)
            assert results[2].distance == pytest.approx(1.0, abs=1e-6)
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_search_excludes_a_closer_vector_from_a_different_embedding_model(
    database_url: str,
) -> None:
    model_id = "filter-test-model"

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            writer = SqlEmbeddingWriter(engine)
            searcher = SqlVectorSearcher(engine)

            real_chunk = await _create_real_chunk(database_url, content="real model chunk")
            wrong_model_chunk = await _create_real_chunk(database_url, content="wrong model chunk")

            # The wrong-model vector is nearly identical to the query --
            # it would rank first by raw distance alone. A genuine
            # "same model and version only" filter must still exclude
            # it entirely.
            await writer.write_embedding(
                chunk_id=wrong_model_chunk,
                response=_response(
                    [0.999, 0.001, 0.0, 0.0], model_id="a-different-model", model_version="v1"
                ),
            )
            await writer.write_embedding(
                chunk_id=real_chunk,
                response=_response([0.5, 0.5, 0.0, 0.0], model_id=model_id, model_version="v1"),
            )

            results = await searcher.search(
                query_vector=[1.0, 0.0, 0.0, 0.0],
                embedding_model_id=model_id,
                embedding_model_version="v1",
                limit=10,
            )

            ranked_chunk_ids = [neighbor.chunk_id for neighbor in results]
            assert ranked_chunk_ids == [real_chunk]
            assert wrong_model_chunk not in ranked_chunk_ids
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_search_respects_a_real_index_generation_pin(database_url: str) -> None:
    model_id = "generation-test-model"

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            writer = SqlEmbeddingWriter(engine)
            searcher = SqlVectorSearcher(engine)

            generation_one_chunk = await _create_real_chunk(
                database_url, content="generation one chunk"
            )
            generation_two_chunk = await _create_real_chunk(
                database_url, content="generation two chunk"
            )

            gen_one_record = await writer.write_embedding(
                chunk_id=generation_one_chunk,
                response=_response([0.9, 0.1, 0.0, 0.0], model_id=model_id, model_version="v1"),
            )
            assert gen_one_record.index_generation == 1

            # No real re-index mechanism exists yet to produce a
            # second real generation (see embedding_writer.py's own
            # docstring) -- inserted directly here to prove the real
            # pin/filter behavior itself, not to claim a second
            # generation is otherwise reachable today.
            async with engine.begin() as connection:
                await connection.execute(
                    sa.insert(embeddings_table).values(
                        embedding_id="emb_test_generation_two",
                        chunk_id=generation_two_chunk,
                        embedding=[0.95, 0.05, 0.0, 0.0],
                        embedding_model_id=model_id,
                        embedding_model_version="v1",
                        dimensions=4,
                        index_generation=2,
                    )
                )

            pinned_to_one = await searcher.search(
                query_vector=[1.0, 0.0, 0.0, 0.0],
                embedding_model_id=model_id,
                embedding_model_version="v1",
                limit=10,
                index_generation=1,
            )
            unpinned = await searcher.search(
                query_vector=[1.0, 0.0, 0.0, 0.0],
                embedding_model_id=model_id,
                embedding_model_version="v1",
                limit=10,
            )

            assert [n.chunk_id for n in pinned_to_one] == [generation_one_chunk]
            assert generation_two_chunk not in [n.chunk_id for n in pinned_to_one]
            assert generation_two_chunk in [n.chunk_id for n in unpinned]
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_search_rejects_a_non_positive_limit(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            searcher = SqlVectorSearcher(engine)

            with pytest.raises(VectorSearchError, match="limit must be positive"):
                await searcher.search(
                    query_vector=[1.0, 0.0],
                    embedding_model_id=_MODEL_ID,
                    embedding_model_version=_MODEL_VERSION,
                    limit=0,
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())
