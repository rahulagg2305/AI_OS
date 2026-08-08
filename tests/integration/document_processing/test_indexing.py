"""``index_document_file`` against real Postgres (ADR-0015 — no mocking
the database or the real writer/chunker it composes) — proves the real
Document Processing → Indexing pipeline glue this step adds
(`P05-S01-M26-T02`): a real file on real disk, genuinely parsed, then
genuinely chunked and written into ``knowledge.documents``/
``knowledge.chunks`` through the pre-existing, unchanged
:class:`~ai_os_kernel.knowledge_manager.indexing.IndexingService`.
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

from ai_os_kernel.document_processing.errors import UnsupportedDocumentFormatError
from ai_os_kernel.document_processing.indexing import index_document_file
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.knowledge_schema import chunks as chunks_table
from ai_os_kernel.persistence.knowledge_schema import documents as documents_table
from ai_os_kernel.persistence.knowledge_writer import SqlKnowledgeWriter
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


def test_a_real_markdown_file_is_parsed_chunked_and_written(
    database_url: str, tmp_path: Path
) -> None:
    path = tmp_path / "spec.md"
    path.write_text("# Title\n\n" + ("word " * 500) + "\n", encoding="utf-8")

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            result = await index_document_file(
                path, engine=engine, writer=SqlKnowledgeWriter(engine), trust="trusted"
            )

            assert result.skipped is False
            document = result.document
            assert document is not None
            assert document.source_uri == str(path)
            assert document.media_type == "text/markdown"
            assert document.trust == "trusted"
            assert len(document.chunks) > 1  # real content long enough to split

            async with engine.connect() as connection:
                doc_row = (
                    (
                        await connection.execute(
                            sa.select(documents_table).where(
                                documents_table.c.document_id == document.document_id
                            )
                        )
                    )
                    .mappings()
                    .one()
                )
                chunk_count = (
                    await connection.execute(
                        sa.select(sa.func.count())
                        .select_from(chunks_table)
                        .where(chunks_table.c.document_id == document.document_id)
                    )
                ).scalar_one()

            assert doc_row["media_type"] == "text/markdown"
            assert chunk_count == len(document.chunks)
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_real_code_file_is_indexed_with_a_source_media_type(
    database_url: str, tmp_path: Path
) -> None:
    path = tmp_path / "module.py"
    path.write_text("def f():\n    return 1\n", encoding="utf-8")

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            result = await index_document_file(
                path, engine=engine, writer=SqlKnowledgeWriter(engine), trust="untrusted"
            )

            assert result.document is not None
            assert result.document.media_type == "text/x-source"
            assert result.document.trust == "untrusted"
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_reindexing_the_same_unchanged_file_is_a_real_no_op(
    database_url: str, tmp_path: Path
) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("stable content\n", encoding="utf-8")

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            writer = SqlKnowledgeWriter(engine)
            first = await index_document_file(path, engine=engine, writer=writer, trust="trusted")
            second = await index_document_file(path, engine=engine, writer=writer, trust="trusted")

            assert first.skipped is False
            assert second.skipped is True
            assert second.document is None
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_deferred_pdf_format_is_refused_before_any_write(
    database_url: str, tmp_path: Path
) -> None:
    path = tmp_path / "spec.pdf"
    path.write_bytes(b"%PDF-1.4 not real")

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            with pytest.raises(UnsupportedDocumentFormatError, match="PDF"):
                await index_document_file(
                    path, engine=engine, writer=SqlKnowledgeWriter(engine), trust="trusted"
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())
