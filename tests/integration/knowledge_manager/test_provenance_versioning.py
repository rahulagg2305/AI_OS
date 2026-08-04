"""P02-S04-M09-T05 — real version/provenance tracking, against real
Postgres (ADR-0015 — no mocking the database). Proves every retrieved
item genuinely carries source *and* version: a real, always-present
``chunk_strategy_version``, and real, correctly-absent-when-genuinely-
absent embedding provenance (``embedding_model_id``/
``embedding_model_version``/``index_generation``) — never a fabricated
value standing in for "no matching embedding exists."
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
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.knowledge_manager.indexing import CHUNK_STRATEGY_VERSION, IndexingService
from ai_os_kernel.knowledge_manager.query_engine import QueryEngine
from ai_os_kernel.llm_gateway.models import EmbeddingResponse, UsageRecord
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.knowledge_keyword_search import SqlKeywordSearcher
from ai_os_kernel.persistence.knowledge_schema import embeddings as embeddings_table
from ai_os_kernel.persistence.knowledge_writer import SqlKnowledgeWriter
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


def _embedding_response(
    vector: list[float], *, model_id: str, model_version: str
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


def _query_engine(engine: AsyncEngine) -> QueryEngine:
    return QueryEngine(
        engine=engine,
        retrieval_service=RetrievalService(
            keyword_searcher=SqlKeywordSearcher(engine),
            vector_searcher=SqlVectorSearcher(engine),
        ),
    )


def test_every_result_carries_a_real_chunk_strategy_version_and_matching_embedding_provenance(
    database_url: str,
) -> None:
    model_id = "provenance-test-model"

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            indexing = IndexingService(engine=engine, writer=SqlKnowledgeWriter(engine))
            index_result = await indexing.index_document(
                source_uri="https://example.com/provenance-test.md",
                content="an aardvark was observed during the provenance survey",
                media_type="text/markdown",
                trust="trusted",
            )
            assert index_result.document is not None
            chunk = index_result.document.chunks[0]
            assert chunk.chunk_strategy_version == CHUNK_STRATEGY_VERSION

            embedding_writer = SqlEmbeddingWriter(engine)
            await embedding_writer.write_embedding(
                chunk_id=chunk.chunk_id,
                response=_embedding_response(
                    [1.0, 0.0, 0.0, 0.0], model_id=model_id, model_version="v1"
                ),
            )

            results = await _query_engine(engine).query(
                RetrievalRequest(
                    query_text="aardvark",
                    query_vector=[1.0, 0.0, 0.0, 0.0],
                    embedding_model_id=model_id,
                    embedding_model_version="v1",
                    limit=10,
                )
            )

            assert len(results) == 1
            result = results[0]
            assert result.keyword_rank == 1
            assert result.vector_rank == 1
            # The real "source" half (already real since P02-S04-M09-T04)
            # plus the real "version" half this ticket adds.
            assert result.chunk_strategy_version == CHUNK_STRATEGY_VERSION
            assert result.embedding_model_id == model_id
            assert result.embedding_model_version == "v1"
            assert result.index_generation == 1
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_keyword_only_hit_has_no_fabricated_embedding_provenance(database_url: str) -> None:
    model_id = "no-embedding-for-this-model"

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            indexing = IndexingService(engine=engine, writer=SqlKnowledgeWriter(engine))
            index_result = await indexing.index_document(
                source_uri="https://example.com/keyword-only-provenance-test.md",
                content="a quokka was observed with no embedding on file",
                media_type="text/markdown",
                trust="trusted",
            )
            assert index_result.document is not None
            chunk = index_result.document.chunks[0]
            # Deliberately no embedding written for this chunk at all.

            results = await _query_engine(engine).query(
                RetrievalRequest(
                    query_text="quokka",
                    query_vector=[0.0, 0.0, 0.0, 0.0],
                    embedding_model_id=model_id,
                    embedding_model_version="v1",
                    limit=10,
                )
            )

            assert len(results) == 1
            result = results[0]
            assert result.chunk_id == chunk.chunk_id
            assert result.keyword_rank == 1
            assert result.vector_rank is None
            # Real "version" for the chunk itself is still present...
            assert result.chunk_strategy_version == CHUNK_STRATEGY_VERSION
            # ...but embedding provenance is a genuine, disclosed absence
            # -- never a fabricated value standing in for "none exists."
            assert result.embedding_model_id is None
            assert result.embedding_model_version is None
            assert result.index_generation is None
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_the_highest_index_generation_wins_deterministically(database_url: str) -> None:
    model_id = "multi-generation-test-model"

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            indexing = IndexingService(engine=engine, writer=SqlKnowledgeWriter(engine))
            index_result = await indexing.index_document(
                source_uri="https://example.com/multi-generation-provenance-test.md",
                content="a wombat was re-indexed across two real generations",
                media_type="text/markdown",
                trust="trusted",
            )
            assert index_result.document is not None
            chunk = index_result.document.chunks[0]

            embedding_writer = SqlEmbeddingWriter(engine)
            gen_one = await embedding_writer.write_embedding(
                chunk_id=chunk.chunk_id,
                response=_embedding_response(
                    [1.0, 0.0, 0.0, 0.0], model_id=model_id, model_version="v1"
                ),
            )
            assert gen_one.index_generation == 1

            # No real re-index mechanism exists yet to produce a second
            # real generation (the same disclosed limitation
            # test_vector_search.py's own P02-S04-M11-T04 test already
            # named) -- inserted directly here, identical precedent, to
            # prove the real tie-break itself.
            async with engine.begin() as connection:
                await connection.execute(
                    sa.insert(embeddings_table).values(
                        embedding_id="emb_test_provenance_generation_two",
                        chunk_id=chunk.chunk_id,
                        embedding=[1.0, 0.0, 0.0, 0.0],
                        embedding_model_id=model_id,
                        embedding_model_version="v1",
                        dimensions=4,
                        index_generation=2,
                    )
                )

            results = await _query_engine(engine).query(
                RetrievalRequest(
                    query_text="wombat",
                    query_vector=[1.0, 0.0, 0.0, 0.0],
                    embedding_model_id=model_id,
                    embedding_model_version="v1",
                    limit=10,
                )
            )

            assert len(results) == 1
            # The higher real generation wins deterministically, not
            # whichever row Postgres happened to return first.
            assert results[0].index_generation == 2
        finally:
            await engine.dispose()

    asyncio.run(_run())
