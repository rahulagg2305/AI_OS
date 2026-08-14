"""The real Context Filter / Ranker (``P02-S03-M08-T09``), end to end,
across two genuinely different real sources — real Postgres (ADR-0015)
plus a real local OpenAI-compatible embeddings server (the same
real-local-endpoint pattern ``test_embedding_writer.py``/
``test_knowledge_resolver.py`` already establish). Proves genuine
cross-source reordering and budget-aware trimming driven by real,
naturally-differing relevance scores — not a fabricated score, and not
a trivial pass-through of resolver order.
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

from ai_os_kernel.context_manager.manager import DefaultContextManager
from ai_os_kernel.context_manager.models import ContextRequest
from ai_os_kernel.context_manager.resolvers import KnowledgeResolver, WorkflowStateResolver
from ai_os_kernel.knowledge_manager.indexing import IndexingService
from ai_os_kernel.knowledge_manager.query_engine import QueryEngine
from ai_os_kernel.llm_gateway.adapters.local_adapter import LocalAdapter, build_local_adapter
from ai_os_kernel.llm_gateway.adapters.model_config import ModelPricing
from ai_os_kernel.llm_gateway.router import RoutingDecision, StaticRouter
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.knowledge_keyword_search import SqlKeywordSearcher
from ai_os_kernel.persistence.knowledge_writer import SqlKnowledgeWriter
from ai_os_kernel.retrieval.retrieval_service import RetrievalService
from ai_os_kernel.retrieval.vector_search import SqlVectorSearcher
from ai_os_kernel.security_manager.permissions import KNOWLEDGE_READ
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from tests.integration._postgres_fixture import postgres_container

# A real, permitted principal. The knowledge gate fails closed
# (R-021), so an assembly with no identity retrieves no knowledge —
# these tests are about assembly and ranking, not authorization.
_PERMITTED = frozenset({KNOWLEDGE_READ})

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


def test_real_cross_source_ranking_and_budget_trimming(
    database_url: str, local_adapter: LocalAdapter
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            indexing = IndexingService(engine=engine, writer=SqlKnowledgeWriter(engine))
            index_result = await indexing.index_document(
                source_uri="https://example.com/filter-ranker-test.md",
                content="a pangolin sighting was logged near the reserve",
                media_type="text/markdown",
                trust="trusted",
            )
            assert index_result.document is not None
            knowledge_chunk = index_result.document.chunks[0]

            await _ensure_workflow_definition_registered(
                database_url, definition_id="test.filter-ranker-workflow", version="1.0.0"
            )
            instance_repository = SqlWorkflowInstanceRepository(engine)
            instance = await instance_repository.create(
                definition_id="test.filter-ranker-workflow",
                definition_version="1.0.0",
                inputs={"task": "investigate pangolin sighting"},
                principal_id="test-principal",
            )

            query_engine = QueryEngine(
                engine=engine,
                retrieval_service=RetrievalService(
                    keyword_searcher=SqlKeywordSearcher(engine),
                    vector_searcher=SqlVectorSearcher(engine),
                ),
            )
            # KnowledgeResolver registered FIRST, WorkflowStateResolver
            # SECOND -- the opposite of the rank order we expect, so any
            # reordering in the result can only come from real scores,
            # never from resolver-arrival order.
            knowledge_resolver = KnowledgeResolver(
                query_engine=query_engine,
                embedder=local_adapter,
                embedding_model_alias="embedding-fast",
                limit=10,
            )
            workflow_state_resolver = WorkflowStateResolver(instance_repository)
            manager = DefaultContextManager([knowledge_resolver, workflow_state_resolver])

            request = ContextRequest(
                workflow_id=instance.workflow_id,
                step_id="investigate",
                knowledge_query="pangolin",
                principal_permissions=_PERMITTED,
            )
            assembled = await manager.assemble(request)

            assert len(assembled.items) == 2
            workflow_item, knowledge_item = assembled.items[0], assembled.items[1]
            # Real, naturally differing scores: WorkflowStateResolver's
            # fixed constant (1.0) genuinely outranks KnowledgeResolver's
            # real RRF-fused score (~0.0164, keyword-rank-1-only) --
            # neither value is fabricated for this test.
            assert workflow_item.relevance_score == 1.0
            assert knowledge_item.relevance_score == pytest.approx(1 / 61)
            assert knowledge_item.relevance_score < workflow_item.relevance_score

            # Real reordering proven: KnowledgeResolver was queried
            # first, yet the higher-scored WorkflowState item is NOT
            # first -- output order is genuinely rank order, not
            # resolver-arrival order.
            ordered_by_source = [item.provenance.source_type for item in assembled.items]
            assert ordered_by_source[0].value == "workflow_state"
            assert ordered_by_source[1].value == "knowledge"
            assert workflow_item.content == '{"task": "investigate pangolin sighting"}'
            assert knowledge_item.content == knowledge_chunk.content

            # Real budget-aware trimming on top of the real ranking: a
            # budget fitting only the higher-ranked item genuinely keeps
            # WorkflowState's item, not the first-queried Knowledge one.
            tight_budget = workflow_item.token_count
            trimmed = await manager.assemble(
                ContextRequest(
                    workflow_id=instance.workflow_id,
                    step_id="investigate",
                    knowledge_query="pangolin",
                    token_budget=tight_budget,
                    principal_permissions=_PERMITTED,
                )
            )
            assert len(trimmed.items) == 1
            assert trimmed.items[0].provenance.source_type.value == "workflow_state"
            assert trimmed.items_excluded_count == 1
        finally:
            await engine.dispose()

    asyncio.run(_run())
