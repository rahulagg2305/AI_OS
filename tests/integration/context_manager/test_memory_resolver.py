"""MemoryResolver, end to end, against real Postgres (ADR-0015 — no
mocking the database) and, for the three-source test, a real local
OpenAI-compatible embeddings server (the identical pattern
``test_knowledge_resolver.py`` already establishes). Proves real,
durable memory genuinely flows into a real context assembly across a
*different* workflow run (never filtered by ``source_workflow_id``),
and calibrates context_manager.md's own "Knowledge outranks Memory in
authority" rule against three real, differing scores in one real
assembly — not just asserted, computed.

Each test uses a distinct real ``memory_type`` (``engineering``/
``asset``/``workflow`` — the only three the schema's own check
constraint allows) purely for test isolation against the shared,
module-scoped Postgres container: ``MemoryResolver`` genuinely queries
every row of its configured type across every workflow, so two tests
sharing a type would otherwise see each other's rows.
"""

from __future__ import annotations

import asyncio
import http.server
import os
import threading
from collections.abc import Generator
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.context_manager.manager import DefaultContextManager
from ai_os_kernel.context_manager.models import ContextRequest, SourceType
from ai_os_kernel.context_manager.resolvers import (
    KnowledgeResolver,
    MemoryResolver,
    WorkflowStateResolver,
)
from ai_os_kernel.knowledge_manager.indexing import IndexingService
from ai_os_kernel.knowledge_manager.query_engine import QueryEngine
from ai_os_kernel.llm_gateway.adapters.local_adapter import LocalAdapter, build_local_adapter
from ai_os_kernel.llm_gateway.adapters.model_config import ModelPricing
from ai_os_kernel.llm_gateway.router import RoutingDecision, StaticRouter
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.knowledge_keyword_search import SqlKeywordSearcher
from ai_os_kernel.persistence.knowledge_writer import SqlKnowledgeWriter
from ai_os_kernel.persistence.memory_writer import SqlMemoryStore
from ai_os_kernel.retrieval.retrieval_service import RetrievalService
from ai_os_kernel.retrieval.vector_search import SqlVectorSearcher
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
_MODEL_ID = "nomic-embed-text"
_PRICING = ModelPricing(
    input_per_million_usd=Decimal("0.00"), output_per_million_usd=Decimal("0.00")
)


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


class _SuccessfulEmbeddingsHandler(http.server.BaseHTTPRequestHandler):
    _body = (
        b'{"object":"list","model":"nomic-embed-text",'
        b'"data":[{"object":"embedding","index":0,"embedding":[0.1,0.2,0.3,0.4]}],'
        b'"usage":{"prompt_tokens":6,"total_tokens":6}}'
    )

    def do_POST(self) -> None:
        # Drain the request body before responding. Closing a socket
        # with unread data in its receive buffer makes Windows send a
        # TCP RST instead of a graceful FIN, so the client can lose a
        # response it had already been sent and surface a connection
        # error instead (R-015, 2026-08-12).
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self._body)))
        self.end_headers()
        self.wfile.write(self._body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass


@pytest.fixture(scope="module")
def embeddings_server_url() -> Generator[str, None, None]:
    server = http.server.HTTPServer(("127.0.0.1", 0), _SuccessfulEmbeddingsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


@pytest.fixture
def local_adapter(embeddings_server_url: str) -> LocalAdapter:
    router = StaticRouter(
        routes={"embedding-fast": RoutingDecision(provider="local", model_id=_MODEL_ID)}
    )
    return build_local_adapter(
        base_url=embeddings_server_url, router=router, pricing={_MODEL_ID: _PRICING}
    )


async def _ensure_workflow_definition_registered(
    database_url: str, *, definition_id: str, version: str
) -> None:
    engine = build_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                sa.text(
                    "INSERT INTO catalog.workflow_definitions "
                    "(definition_id, version, pack_id, graph, inputs_schema, "
                    " outputs_schema, declared_permissions, validated_at) "
                    "VALUES (:definition_id, :version, 'test.pack', '{}'::jsonb, "
                    " '{}'::jsonb, '{}'::jsonb, '[]'::jsonb, now()) "
                    "ON CONFLICT (definition_id, version) DO NOTHING"
                ),
                {"definition_id": definition_id, "version": version},
            )
    finally:
        await engine.dispose()


async def _create_real_workflow_instance(
    database_url: str, engine: AsyncEngine, *, suffix: str
) -> str:
    definition_id = f"test.memory-resolver-workflow-{suffix}"
    version = "1.0.0"
    await _ensure_workflow_definition_registered(
        database_url, definition_id=definition_id, version=version
    )
    instance = await SqlWorkflowInstanceRepository(engine).create(
        definition_id=definition_id,
        definition_version=version,
        inputs={"task": f"task for {suffix}"},
        principal_id="test-principal",
    )
    return instance.workflow_id


def test_memory_written_under_a_different_run_still_flows_into_this_context(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            other_workflow_id = await _create_real_workflow_instance(
                database_url, engine, suffix="other-a"
            )
            memory_store = SqlMemoryStore(engine)
            written = await memory_store.write_memory(
                memory_type="engineering",
                content="use exponential backoff for retries",
                source_workflow_id=other_workflow_id,
            )

            this_workflow_id = await _create_real_workflow_instance(
                database_url, engine, suffix="this-a"
            )
            context_manager = DefaultContextManager(
                [MemoryResolver(memory_store=memory_store, memory_type="engineering", limit=10)]
            )

            assembled = await context_manager.assemble(
                ContextRequest(workflow_id=this_workflow_id, step_id="research")
            )

            assert assembled.sources_queried == [SourceType.MEMORY]
            assert len(assembled.items) == 1
            memory_item = assembled.items[0]
            assert memory_item.content == "use exponential backoff for retries"
            assert memory_item.provenance.identifier == f"memory_item:{written.memory_id}"
            assert memory_item.trust == "untrusted"
            # No quality_signal was set -- a real, principled 0.0, not
            # a fabricated positive score.
            assert memory_item.relevance_score == 0.0
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_three_real_sources_calibrate_knowledge_outranks_memory(
    database_url: str, local_adapter: LocalAdapter
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            indexing = IndexingService(engine=engine, writer=SqlKnowledgeWriter(engine))
            index_result = await indexing.index_document(
                source_uri="https://example.com/three-source-calibration.md",
                content="a serval sighting was logged near the reserve",
                media_type="text/markdown",
                trust="trusted",
            )
            assert index_result.document is not None

            memory_store = SqlMemoryStore(engine)
            other_workflow_id = await _create_real_workflow_instance(
                database_url, engine, suffix="other-b"
            )
            await memory_store.write_memory(
                memory_type="asset",
                content="a diagram generated during a prior serval survey",
                source_workflow_id=other_workflow_id,
            )

            this_workflow_id = await _create_real_workflow_instance(
                database_url, engine, suffix="this-b"
            )
            instance_repository = SqlWorkflowInstanceRepository(engine)

            query_engine = QueryEngine(
                engine=engine,
                retrieval_service=RetrievalService(
                    keyword_searcher=SqlKeywordSearcher(engine),
                    vector_searcher=SqlVectorSearcher(engine),
                ),
            )
            context_manager = DefaultContextManager(
                [
                    MemoryResolver(memory_store=memory_store, memory_type="asset", limit=10),
                    KnowledgeResolver(
                        query_engine=query_engine,
                        embedder=local_adapter,
                        embedding_model_alias="embedding-fast",
                        limit=10,
                    ),
                    WorkflowStateResolver(instance_repository),
                ]
            )

            assembled = await context_manager.assemble(
                ContextRequest(
                    workflow_id=this_workflow_id,
                    step_id="research",
                    knowledge_query="serval",
                )
            )

            assert set(assembled.sources_queried) == {
                SourceType.MEMORY,
                SourceType.KNOWLEDGE,
                SourceType.WORKFLOW_STATE,
            }
            assert len(assembled.items) == 3

            # Real fused RRF score (keyword-only, IndexingService writes
            # no embeddings of its own): 1/(60+1).
            expected_knowledge_score = 1 / 61
            ordered_sources = [item.provenance.source_type for item in assembled.items]
            ordered_scores = [item.relevance_score for item in assembled.items]

            assert ordered_sources == [
                SourceType.WORKFLOW_STATE,
                SourceType.KNOWLEDGE,
                SourceType.MEMORY,
            ]
            assert ordered_scores[0] == 1.0
            assert ordered_scores[1] == pytest.approx(expected_knowledge_score)
            assert ordered_scores[2] == 0.0
            # The real calibration this ticket asks for: Knowledge
            # genuinely outranks Memory, with real, differing, non-zero
            # (for Knowledge) scores -- not asserted by fiat.
            assert ordered_scores[1] > ordered_scores[2]
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_real_quality_signal_is_reflected_directly_as_relevance(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            workflow_id = await _create_real_workflow_instance(
                database_url, engine, suffix="quality-c"
            )
            memory_store = SqlMemoryStore(engine)
            await memory_store.write_memory(
                memory_type="workflow",
                content="this run took 4 attempts to succeed",
                source_workflow_id=workflow_id,
                quality_signal=Decimal("0.5"),
            )

            context_manager = DefaultContextManager(
                [MemoryResolver(memory_store=memory_store, memory_type="workflow", limit=10)]
            )

            assembled = await context_manager.assemble(
                ContextRequest(workflow_id=workflow_id, step_id="research")
            )

            assert len(assembled.items) == 1
            assert assembled.items[0].relevance_score == 0.5
        finally:
            await engine.dispose()

    asyncio.run(_run())
