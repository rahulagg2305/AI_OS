"""IndexingService against real Postgres (ADR-0015 — no mocking the
database or the real writer/searchers it composes). Proves real,
multi-chunk output from real content, a real archive-and-replace
change policy, and that a real chunk this component just wrote is
genuinely retrievable through the real
:class:`~ai_os_kernel.retrieval.retrieval_service.RetrievalService`
built at ``P02-S04-M11-T06`` — not a hand-built fixture standing in for
either.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Generator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from ai_os_kernel.knowledge_manager.indexing import IndexingError, IndexingService, chunk_content
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.knowledge_keyword_search import SqlKeywordSearcher
from ai_os_kernel.persistence.knowledge_schema import documents as documents_table
from ai_os_kernel.persistence.knowledge_writer import SqlKnowledgeWriter
from ai_os_kernel.retrieval.retrieval_service import RetrievalRequest, RetrievalService
from ai_os_kernel.retrieval.vector_search import SqlVectorSearcher
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

# Two distinctive terms separated by enough filler that, at
# chunk_size=50/overlap=10, they land in different, non-overlapping
# real chunks -- hand-verified below, not assumed.
_CONTENT_V1 = "aardvark " + ("x" * 200) + " quokka"


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


def test_chunk_content_splits_deterministically_with_overlap() -> None:
    windows = chunk_content(_CONTENT_V1, chunk_size=50, overlap=10)

    assert len(windows) == 6
    assert windows[0].content.startswith("aardvark")
    assert windows[-1].content.endswith("quokka")
    # Every window is a real, contiguous slice of the real content --
    # the aardvark chunk and the quokka chunk are genuinely disjoint.
    assert "quokka" not in windows[0].content
    assert "aardvark" not in windows[-1].content


def test_chunk_content_rejects_invalid_input() -> None:
    with pytest.raises(IndexingError, match="must not be blank"):
        chunk_content("   ")
    with pytest.raises(IndexingError, match="overlap must be in"):
        chunk_content("real content", chunk_size=10, overlap=10)


def test_indexed_chunk_is_genuinely_retrievable_through_retrieval_service(
    database_url: str,
) -> None:
    source_uri = "https://example.com/indexing-service-test.md"

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            service = IndexingService(
                engine=engine,
                writer=SqlKnowledgeWriter(engine),
                chunk_size=50,
                chunk_overlap=10,
            )

            result = await service.index_document(
                source_uri=source_uri,
                content=_CONTENT_V1,
                media_type="text/markdown",
                trust="trusted",
            )

            assert result.skipped is False
            assert result.superseded_document_id is None
            document = result.document
            assert document is not None
            assert len(document.chunks) == 6

            aardvark_chunk = next(c for c in document.chunks if "aardvark" in c.content)
            quokka_chunk = next(c for c in document.chunks if "quokka" in c.content)
            assert aardvark_chunk.chunk_id != quokka_chunk.chunk_id

            retrieval = RetrievalService(
                keyword_searcher=SqlKeywordSearcher(engine),
                vector_searcher=SqlVectorSearcher(engine),
            )
            # No embeddings exist for this made-up model -- vector search
            # genuinely returns nothing, and RetrievalService still
            # returns the real, genuinely-indexed keyword hit unchanged
            # (RRF's own "absence from one list is zero contribution").
            aardvark_hits = await retrieval.search(
                RetrievalRequest(
                    query_text="aardvark",
                    query_vector=[0.0, 0.0],
                    embedding_model_id="no-embeddings-indexed-for-this-model",
                    embedding_model_version="v1",
                    limit=10,
                )
            )
            aardvark_hit_ids = [hit.chunk_id for hit in aardvark_hits]
            assert aardvark_chunk.chunk_id in aardvark_hit_ids
            assert quokka_chunk.chunk_id not in aardvark_hit_ids

            quokka_hits = await retrieval.search(
                RetrievalRequest(
                    query_text="quokka",
                    query_vector=[0.0, 0.0],
                    embedding_model_id="no-embeddings-indexed-for-this-model",
                    embedding_model_version="v1",
                    limit=10,
                )
            )
            quokka_hit_ids = [hit.chunk_id for hit in quokka_hits]
            assert quokka_chunk.chunk_id in quokka_hit_ids
            assert aardvark_chunk.chunk_id not in quokka_hit_ids

            # Re-indexing byte-identical content is a genuine no-op.
            unchanged = await service.index_document(
                source_uri=source_uri,
                content=_CONTENT_V1,
                media_type="text/markdown",
                trust="trusted",
            )
            assert unchanged.skipped is True
            assert unchanged.document is None

            # Real change: archive-and-replace.
            changed = await service.index_document(
                source_uri=source_uri,
                content=_CONTENT_V1 + " updated",
                media_type="text/markdown",
                trust="trusted",
            )
            assert changed.skipped is False
            assert changed.superseded_document_id == document.document_id
            assert changed.document is not None
            assert changed.document.document_id != document.document_id

            async with engine.connect() as connection:
                archived_at = (
                    await connection.execute(
                        sa.select(documents_table.c.archived_at).where(
                            documents_table.c.document_id == document.document_id
                        )
                    )
                ).scalar_one()
            assert archived_at is not None

            # Disclosed, tested limitation: the real keyword searcher
            # does not filter archived_at yet, so the superseded
            # aardvark chunk genuinely still surfaces.
            still_surfaces = await SqlKeywordSearcher(engine).search(query="aardvark", limit=10)
            assert aardvark_chunk.chunk_id in [r.chunk_id for r in still_surfaces]
        finally:
            await engine.dispose()

    asyncio.run(_run())
