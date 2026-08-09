"""SqlEmbeddingWriter / embed_chunk against a real Postgres+pgvector
container (ADR-0015 — no mocking the database) and a real, local
OpenAI-compatible embeddings server (ADR-0015's own "real local
endpoint, not a live paid provider" pattern already established for
``embed()`` itself). Proves: a genuine embedding vector, produced by
the real ``LocalAdapter.embed()`` built at ``P02-S02-M06-T09``, is
genuinely written to and read back from ``knowledge.embeddings`` —
real ``embedding_model_id``/``embedding_model_version``/``dimensions``,
a real foreign key to an already-real ``knowledge.chunks`` row, and a
genuine rejection when that row does not exist.
"""

from __future__ import annotations

import asyncio
import http.server
import os
import threading
from collections.abc import Generator
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from ai_os_kernel.llm_gateway.adapters.local_adapter import LocalAdapter, build_local_adapter
from ai_os_kernel.llm_gateway.adapters.model_config import ModelPricing
from ai_os_kernel.llm_gateway.router import RoutingDecision, StaticRouter
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.knowledge_schema import embeddings as embeddings_table
from ai_os_kernel.persistence.knowledge_writer import ChunkInput, SqlKnowledgeWriter
from ai_os_kernel.retrieval.embedding_writer import (
    EmbeddingWriteError,
    SqlEmbeddingWriter,
    embed_chunk,
)
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
    """Serves a real, well-formed OpenAI-compatible ``/v1/embeddings``
    JSON body — the identical real local server pattern
    ``tests/unit/kernel/llm_gateway/adapters/test_local_adapter.py``
    already establishes for proving ``embed()`` itself."""

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
        server.server_close()


@pytest.fixture
def local_adapter(embeddings_server_url: str) -> LocalAdapter:
    router = StaticRouter(
        routes={"embedding-fast": RoutingDecision(provider="local", model_id=_MODEL_ID)}
    )
    return build_local_adapter(
        base_url=embeddings_server_url, router=router, pricing={_MODEL_ID: _PRICING}
    )


async def _create_real_chunk(database_url: str) -> str:
    engine = build_engine(database_url)
    try:
        writer = SqlKnowledgeWriter(engine)
        record = await writer.write_document(
            source_uri="https://example.com/embedding-writer.md",
            content_hash="sha256:" + "a" * 64,
            media_type="text/markdown",
            trust="trusted",
            chunks=[
                ChunkInput(
                    content="the kernel embedding writer",
                    token_count=4,
                    chunk_strategy_version="fixed-size-v1",
                )
            ],
        )
        return record.chunks[0].chunk_id
    finally:
        await engine.dispose()


async def _fetch_embedding(database_url: str, embedding_id: str) -> dict[str, object] | None:
    engine = build_engine(database_url)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                sa.select(embeddings_table).where(embeddings_table.c.embedding_id == embedding_id)
            )
            row = result.mappings().one_or_none()
            return dict(row) if row is not None else None
    finally:
        await engine.dispose()


def test_embed_chunk_writes_a_real_vector_readable_back_from_postgres(
    database_url: str, local_adapter: LocalAdapter
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            chunk_id = await _create_real_chunk(database_url)
            writer = SqlEmbeddingWriter(engine)

            record = await embed_chunk(
                gateway=local_adapter,
                writer=writer,
                chunk_id=chunk_id,
                text="the kernel embedding writer",
                model_alias="embedding-fast",
            )

            assert record.chunk_id == chunk_id
            assert record.embedding == [0.1, 0.2, 0.3, 0.4]
            assert record.embedding_model_id == _MODEL_ID
            assert record.dimensions == 4
            assert record.index_generation == 1

            row = await _fetch_embedding(database_url, record.embedding_id)
            assert row is not None
            assert row["chunk_id"] == chunk_id
            stored_vector = cast("list[float]", row["embedding"])
            assert [round(float(value), 4) for value in stored_vector] == [0.1, 0.2, 0.3, 0.4]
            assert row["embedding_model_id"] == _MODEL_ID
            assert row["embedding_model_version"] == _MODEL_ID
            assert row["dimensions"] == 4
            assert row["index_generation"] == 1
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_write_embedding_rejects_a_chunk_id_with_no_real_chunk_row(
    database_url: str, local_adapter: LocalAdapter
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            writer = SqlEmbeddingWriter(engine)

            with pytest.raises(EmbeddingWriteError):
                await embed_chunk(
                    gateway=local_adapter,
                    writer=writer,
                    chunk_id="chunk_does_not_exist",
                    text="orphaned text",
                    model_alias="embedding-fast",
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_two_embeddings_for_two_real_chunks_are_independently_readable(
    database_url: str, local_adapter: LocalAdapter
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            chunk_a = await _create_real_chunk(database_url)
            chunk_b = await _create_real_chunk(database_url)
            writer = SqlEmbeddingWriter(engine)

            record_a = await embed_chunk(
                gateway=local_adapter,
                writer=writer,
                chunk_id=chunk_a,
                text="chunk a text",
                model_alias="embedding-fast",
            )
            record_b = await embed_chunk(
                gateway=local_adapter,
                writer=writer,
                chunk_id=chunk_b,
                text="chunk b text",
                model_alias="embedding-fast",
            )

            assert record_a.embedding_id != record_b.embedding_id
            row_a = await _fetch_embedding(database_url, record_a.embedding_id)
            row_b = await _fetch_embedding(database_url, record_b.embedding_id)
            assert row_a is not None
            assert row_b is not None
            assert row_a["chunk_id"] == chunk_a
            assert row_b["chunk_id"] == chunk_b
        finally:
            await engine.dispose()

    asyncio.run(_run())
