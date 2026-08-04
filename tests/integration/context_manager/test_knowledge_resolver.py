"""KnowledgeResolver, end to end, against real Postgres (ADR-0015 — no
mocking the database) and a real local OpenAI-compatible embeddings
server (the identical real-local-endpoint pattern already established
in ``tests/integration/retrieval/test_embedding_writer.py``). Proves a
real workflow step's context assembly genuinely includes real, queried
knowledge content: a document indexed through the real
``IndexingService`` is retrieved through the real ``QueryEngine`` and
lands, with real provenance, inside a real ``DefaultContextManager``
assembly alongside a real ``WorkflowStateResolver`` item — two real
sources, one real assembled context.
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
from ai_os_kernel.context_manager.models import ContextRequest, SourceType
from ai_os_kernel.context_manager.resolvers import KnowledgeResolver, WorkflowStateResolver
from ai_os_kernel.knowledge_manager.indexing import IndexingService
from ai_os_kernel.knowledge_manager.query_engine import QueryEngine
from ai_os_kernel.llm_gateway.adapters.local_adapter import LocalAdapter, build_local_adapter
from ai_os_kernel.llm_gateway.adapters.model_config import ModelPricing
from ai_os_kernel.llm_gateway.models import EmbeddingRequest, EmbeddingResponse
from ai_os_kernel.llm_gateway.router import RoutingDecision, StaticRouter
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.knowledge_keyword_search import SqlKeywordSearcher
from ai_os_kernel.persistence.knowledge_writer import SqlKnowledgeWriter
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
    """The identical real, local OpenAI-compatible ``/v1/embeddings``
    server ``test_embedding_writer.py`` already establishes."""

    _body = (
        b'{"object":"list","model":"nomic-embed-text",'
        b'"data":[{"object":"embedding","index":0,"embedding":[0.1,0.2,0.3,0.4]}],'
        b'"usage":{"prompt_tokens":6,"total_tokens":6}}'
    )

    def do_POST(self) -> None:
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
    # workflow_instances carries a real composite FK to
    # catalog.workflow_definitions (data_model.md §4.1) -- the identical
    # minimal, real row this package's own conftest.py inserts for every
    # workflow_engine integration test, reused here rather than
    # reinvented, since this module has no workflow_engine test's own
    # autouse fixture to inherit.
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


def test_a_real_workflow_step_assembly_includes_real_queried_knowledge(
    database_url: str, local_adapter: LocalAdapter
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            indexing = IndexingService(engine=engine, writer=SqlKnowledgeWriter(engine))
            index_result = await indexing.index_document(
                source_uri="https://example.com/narwhal-migration.md",
                content="a narwhal migration pattern was recorded near the ice shelf",
                media_type="text/markdown",
                trust="trusted",
            )
            assert index_result.document is not None
            narwhal_chunk = index_result.document.chunks[0]

            await _ensure_workflow_definition_registered(
                database_url, definition_id="test.knowledge-resolver-workflow", version="1.0.0"
            )
            instance_repository = SqlWorkflowInstanceRepository(engine)
            instance = await instance_repository.create(
                definition_id="test.knowledge-resolver-workflow",
                definition_version="1.0.0",
                inputs={"task": "research narwhal migration"},
                principal_id="test-principal",
            )

            query_engine = QueryEngine(
                engine=engine,
                retrieval_service=RetrievalService(
                    keyword_searcher=SqlKeywordSearcher(engine),
                    vector_searcher=SqlVectorSearcher(engine),
                ),
            )
            context_manager = DefaultContextManager(
                [
                    WorkflowStateResolver(instance_repository),
                    KnowledgeResolver(
                        query_engine=query_engine,
                        embedder=local_adapter,
                        embedding_model_alias="embedding-fast",
                        limit=10,
                    ),
                ]
            )

            assembled = await context_manager.assemble(
                ContextRequest(
                    workflow_id=instance.workflow_id,
                    step_id="research",
                    knowledge_query="narwhal",
                )
            )

            assert set(assembled.sources_queried) == {
                SourceType.WORKFLOW_STATE,
                SourceType.KNOWLEDGE,
            }

            knowledge_items = [
                item
                for item in assembled.items
                if item.provenance.source_type == SourceType.KNOWLEDGE
            ]
            assert len(knowledge_items) == 1
            knowledge_item = knowledge_items[0]
            assert knowledge_item.content == narwhal_chunk.content
            assert (
                knowledge_item.provenance.identifier == f"knowledge_chunk:{narwhal_chunk.chunk_id}"
            )
            assert knowledge_item.trust == "trusted"
            # Real fused RRF score -- keyword-only here (IndexingService
            # writes no embeddings of its own, so vector search
            # genuinely finds nothing for this model), a real,
            # hand-computed value, not the WorkflowStateResolver's
            # fixed constant.
            assert knowledge_item.relevance_score == pytest.approx(1 / 61)

            workflow_items = [
                item
                for item in assembled.items
                if item.provenance.source_type == SourceType.WORKFLOW_STATE
            ]
            assert len(workflow_items) == 1
            assert "research narwhal migration" in workflow_items[0].content
            assert workflow_items[0].relevance_score == 1.0
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_no_knowledge_query_contributes_no_knowledge_items(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            await _ensure_workflow_definition_registered(
                database_url, definition_id="test.knowledge-resolver-no-query", version="1.0.0"
            )
            instance_repository = SqlWorkflowInstanceRepository(engine)
            instance = await instance_repository.create(
                definition_id="test.knowledge-resolver-no-query",
                definition_version="1.0.0",
                inputs={},
                principal_id="test-principal",
            )

            # A resolver with no real embedder call needed -- the
            # blank-query short-circuit runs before any embed() call.
            query_engine = QueryEngine(
                engine=engine,
                retrieval_service=RetrievalService(
                    keyword_searcher=SqlKeywordSearcher(engine),
                    vector_searcher=SqlVectorSearcher(engine),
                ),
            )
            context_manager = DefaultContextManager(
                [
                    KnowledgeResolver(
                        query_engine=query_engine,
                        embedder=_UnreachableEmbedder(),
                        embedding_model_alias="embedding-fast",
                        limit=10,
                    )
                ]
            )

            assembled = await context_manager.assemble(
                ContextRequest(workflow_id=instance.workflow_id, step_id="research")
            )

            assert assembled.items == []
            assert assembled.sources_queried == [SourceType.KNOWLEDGE]
        finally:
            await engine.dispose()

    asyncio.run(_run())


class _UnreachableEmbedder:
    """Proves ``KnowledgeResolver`` short-circuits on a blank
    ``knowledge_query`` *before* ever calling ``embed()`` -- any real
    call here is a genuine test failure, not a fake standing in for
    real behaviour."""

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        raise AssertionError("embed() must not be called for a blank knowledge_query")
