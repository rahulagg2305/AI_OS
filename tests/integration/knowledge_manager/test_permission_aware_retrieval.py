"""§5's Access / Filter Layer against real Postgres (`P02-S04-M09-T08`).

Every test drives the real `IndexingService` → real `RetrievalService` →
real `QueryEngine.query` path, and the permission-denied cases assert
against what Postgres genuinely returned — not a Python-side filter
standing in for the control.

The load-bearing test is
`test_a_denied_principal_is_trimmed_in_sql_not_after_ranking`: it proves
the retrieval service genuinely *found* the chunk while the query still
returned nothing, which is the difference between the SQL predicate
search_vector_search.md §4 requires and the post-filtering it rules out.
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
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.context_manager.models import ContextRequest
from ai_os_kernel.context_manager.resolvers import KnowledgeResolver
from ai_os_kernel.knowledge_manager.indexing import IndexingService
from ai_os_kernel.knowledge_manager.query_engine import QueryEngine
from ai_os_kernel.llm_gateway.models import EmbeddingRequest, EmbeddingResponse, UsageRecord
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.knowledge_keyword_search import SqlKeywordSearcher
from ai_os_kernel.persistence.knowledge_writer import SqlKnowledgeWriter
from ai_os_kernel.retrieval.retrieval_service import RetrievalRequest, RetrievalService
from ai_os_kernel.retrieval.vector_search import SqlVectorSearcher
from ai_os_kernel.security_manager.permissions import (
    KNOWLEDGE_READ,
    WORKFLOW_READ,
    permissions_for_roles,
)
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

_PERMITTED = frozenset({KNOWLEDGE_READ})
# A real, non-empty permission set that genuinely lacks knowledge:read —
# a principal who can read workflows but was never granted knowledge.
_DENIED = frozenset({WORKFLOW_READ})


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


def _query_engine(engine: AsyncEngine) -> QueryEngine:
    return QueryEngine(
        engine=engine,
        retrieval_service=RetrievalService(
            keyword_searcher=SqlKeywordSearcher(engine),
            vector_searcher=SqlVectorSearcher(engine),
        ),
    )


async def _index(engine: AsyncEngine, *, source_uri: str, content: str) -> None:
    indexing = IndexingService(engine=engine, writer=SqlKnowledgeWriter(engine))
    result = await indexing.index_document(
        source_uri=source_uri, content=content, media_type="text/markdown", trust="trusted"
    )
    assert result.document is not None


def test_a_permitted_principal_genuinely_retrieves(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            await _index(
                engine,
                source_uri="https://example.com/perm-allowed.md",
                content="the platypus reviewed the architecture",
            )
            results = await _query_engine(engine).query(
                _query("platypus"), principal_permissions=_PERMITTED
            )
            assert len(results) == 1
            assert "platypus" in results[0].content
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_denied_principal_is_trimmed_in_sql_not_after_ranking(database_url: str) -> None:
    """The real proof this layer exists for.

    The retrieval service is asked the identical question directly and
    genuinely *finds* the chunk — so the emptiness of the permitted-less
    query is the database's own doing, applied in the same statement
    that resolves ranking and provenance, exactly as
    search_vector_search.md §4 requires ("applied AS SQL PREDICATES, not
    post-filtering") and ADR-0013 demands ("permission trimming that
    cannot leak through ranking").
    """

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            await _index(
                engine,
                source_uri="https://example.com/perm-denied.md",
                content="the echidna documented the retry policy",
            )
            retrieval = RetrievalService(
                keyword_searcher=SqlKeywordSearcher(engine),
                vector_searcher=SqlVectorSearcher(engine),
            )

            # The content is genuinely findable — this is not an empty
            # index masquerading as a working permission check.
            fused = await retrieval.search(_query("echidna"))
            assert fused, "precondition failed: the chunk is not retrievable at all"

            denied = await _query_engine(engine).query(
                _query("echidna"), principal_permissions=_DENIED
            )
            assert denied == []
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_no_principal_is_denied_because_the_gate_fails_closed(database_url: str) -> None:
    """R-021, 2026-08-14: this gate fails closed.

    It first treated `None` as "unenforced", on the reasoning that no
    principal reached most retrieval paths. The R-021 investigation
    disproved that premise by finding a real, authenticated bypass
    (`ExperimentRunOrchestrator` took the principal's id but not their
    permissions), so a forgotten argument silently disabled a security
    control. Failing closed makes the same mistake produce a thinner
    context instead — visible and safe rather than invisible and
    permissive.
    """

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            await _index(
                engine,
                source_uri="https://example.com/perm-unenforced.md",
                content="the numbat inspected the lease reaper",
            )
            # The content is genuinely retrievable with a real principal…
            permitted = await _query_engine(engine).query(
                _query("numbat"), principal_permissions=_PERMITTED
            )
            assert len(permitted) == 1

            # …and genuinely denied without one.
            results = await _query_engine(engine).query(
                _query("numbat"), principal_permissions=None
            )
            assert results == []
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_an_empty_permission_set_is_denied_not_treated_as_absent(database_url: str) -> None:
    """The distinction that makes `None`-means-unenforced safe: a
    principal who genuinely holds no permissions is a known principal,
    and ADR-0023's "absence of a permission is denial" applies to them.
    Only a missing identity is unenforced."""

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            await _index(
                engine,
                source_uri="https://example.com/perm-empty.md",
                content="the quokka audited the outbox relay",
            )
            results = await _query_engine(engine).query(
                _query("quokka"), principal_permissions=frozenset()
            )
            assert results == []
        finally:
            await engine.dispose()

    asyncio.run(_run())


class _FixedEmbedder:
    """A real `Embedder` returning a fixed vector — the resolver's own
    embed call is not what these tests are about, and a real local
    server is already proven elsewhere."""

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        return EmbeddingResponse(
            vectors=[[0.0, 0.0]],
            model_id="test-embedder",
            model_version="v1",
            dimensions=2,
            usage=UsageRecord(
                input_tokens=1,
                output_tokens=0,
                cache_read_tokens=0,
                cache_write_tokens=0,
                cost_usd=Decimal("0"),
                latency_ms=1,
                provider="local",
                model_id="test-embedder",
                retries=0,
                fallback_used=False,
            ),
        )


def test_the_real_resolver_carries_the_principal_all_the_way_down(database_url: str) -> None:
    """End to end through the path that actually reaches an LLM prompt:
    `KnowledgeResolver` is wired into `se.delivery_pipeline`'s
    `requirements-analyst` step, and before this ticket knowledge got
    there with no authorization step anywhere. The same real request,
    differing only in its principal, must now differ in what it yields.
    """

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            await _index(
                engine,
                source_uri="https://example.com/perm-resolver.md",
                content="the bilby specified the approval gate",
            )
            resolver = KnowledgeResolver(
                query_engine=_query_engine(engine),
                embedder=_FixedEmbedder(),
                embedding_model_alias="embedding-fast",
                limit=10,
            )

            permitted = await resolver.resolve(
                ContextRequest(
                    workflow_id="wf_perm",
                    step_id="requirements-analyst",
                    knowledge_query="bilby",
                    principal_permissions=_PERMITTED,
                )
            )
            denied = await resolver.resolve(
                ContextRequest(
                    workflow_id="wf_perm",
                    step_id="requirements-analyst",
                    knowledge_query="bilby",
                    principal_permissions=_DENIED,
                )
            )

            assert [item.content for item in permitted] != []
            assert denied == []
        finally:
            await engine.dispose()

    asyncio.run(_run())


@pytest.mark.parametrize("role", ["viewer", "operator", "approver", "maintainer", "admin"])
def test_every_real_role_grants_knowledge_read(role: str) -> None:
    """Product-owner decision, 2026-08-14. Without this the gate would
    starve every principal, including `admin`, rather than securing
    anything."""
    assert KNOWLEDGE_READ in permissions_for_roles([role])


def test_an_unknown_role_grants_no_knowledge_access() -> None:
    """Deny by default survives this change — `permissions_for_roles`
    still grants nothing for a role it does not know."""
    assert permissions_for_roles(["not-a-real-role"]) == frozenset()
