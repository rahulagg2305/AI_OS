"""`IndexingService`'s in-line embedding seam (`P02-S04-M09-T06`)
against real Postgres+pgvector and a real, local OpenAI-compatible
embeddings server — the identical "real local endpoint, not a live paid
provider" pattern `tests/integration/retrieval/test_embedding_writer.py`
already establishes for `embed()` itself (ADR-0015).

**Nothing here is a hand-built stand-in for the produced path.** Every
test drives the real `IndexingService.index_document`, which calls the
real `embed_chunk`, which calls the real `LocalAdapter.embed()` over
real HTTP, which writes through the real `SqlEmbeddingWriter` into a
real `knowledge.embeddings` row. The headline test then runs a real
`SqlVectorSearcher` query and finds the chunk — which is the ticket's
actual Goal ("make freshly-indexed content genuinely vector-searchable")
and is the assertion that would have failed before this step, since
`indexing.py` contained no call to `embed` at all.
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

from ai_os_kernel.knowledge_manager.indexing import IndexingError, IndexingService
from ai_os_kernel.llm_gateway.adapters.local_adapter import LocalAdapter, build_local_adapter
from ai_os_kernel.llm_gateway.adapters.model_config import ModelPricing
from ai_os_kernel.llm_gateway.router import RoutingDecision, StaticRouter
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.knowledge_schema import embeddings as embeddings_table
from ai_os_kernel.persistence.knowledge_writer import SqlKnowledgeWriter
from ai_os_kernel.retrieval.embedding_writer import SqlEmbeddingWriter
from ai_os_kernel.retrieval.vector_search import SqlVectorSearcher
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

_MODEL_ID = "nomic-embed-text"
_MODEL_ALIAS = "embedding-fast"
_VECTOR = [0.1, 0.2, 0.3, 0.4]
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


class _CountingEmbeddingsHandler(http.server.BaseHTTPRequestHandler):
    """A real OpenAI-compatible ``/v1/embeddings`` endpoint that also
    counts how many real requests it served.

    The count is what makes the cost assertions real: this ticket's
    whole fork was about billable calls, so "how many times did indexing
    actually hit the provider" has to be observed, not assumed.
    """

    requests_served = 0

    _body = (
        b'{"object":"list","model":"nomic-embed-text",'
        b'"data":[{"object":"embedding","index":0,"embedding":[0.1,0.2,0.3,0.4]}],'
        b'"usage":{"prompt_tokens":6,"total_tokens":6}}'
    )

    def do_POST(self) -> None:
        # Drain the body before responding: closing a socket with unread
        # data makes Windows send a TCP RST rather than a graceful FIN,
        # losing an already-sent response (R-015, 2026-08-12).
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        type(self).requests_served += 1
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self._body)))
        self.end_headers()
        self.wfile.write(self._body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass


@pytest.fixture(scope="module")
def embeddings_server_url() -> Generator[str, None, None]:
    server = http.server.HTTPServer(("127.0.0.1", 0), _CountingEmbeddingsHandler)
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
        routes={_MODEL_ALIAS: RoutingDecision(provider="local", model_id=_MODEL_ID)}
    )
    return build_local_adapter(
        base_url=embeddings_server_url, router=router, pricing={_MODEL_ID: _PRICING}
    )


async def _count_embeddings_for_chunks(database_url: str, chunk_ids: list[str]) -> int:
    engine = build_engine(database_url)
    try:
        async with engine.connect() as connection:
            return int(
                (
                    await connection.execute(
                        sa.select(sa.func.count())
                        .select_from(embeddings_table)
                        .where(embeddings_table.c.chunk_id.in_(chunk_ids))
                    )
                ).scalar_one()
            )
    finally:
        await engine.dispose()


def test_every_freshly_indexed_chunk_gets_a_real_vector(
    database_url: str, local_adapter: LocalAdapter
) -> None:
    """A real multi-chunk document: every chunk must end up with a real
    `knowledge.embeddings` row, and the reported count must match what
    Postgres actually holds rather than what the service believes."""

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            service = IndexingService(
                engine=engine,
                writer=SqlKnowledgeWriter(engine),
                chunk_size=100,
                chunk_overlap=10,
                embedder=local_adapter,
                embedding_writer=SqlEmbeddingWriter(engine),
                embedding_model_alias=_MODEL_ALIAS,
            )

            result = await service.index_document(
                source_uri="https://example.com/embedded-multi.md",
                content="kernel embedding coverage. " * 30,
                media_type="text/markdown",
                trust="trusted",
            )

            assert result.skipped is False
            assert result.document is not None
            chunk_ids = [chunk.chunk_id for chunk in result.document.chunks]
            assert len(chunk_ids) > 1, "expected a genuinely multi-chunk document"

            # The real count in Postgres, not the service's own tally.
            stored = await _count_embeddings_for_chunks(database_url, chunk_ids)
            assert stored == len(chunk_ids)
            assert result.embedded_chunk_count == len(chunk_ids)
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_freshly_indexed_content_is_genuinely_vector_searchable(
    database_url: str, local_adapter: LocalAdapter
) -> None:
    """The ticket's actual Goal, and the assertion that could not have
    passed before this step: index content, then find it through a real
    `SqlVectorSearcher` nearest-neighbour query over real pgvector."""

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            service = IndexingService(
                engine=engine,
                writer=SqlKnowledgeWriter(engine),
                embedder=local_adapter,
                embedding_writer=SqlEmbeddingWriter(engine),
                embedding_model_alias=_MODEL_ALIAS,
            )

            result = await service.index_document(
                source_uri="https://example.com/vector-searchable.md",
                content="the retrieval service fuses keyword and vector hits",
                media_type="text/markdown",
                trust="trusted",
            )
            assert result.document is not None
            indexed_chunk_ids = {chunk.chunk_id for chunk in result.document.chunks}

            # `embedding_model_version` is the model id here because
            # that is genuinely what the real adapter records: an
            # OpenAI-compatible server echoes back only the model it
            # served, so `LocalAdapter` sets `model_version=model_id`
            # deliberately (see its own comment). Not a value tuned to
            # make this query match.
            neighbors = await SqlVectorSearcher(engine).search(
                query_vector=_VECTOR,
                embedding_model_id=_MODEL_ID,
                embedding_model_version=_MODEL_ID,
                limit=50,
            )

            found = {n.chunk_id for n in neighbors} & indexed_chunk_ids
            assert found == indexed_chunk_ids, (
                f"freshly indexed chunks were not vector-searchable: "
                f"{indexed_chunk_ids - {n.chunk_id for n in neighbors}}"
            )
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_indexing_without_an_embedder_writes_no_vectors_and_calls_nothing(
    database_url: str, embeddings_server_url: str
) -> None:
    """Zero regression, proven rather than asserted: the pre-`T06`
    composition must behave exactly as before — no vectors, no provider
    call, no cost. `embedded_chunk_count == 0` is a correct outcome
    here, not a failure."""

    async def _run() -> None:
        engine = build_engine(database_url)
        calls_before = _CountingEmbeddingsHandler.requests_served
        try:
            service = IndexingService(engine=engine, writer=SqlKnowledgeWriter(engine))

            result = await service.index_document(
                source_uri="https://example.com/no-embedder.md",
                content="keyword only, exactly as before this step",
                media_type="text/markdown",
                trust="trusted",
            )

            assert result.skipped is False
            assert result.document is not None
            assert result.embedded_chunk_count == 0
            chunk_ids = [chunk.chunk_id for chunk in result.document.chunks]
            assert await _count_embeddings_for_chunks(database_url, chunk_ids) == 0
            assert _CountingEmbeddingsHandler.requests_served == calls_before
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_an_unchanged_reindex_costs_nothing(database_url: str, local_adapter: LocalAdapter) -> None:
    """The real cost guard. Re-indexing identical content is already a
    no-op for writes; it must also make **zero** provider calls, or the
    archive-and-replace policy would silently re-bill every unchanged
    document on every pass."""

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            service = IndexingService(
                engine=engine,
                writer=SqlKnowledgeWriter(engine),
                embedder=local_adapter,
                embedding_writer=SqlEmbeddingWriter(engine),
                embedding_model_alias=_MODEL_ALIAS,
            )
            content = "identical content indexed twice"

            first = await service.index_document(
                source_uri="https://example.com/reindex-cost.md",
                content=content,
                media_type="text/markdown",
                trust="trusted",
            )
            assert first.skipped is False
            assert first.embedded_chunk_count == 1

            calls_after_first = _CountingEmbeddingsHandler.requests_served

            second = await service.index_document(
                source_uri="https://example.com/reindex-cost.md",
                content=content,
                media_type="text/markdown",
                trust="trusted",
            )

            assert second.skipped is True
            assert second.embedded_chunk_count == 0
            assert _CountingEmbeddingsHandler.requests_served == calls_after_first
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_changed_content_embeds_the_replacement(
    database_url: str, local_adapter: LocalAdapter
) -> None:
    """Archive-and-replace must leave the *replacement* genuinely
    vector-searchable — a fresh document whose chunks had no vectors
    would be the same gap this ticket closed, reintroduced on the update
    path."""

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            service = IndexingService(
                engine=engine,
                writer=SqlKnowledgeWriter(engine),
                embedder=local_adapter,
                embedding_writer=SqlEmbeddingWriter(engine),
                embedding_model_alias=_MODEL_ALIAS,
            )
            uri = "https://example.com/changed-content.md"

            await service.index_document(
                source_uri=uri,
                content="the original text",
                media_type="text/markdown",
                trust="trusted",
            )
            replacement = await service.index_document(
                source_uri=uri,
                content="genuinely different text",
                media_type="text/markdown",
                trust="trusted",
            )

            assert replacement.skipped is False
            assert replacement.superseded_document_id is not None
            assert replacement.document is not None
            new_chunk_ids = [chunk.chunk_id for chunk in replacement.document.chunks]
            assert replacement.embedded_chunk_count == len(new_chunk_ids)
            assert await _count_embeddings_for_chunks(database_url, new_chunk_ids) == len(
                new_chunk_ids
            )
        finally:
            await engine.dispose()

    asyncio.run(_run())


@pytest.mark.parametrize(
    "kwargs",
    [
        {"embedder": object()},
        {"embedding_model_alias": _MODEL_ALIAS},
        {"embedder": object(), "embedding_model_alias": _MODEL_ALIAS},
    ],
)
def test_a_partial_embedding_configuration_is_refused_loudly(
    database_url: str, kwargs: dict[str, object]
) -> None:
    """A caller that supplied some of the three plainly wanted vectors.
    Silently indexing without them would produce exactly the
    keyword-only-index-that-looks-complete this ticket eliminated."""
    engine = build_engine(database_url)
    with pytest.raises(IndexingError, match="together"):
        IndexingService(
            engine=engine,
            writer=SqlKnowledgeWriter(engine),
            **kwargs,  # type: ignore[arg-type]
        )
