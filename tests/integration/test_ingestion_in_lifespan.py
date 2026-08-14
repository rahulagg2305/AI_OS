"""Real, end-to-end proof of this ticket's actual Goal
(`P02-S04-M09-T07`): knowledge ingestion is **automatic, not merely
callable**.

`index_document_file` was proven and tested but had no production caller
anywhere in `kernel/src` — no `bootstrap.py` wiring, no API route — so
`knowledge_manager.md` recorded ingestion as "reachable, not yet
automatic". These tests start a real `_lifespan` through the real
`build_app` composition and assert that real files on disk become real
`knowledge.documents` rows **with no ingestion call anywhere in the
test**, which is the only assertion that would have failed before.

The negative control matters as much: with `knowledge_source_dirs`
unset — every environment today — nothing is ingested at all, so this
feature cannot start because a default said so.

Real Postgres via testcontainers (ADR-0015) — no mocking the database.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Generator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from ai_os_kernel.bootstrap import build_app
from ai_os_kernel.configuration_manager import PlatformConfig
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.knowledge_schema import documents as documents_table
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
SCHEMA_PATH = "platform_sdk/schemas/manifest.schema.json"

# The scan is a one-shot task over a handful of real files, so this is a
# real completion wait, not a poll interval. Generous because a real
# Postgres round trip per document is genuinely involved.
_INGESTION_WAIT_SECONDS = 15.0
_POLL_SECONDS = 0.2


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


def _config(knowledge_source_dirs: list[str] | None) -> PlatformConfig:
    return PlatformConfig(
        env="test",
        role="api",
        # Isolated from the real capability_packs/ tree — this file's own
        # scope is knowledge ingestion, not pack discovery/health.
        capability_pack_dirs=[],
        manifest_schema_path=SCHEMA_PATH,
        knowledge_source_dirs=knowledge_source_dirs,
    )


def _count_documents(database_url: str, source_uris: list[str]) -> int:
    engine = build_engine(database_url)

    async def _run() -> int:
        try:
            async with engine.connect() as connection:
                return int(
                    (
                        await connection.execute(
                            sa.select(sa.func.count())
                            .select_from(documents_table)
                            .where(documents_table.c.source_uri.in_(source_uris))
                        )
                    ).scalar_one()
                )
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def _trust_values(database_url: str, source_uris: list[str]) -> set[str]:
    engine = build_engine(database_url)

    async def _run() -> set[str]:
        try:
            async with engine.connect() as connection:
                rows = (
                    await connection.execute(
                        sa.select(documents_table.c.trust).where(
                            documents_table.c.source_uri.in_(source_uris)
                        )
                    )
                ).scalars()
                return set(rows)
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def _write_docs_tree(root: Path) -> list[str]:
    root.mkdir(parents=True)
    (root / "adr").mkdir()
    files = {
        root / "adr" / "ADR-9001-lifespan.md": "# ADR-9001\n\nIngestion runs at startup.",
        root / "overview.md": "# Overview\n\nThe Kernel owns workflow execution.",
    }
    for path, text in files.items():
        path.write_text(text, encoding="utf-8")
    return [str(path) for path in files]


def test_ingestion_genuinely_runs_on_its_own_from_a_real_lifespan(
    database_url: str, tmp_path: Path
) -> None:
    """No ingestion call anywhere in this test. `_lifespan` starts the
    real scan because `knowledge_source_dirs` is configured, and real
    files on disk become real rows."""
    root = tmp_path / "auto-docs"
    source_uris = _write_docs_tree(root)
    assert _count_documents(database_url, source_uris) == 0

    app = build_app(_config([str(root)]))

    with TestClient(app):
        deadline = time.monotonic() + _INGESTION_WAIT_SECONDS
        while time.monotonic() < deadline:
            if _count_documents(database_url, source_uris) == len(source_uris):
                break
            time.sleep(_POLL_SECONDS)

        assert _count_documents(database_url, source_uris) == len(source_uris)
        # ADR-0016 control 1, all the way through the real composition.
        assert _trust_values(database_url, source_uris) == {"untrusted"}


def test_no_configuration_means_no_ingestion_at_all(database_url: str, tmp_path: Path) -> None:
    """The negative control, and the real default. Every environment
    today leaves `knowledge_source_dirs` unset, and this feature reads
    the filesystem and can spend real money — so it must not start
    because a default said so."""
    root = tmp_path / "unconfigured-docs"
    source_uris = _write_docs_tree(root)

    app = build_app(_config(None))

    with TestClient(app):
        assert not hasattr(app.state, "knowledge_ingestion_task")
        time.sleep(1.0)
        assert _count_documents(database_url, source_uris) == 0


def test_the_ingestion_task_is_registered_for_clean_shutdown(
    database_url: str, tmp_path: Path
) -> None:
    """A long first scan must be cancellable rather than waited out, so
    the task is registered with the real shutdown coordinator."""
    root = tmp_path / "shutdown-docs"
    _write_docs_tree(root)

    app = build_app(_config([str(root)]))

    with TestClient(app):
        task = app.state.knowledge_ingestion_task
        assert task is not None

    # TestClient.__exit__ returns only once the real ASGI lifespan
    # shutdown sequence has genuinely completed.
    assert task.done()
