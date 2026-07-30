"""Real, end-to-end proof of this step's own deliverable: the Pack
Health Collector's own real background polling loop
(``ai_os_kernel.capability_manager.health_poller.run_health_polling_loop``)
genuinely re-polls every ``POLL_INTERVAL_SECONDS`` for the lifetime of
the running Kernel process — not just once, at startup — and is
genuinely, cleanly stopped on shutdown, not merely abandoned.

Two real scenarios:

1. A real Kernel process, started with a short, test-only
   ``pack_health_poll_interval_seconds`` override (``PlatformConfig``'s
   own new field — production always uses the real, decided
   ``POLL_INTERVAL_SECONDS``), left running across two real, separate
   wall-clock waits. `catalog.packs.health.checked_at` is read back
   twice, independently, through a dedicated engine (never
   ``app.state``'s own internal one, to stay clear of the real
   cross-event-loop hazard a prior step's own testing already found and
   documented) — genuinely strictly increasing both times, real proof
   of continuous re-polling, not the one-shot startup poll alone.
2. The same real Kernel process, stopped via ``TestClient``'s own
   ``__exit__`` (which only returns once the real ASGI ``lifespan``
   shutdown sequence — ``_lifespan``'s own ``finally`` block — has
   actually completed): the background ``asyncio.Task`` stored at
   ``app.state.pack_health_polling_task`` is genuinely done and
   genuinely cancelled, not merely orphaned or left running.

Real Postgres via testcontainers (ADR-0015) — no mocking the database.
"""

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
from ai_os_kernel.persistence.catalog_schema import packs as packs_table
from ai_os_kernel.persistence.engine import build_engine
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
SCHEMA_PATH = "platform_sdk/schemas/manifest.schema.json"

# Short enough that waiting out several real intervals in a test takes
# well under a second of real wall-clock time; long enough that the
# real per-pack poll work (a real SELECT + real agent resolution
# attempts) reliably completes within one interval on this machine.
_TEST_POLL_INTERVAL_SECONDS = 0.2

_SE_PACK_ID = "software-engineering"


def _config(poll_interval_seconds: float | None = None) -> PlatformConfig:
    return PlatformConfig(
        env="test",
        role="api",
        manifest_schema_path=SCHEMA_PATH,
        pack_health_poll_interval_seconds=poll_interval_seconds,
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


def _read_checked_at(database_url: str, pack_id: str) -> str:
    """A dedicated, disposable engine — never ``app.state``'s own
    internal one — built and used entirely within one ``asyncio.run()``
    call, the exact pattern
    ``tests/integration/test_bootstrap_pack_discovery.py`` already
    established to stay clear of the real, documented cross-event-loop
    hazard (asyncpg connections are bound to the loop that created
    them)."""
    engine = build_engine(database_url)

    async def _run() -> str:
        try:
            async with engine.connect() as connection:
                result = await connection.execute(
                    sa.select(packs_table.c.health).where(packs_table.c.pack_id == pack_id)
                )
                health = result.scalar_one()
            assert health is not None
            checked_at: str = health["checked_at"]
            return checked_at
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def test_the_background_polling_loop_genuinely_re_polls_across_real_intervals(
    database_url: str,
) -> None:
    app = build_app(_config(poll_interval_seconds=_TEST_POLL_INTERVAL_SECONDS))

    with TestClient(app):
        wait_seconds = _TEST_POLL_INTERVAL_SECONDS * 3
        time.sleep(wait_seconds)
        checked_at_1 = _read_checked_at(database_url, _SE_PACK_ID)

        time.sleep(wait_seconds)
        checked_at_2 = _read_checked_at(database_url, _SE_PACK_ID)

        time.sleep(wait_seconds)
        checked_at_3 = _read_checked_at(database_url, _SE_PACK_ID)

    # Genuinely, strictly increasing across two independent real waits —
    # the loop is still polling well after the one-shot startup poll,
    # not merely once.
    assert checked_at_1 < checked_at_2 < checked_at_3


def test_the_background_polling_loop_is_genuinely_cancelled_on_shutdown(
    database_url: str,
) -> None:
    app = build_app(_config(poll_interval_seconds=_TEST_POLL_INTERVAL_SECONDS))

    with TestClient(app):
        task = app.state.pack_health_polling_task
        assert task is not None
        assert not task.done()

    # TestClient.__exit__ only returns once the real ASGI lifespan
    # shutdown sequence (_lifespan's own `finally` block, including
    # `await health_polling_task`) has genuinely completed — no
    # additional sleep or polling needed to observe the real outcome.
    assert task.done()
    assert task.cancelled()
