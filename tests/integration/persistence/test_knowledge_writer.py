"""SqlKnowledgeWriter against a real Postgres container (ADR-0015 — no
mocking the database). Proves: writing a document and its already-chunked
content produces real ``knowledge.documents``/``knowledge.chunks`` rows
with the documented columns, ``ordinal`` is derived from input order,
chunk ``content_tsv`` still genuinely generates through this write path
(not just through a raw ``INSERT``, see ``test_migrations.py``'s own
proof of the column itself), and the writer's own validation (blank
fields, an empty chunk sequence) is enforced before any row is written.
"""

import asyncio
import os
from collections.abc import Generator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.knowledge_writer import (
    ChunkInput,
    KnowledgeWriteError,
    SqlKnowledgeWriter,
)
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


def _chunk(content: str, *, token_count: int = 3) -> ChunkInput:
    return ChunkInput(
        content=content,
        token_count=token_count,
        chunk_strategy_version="fixed-size-v1",
        metadata={"section": content[:5]},
    )


async def _fetch_document(database_url: str, document_id: str) -> dict[str, object] | None:
    engine = build_engine(database_url)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                sa.text("SELECT * FROM knowledge.documents WHERE document_id = :document_id"),
                {"document_id": document_id},
            )
            row = result.mappings().one_or_none()
            return dict(row) if row is not None else None
    finally:
        await engine.dispose()


async def _fetch_chunks(database_url: str, document_id: str) -> list[dict[str, object]]:
    engine = build_engine(database_url)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                sa.text(
                    "SELECT *, content_tsv::text AS content_tsv_text FROM knowledge.chunks "
                    "WHERE document_id = :document_id ORDER BY ordinal"
                ),
                {"document_id": document_id},
            )
            return [dict(row) for row in result.mappings().all()]
    finally:
        await engine.dispose()


def test_write_document_writes_the_documented_columns(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            writer = SqlKnowledgeWriter(engine)

            record = await writer.write_document(
                source_uri="https://example.com/architecture.md",
                content_hash="sha256:" + "a" * 64,
                media_type="text/markdown",
                trust="trusted",
                project_id="proj_aios",
                chunks=[_chunk("architecture overview"), _chunk("deployment topology")],
            )

            document_row = await _fetch_document(database_url, record.document_id)
            assert document_row is not None
            assert document_row["source_uri"] == "https://example.com/architecture.md"
            assert document_row["content_hash"] == "sha256:" + "a" * 64
            assert document_row["media_type"] == "text/markdown"
            assert document_row["project_id"] == "proj_aios"
            assert document_row["trust"] == "trusted"
            assert document_row["ingested_at"] is not None
            assert document_row["archived_at"] is None

            chunk_rows = await _fetch_chunks(database_url, record.document_id)
            assert len(chunk_rows) == 2
            assert [row["ordinal"] for row in chunk_rows] == [0, 1]
            assert chunk_rows[0]["content"] == "architecture overview"
            assert chunk_rows[1]["content"] == "deployment topology"
            assert chunk_rows[0]["chunk_strategy_version"] == "fixed-size-v1"
            assert chunk_rows[0]["metadata"] == {"section": "archi"}
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_write_document_generates_prefixed_ids_for_document_and_chunks(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            writer = SqlKnowledgeWriter(engine)

            record = await writer.write_document(
                source_uri="https://example.com/ids.md",
                content_hash="sha256:" + "b" * 64,
                media_type="text/markdown",
                trust="untrusted",
                chunks=[_chunk("one chunk only")],
            )

            assert record.document_id.startswith("doc_")
            assert all(chunk.chunk_id.startswith("chunk_") for chunk in record.chunks)
            assert all(chunk.document_id == record.document_id for chunk in record.chunks)
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_write_document_content_tsv_is_generated_for_each_chunk(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            writer = SqlKnowledgeWriter(engine)

            record = await writer.write_document(
                source_uri="https://example.com/tsv.md",
                content_hash="sha256:" + "c" * 64,
                media_type="text/markdown",
                trust="trusted",
                chunks=[_chunk("the kernel architecture document")],
            )

            chunk_rows = await _fetch_chunks(database_url, record.document_id)
            assert "architectur" in str(chunk_rows[0]["content_tsv_text"])
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_write_document_defaults_project_id_to_none_when_not_supplied(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            writer = SqlKnowledgeWriter(engine)

            record = await writer.write_document(
                source_uri="https://example.com/no-project.md",
                content_hash="sha256:" + "d" * 64,
                media_type="text/markdown",
                trust="trusted",
                chunks=[_chunk("no project supplied")],
            )

            assert record.project_id is None
            document_row = await _fetch_document(database_url, record.document_id)
            assert document_row is not None
            assert document_row["project_id"] is None
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_write_document_two_calls_create_two_independent_documents(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            writer = SqlKnowledgeWriter(engine)

            first = await writer.write_document(
                source_uri="https://example.com/repeat.md",
                content_hash="sha256:" + "e" * 64,
                media_type="text/markdown",
                trust="trusted",
                chunks=[_chunk("identical content")],
            )
            second = await writer.write_document(
                source_uri="https://example.com/repeat.md",
                content_hash="sha256:" + "e" * 64,
                media_type="text/markdown",
                trust="trusted",
                chunks=[_chunk("identical content")],
            )

            assert first.document_id != second.document_id
            assert len(await _fetch_chunks(database_url, first.document_id)) == 1
            assert len(await _fetch_chunks(database_url, second.document_id)) == 1
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_write_document_rejects_an_empty_chunk_sequence(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            writer = SqlKnowledgeWriter(engine)

            with pytest.raises(KnowledgeWriteError, match="chunks must not be empty"):
                await writer.write_document(
                    source_uri="https://example.com/empty.md",
                    content_hash="sha256:" + "f" * 64,
                    media_type="text/markdown",
                    trust="trusted",
                    chunks=[],
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())


async def _attempt_write_with(
    writer: SqlKnowledgeWriter, *, source_uri: str, content_hash: str, media_type: str
) -> None:
    await writer.write_document(
        source_uri=source_uri,
        content_hash=content_hash,
        media_type=media_type,
        trust="trusted",
        chunks=[_chunk("some content")],
    )


def test_write_document_rejects_a_blank_source_uri(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            writer = SqlKnowledgeWriter(engine)
            with pytest.raises(KnowledgeWriteError, match="must not be blank"):
                await _attempt_write_with(
                    writer,
                    source_uri="",
                    content_hash="sha256:" + "0" * 64,
                    media_type="text/markdown",
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_write_document_rejects_a_blank_content_hash(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            writer = SqlKnowledgeWriter(engine)
            with pytest.raises(KnowledgeWriteError, match="must not be blank"):
                await _attempt_write_with(
                    writer,
                    source_uri="https://example.com/blank.md",
                    content_hash="   ",
                    media_type="text/markdown",
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_write_document_rejects_a_blank_media_type(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            writer = SqlKnowledgeWriter(engine)
            with pytest.raises(KnowledgeWriteError, match="must not be blank"):
                await _attempt_write_with(
                    writer,
                    source_uri="https://example.com/blank.md",
                    content_hash="sha256:" + "0" * 64,
                    media_type="",
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_write_document_rejects_an_unknown_trust_value(database_url: str) -> None:
    """The ``ck_documents_trust`` check constraint (data_model.md §7's
    own ``trusted``/``untrusted`` enumeration) is enforced by the
    database, not re-validated in Python — a violation surfaces as a
    :class:`KnowledgeWriteError`, wrapping the underlying
    :class:`sqlalchemy.exc.IntegrityError`, never a bare stack trace."""

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            writer = SqlKnowledgeWriter(engine)

            with pytest.raises(KnowledgeWriteError):
                await writer.write_document(
                    source_uri="https://example.com/bad-trust.md",
                    content_hash="sha256:" + "1" * 64,
                    media_type="text/markdown",
                    trust="unknown",  # type: ignore[arg-type]
                    chunks=[_chunk("some content")],
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())
