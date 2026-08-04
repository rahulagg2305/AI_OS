"""QueryEngine against real Postgres (ADR-0015 — no mocking the
database or the real IndexingService/RetrievalService it composes).
Proves real, provenance-enriched results for a fresh document, and
proves the real, partial archived_at-filtering improvement this step
adds: a chunk superseded by a real re-index is genuinely excluded from
QueryEngine's own output while still surfacing through the real
SqlKeywordSearcher directly — the disclosed, narrower scope this
module's own docstring states, not just claimed.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from ai_os_kernel.knowledge_manager.indexing import IndexingService
from ai_os_kernel.knowledge_manager.query_engine import QueryEngine
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.knowledge_keyword_search import SqlKeywordSearcher
from ai_os_kernel.persistence.knowledge_writer import SqlKnowledgeWriter
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


def _query(text: str) -> RetrievalRequest:
    return RetrievalRequest(
        query_text=text,
        query_vector=[0.0, 0.0],
        embedding_model_id="no-embeddings-indexed-for-this-model",
        embedding_model_version="v1",
        limit=10,
    )


def test_query_returns_real_provenance_for_a_fresh_document(database_url: str) -> None:
    source_uri = "https://example.com/query-engine-fresh.md"

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            indexing = IndexingService(engine=engine, writer=SqlKnowledgeWriter(engine))
            index_result = await indexing.index_document(
                source_uri=source_uri,
                content="the wallaby grazed quietly at dusk",
                media_type="text/markdown",
                trust="trusted",
            )
            assert index_result.document is not None
            wallaby_chunk = index_result.document.chunks[0]

            query_engine = QueryEngine(
                engine=engine,
                retrieval_service=RetrievalService(
                    keyword_searcher=SqlKeywordSearcher(engine),
                    vector_searcher=SqlVectorSearcher(engine),
                ),
            )
            results = await query_engine.query(_query("wallaby"))

            assert len(results) == 1
            result = results[0]
            assert result.chunk_id == wallaby_chunk.chunk_id
            assert result.document_id == index_result.document.document_id
            assert result.source_uri == source_uri
            assert result.trust == "trusted"
            assert result.content == wallaby_chunk.content
            assert result.keyword_rank == 1
            assert result.vector_rank is None
            assert result.fused_score > 0
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_query_excludes_a_superseded_chunk_that_the_raw_searcher_still_returns(
    database_url: str,
) -> None:
    source_uri = "https://example.com/query-engine-superseded.md"

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            indexing = IndexingService(engine=engine, writer=SqlKnowledgeWriter(engine))
            original = await indexing.index_document(
                source_uri=source_uri,
                content="a rare pangolin sighting was logged here",
                media_type="text/markdown",
                trust="trusted",
            )
            assert original.document is not None
            pangolin_chunk = original.document.chunks[0]

            replaced = await indexing.index_document(
                source_uri=source_uri,
                content="an entirely unrelated replacement paragraph",
                media_type="text/markdown",
                trust="trusted",
            )
            assert replaced.skipped is False
            assert replaced.superseded_document_id == original.document.document_id

            query_engine = QueryEngine(
                engine=engine,
                retrieval_service=RetrievalService(
                    keyword_searcher=SqlKeywordSearcher(engine),
                    vector_searcher=SqlVectorSearcher(engine),
                ),
            )
            enriched_results = await query_engine.query(_query("pangolin"))
            assert enriched_results == []

            # The disclosed, narrower scope: bypassing QueryEngine, the
            # real searcher still returns the superseded chunk unfiltered.
            raw_results = await SqlKeywordSearcher(engine).search(query="pangolin", limit=10)
            assert pangolin_chunk.chunk_id in [r.chunk_id for r in raw_results]
        finally:
            await engine.dispose()

    asyncio.run(_run())
