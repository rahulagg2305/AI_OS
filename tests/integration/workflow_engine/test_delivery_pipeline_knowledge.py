"""Real, production-wiring proof for ``P02-S03-M08-T12``: real, indexed
knowledge genuinely reaches the ``requirements-analyst`` step of
``se.delivery_pipeline`` through the actual production composition
(``build_pipeline_trigger``/``build_pipeline_context_manager`` in
``ai_os_kernel.workflow_engine.delivery_pipeline`` — the same functions
``kernel/bootstrap.py`` calls), not a hand-built duplicate.

Real Postgres via testcontainers (ADR-0015) and a real, local
OpenAI-compatible embeddings server (the identical pattern
``tests/integration/context_manager/test_knowledge_resolver.py`` and
``tests/integration/retrieval/test_embedding_writer.py`` already
establish) — no mocking either. Only the ``requirements-analyst`` agent
is registered: this test's own job is to prove the first step's real,
persisted output genuinely includes real indexed knowledge content, not
to drive the whole seven-step pipeline to completion (that is already
proven, unrelated to this ticket, in ``test_delivery_pipeline.py``).
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
from alembic import command
from alembic.config import Config

from ai_os_kernel.context_manager.resolvers import KnowledgeResolver
from ai_os_kernel.knowledge_manager.indexing import IndexingService
from ai_os_kernel.knowledge_manager.query_engine import QueryEngine
from ai_os_kernel.llm_gateway.adapters.local_adapter import LocalAdapter, build_local_adapter
from ai_os_kernel.llm_gateway.adapters.model_config import ModelPricing
from ai_os_kernel.llm_gateway.gateway import EchoLLMGateway
from ai_os_kernel.llm_gateway.router import RoutingDecision, StaticRouter
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.knowledge_keyword_search import SqlKeywordSearcher
from ai_os_kernel.persistence.knowledge_writer import SqlKnowledgeWriter
from ai_os_kernel.prompt_engine.renderer import InMemoryPromptEngine
from ai_os_kernel.retrieval.retrieval_service import RetrievalService
from ai_os_kernel.retrieval.vector_search import SqlVectorSearcher
from ai_os_kernel.sdk_adapters.pack_context import build_pack_context
from ai_os_kernel.security_manager.permissions import KNOWLEDGE_READ
from ai_os_kernel.workflow_engine.delivery_pipeline import build_pipeline_trigger
from ai_os_kernel.workflow_engine.registry import InMemoryAgentRegistry
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from ai_os_pack_software_engineering.agents.requirements_analyst import (
    RequirementsAnalystAgentEntrypoint,
)
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
_PACK_ID = "software-engineering"
_PACK_VERSION = "0.1.0"
_AGENT_ID = f"{_PACK_ID}/requirements-analyst"
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
    server ``test_knowledge_resolver.py`` already establishes."""

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


def _requirements_analyst_agent() -> RequirementsAnalystAgentEntrypoint:
    agent = RequirementsAnalystAgentEntrypoint()
    agent.bind_pack_context(
        build_pack_context(
            pack_id=_PACK_ID,
            pack_version=_PACK_VERSION,
            permissions=["llm:invoke"],
            llm_gateway=EchoLLMGateway(),
            prompt_engine=InMemoryPromptEngine(
                templates={("requirements.analyze", "0.1.0"): "Raw ask was: {{context}}"}
            ),
        )
    )
    return agent


def test_real_indexed_knowledge_reaches_requirements_analyst_through_production_wiring(
    database_url: str, local_adapter: LocalAdapter
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            indexing = IndexingService(engine=engine, writer=SqlKnowledgeWriter(engine))
            index_result = await indexing.index_document(
                source_uri="https://example.com/narwhal-migration-standard.md",
                content="the narwhal migration standard requires cold-water tagging",
                media_type="text/markdown",
                trust="trusted",
            )
            assert index_result.document is not None
            narwhal_chunk = index_result.document.chunks[0]

            query_engine = QueryEngine(
                engine=engine,
                retrieval_service=RetrievalService(
                    keyword_searcher=SqlKeywordSearcher(engine),
                    vector_searcher=SqlVectorSearcher(engine),
                ),
            )
            knowledge_resolver = KnowledgeResolver(
                query_engine=query_engine,
                embedder=local_adapter,
                embedding_model_alias="embedding-fast",
                limit=10,
            )

            # The exact real production composition ai_os_kernel.bootstrap
            # builds -- build_pipeline_trigger, not a hand-assembled
            # DefaultContextManager -- with only requirements-analyst
            # registered, since this test's own job ends once its real,
            # persisted output is proven, not the full seven-step run.
            trigger = build_pipeline_trigger(
                engine,
                InMemoryAgentRegistry({_AGENT_ID: _requirements_analyst_agent()}),
                knowledge_resolver=knowledge_resolver,
            )

            # A real principal, carrying real permissions — exactly what
            # `routes/workflows.py` passes from its authenticated
            # `SecurityContext`. Required since R-021 made the knowledge
            # gate fail closed: a trigger with no identity now retrieves
            # nothing, which the companion test below proves.
            result = await trigger(
                {"requirement": "narwhal migration standard"},
                "test-principal",
                principal_permissions=frozenset({KNOWLEDGE_READ}),
            )

            steps = await SqlWorkflowInstanceRepository(engine).list_steps(
                result.last_instance.workflow_id  # type: ignore[union-attr]
            )
            requirements_analyst_outputs = next(
                s.outputs for s in steps if s.step_name == "requirements-analyst"
            )
            assert requirements_analyst_outputs is not None
            analysis = requirements_analyst_outputs["analysis"]

            # Both real sources, in one real, rendered prompt: the raw
            # requirement (WorkflowStateResolver, already proven in
            # test_delivery_pipeline.py) and now real, indexed knowledge
            # content too (KnowledgeResolver, via the derived query this
            # ticket's own _QueryFromRequirementInputResolver builds).
            # Real Postgres full-text search (plainto_tsquery) ANDs every
            # query word -- "narwhal migration standard" is deliberately
            # a real subset of the indexed chunk's own words, the same
            # single/few-word query shape test_knowledge_resolver.py's
            # own real query ("narwhal") already establishes.
            assert "narwhal migration standard" in analysis
            assert narwhal_chunk.content in analysis

            # R-021, end to end through the identical production wiring:
            # the same trigger, the same indexed content, the same real
            # resolver — only the identity differs. A run carrying no
            # principal must not reach the knowledge, because the gate
            # fails closed. This is the assertion that would have failed
            # while `ExperimentRunOrchestrator` was silently creating
            # instances with `principal_permissions = NULL`.
            unidentified = await trigger(
                {"requirement": "narwhal migration standard"}, "test-principal"
            )
            unidentified_steps = await SqlWorkflowInstanceRepository(engine).list_steps(
                unidentified.last_instance.workflow_id  # type: ignore[union-attr]
            )
            unidentified_analysis = next(
                s.outputs for s in unidentified_steps if s.step_name == "requirements-analyst"
            )
            assert unidentified_analysis is not None
            # The raw requirement still arrives (WorkflowStateResolver is
            # unaffected) — only the knowledge is withheld.
            assert "narwhal migration standard" in unidentified_analysis["analysis"]
            assert narwhal_chunk.content not in unidentified_analysis["analysis"]
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_no_knowledge_resolver_configured_changes_nothing(database_url: str) -> None:
    # Zero regression: the default knowledge_resolver=None path (every
    # caller before this step, and any real deployment with no local
    # embeddings server configured) behaves exactly as before -- no
    # KnowledgeResolver in the composition at all.
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            trigger = build_pipeline_trigger(
                engine, InMemoryAgentRegistry({_AGENT_ID: _requirements_analyst_agent()})
            )

            result = await trigger({"requirement": "a plain requirement, no knowledge"}, "p")

            steps = await SqlWorkflowInstanceRepository(engine).list_steps(
                result.last_instance.workflow_id  # type: ignore[union-attr]
            )
            requirements_analyst_outputs = next(
                s.outputs for s in steps if s.step_name == "requirements-analyst"
            )
            assert requirements_analyst_outputs is not None
            assert "a plain requirement, no knowledge" in requirements_analyst_outputs["analysis"]
        finally:
            await engine.dispose()

    asyncio.run(_run())
