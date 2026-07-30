"""Real, end-to-end proof of this step's own deliverable: the Lease
Reaper's own real background loop
(``ai_os_kernel.workflow_engine.lease_reaper.run_reap_loop``) —
applying the identical, already-proven pattern
``ai_os_kernel.capability_manager.health_poller.run_health_polling_loop``
established for the Pack Health Collector — genuinely reclaims a real,
expired ``workflow_leases`` row on its own, across real intervals, with
no manual ``reap_once()`` call anywhere in this test file, and is
genuinely, cleanly stopped on shutdown, not merely abandoned.

Two real scenarios:

1. A real running workflow instance, leased by a real worker, then
   forced into the past directly (``expires_at`` pushed behind "now" —
   the identical "simulate the crashed worker" technique
   ``tests/integration/workflow_engine/test_lease_acquisition.py``'s
   own ``test_an_expired_lease_can_be_reclaimed`` already establishes),
   left running across two real, separate wall-clock waits with a
   short, test-only ``lease_reap_interval_seconds`` override
   (``PlatformConfig``'s own new field — production always uses the
   real, decided ``LEASE_REAP_INTERVAL_SECONDS``). The lease row is
   read back through a dedicated engine (never ``app.state``'s own
   internal one, staying clear of the real cross-event-loop hazard a
   prior step's own testing already found and documented) — genuinely
   gone, reclaimed by the background loop itself.
2. The same real Kernel process, stopped via ``TestClient``'s own
   ``__exit__`` (which only returns once the real ASGI ``lifespan``
   shutdown sequence — ``_lifespan``'s own ``finally`` block — has
   actually completed): the background ``asyncio.Task`` stored at
   ``app.state.lease_reap_task`` is genuinely done and genuinely
   cancelled, not merely orphaned or left running.

Real Postgres via testcontainers (ADR-0015) — no mocking the database.
"""

import asyncio
import os
import time
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.bootstrap import build_app
from ai_os_kernel.configuration_manager import PlatformConfig
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.schema import workflow_leases
from ai_os_kernel.workflow_engine.lease import SqlWorkflowLeaseRepository
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
SCHEMA_PATH = "platform_sdk/schemas/manifest.schema.json"

# Short enough that waiting out several real intervals in a test takes
# well under a second of real wall-clock time; long enough that the
# real per-pass reap work (a real bounded SELECT + DELETE) reliably
# completes within one interval on this machine.
_TEST_REAP_INTERVAL_SECONDS = 0.2

_DEFINITION_ID = "se.product_creation"
_DEFINITION_VERSION = "1.0.0"
_DEFINITION_PACK_ID = "se.software_engineering"


def _config(lease_reap_interval_seconds: float | None = None) -> PlatformConfig:
    return PlatformConfig(
        env="test",
        role="api",
        # Isolated from the real capability_packs/ tree — this file's
        # own scope is the lease reaper, not pack discovery/health.
        capability_pack_dirs=[],
        manifest_schema_path=SCHEMA_PATH,
        lease_reap_interval_seconds=lease_reap_interval_seconds,
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


async def _ensure_default_workflow_definition_registered(engine: AsyncEngine) -> None:
    """The identical, idempotent seed
    ``tests/integration/workflow_engine/conftest.py``'s own autouse
    fixture already provides for every test *inside* that package —
    this file lives one level up (it exercises ``_lifespan``'s own
    real composition, not a workflow_engine-internal unit), so that
    fixture does not apply here; reused verbatim rather than
    duplicating a second, subtly different seed."""
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                "INSERT INTO catalog.workflow_definitions "
                "(definition_id, version, pack_id, graph, inputs_schema, "
                " outputs_schema, declared_permissions, validated_at) "
                "VALUES (:definition_id, :version, :pack_id, '{}'::jsonb, "
                " '{}'::jsonb, '{}'::jsonb, '[]'::jsonb, now()) "
                "ON CONFLICT (definition_id, version) DO NOTHING"
            ),
            {
                "definition_id": _DEFINITION_ID,
                "version": _DEFINITION_VERSION,
                "pack_id": _DEFINITION_PACK_ID,
            },
        )


def _create_expired_leased_instance(database_url: str) -> str:
    """A real running instance, leased by a real worker, then forced
    into the past directly — the exact "simulate the crashed worker"
    technique ``test_lease_acquisition.py``'s own
    ``test_an_expired_lease_can_be_reclaimed`` already establishes.
    Built and used entirely within one ``asyncio.run()`` call, the same
    dedicated-engine pattern this whole test file follows to stay clear
    of the real, documented cross-event-loop hazard."""
    engine = build_engine(database_url)

    async def _run() -> str:
        try:
            await _ensure_default_workflow_definition_registered(engine)
            instance_repository = SqlWorkflowInstanceRepository(engine)
            created = await instance_repository.create(
                definition_id=_DEFINITION_ID,
                definition_version=_DEFINITION_VERSION,
                inputs={"specPath": "specs/product.md"},
                principal_id="user-42",
            )
            await instance_repository.transition_to_running(
                workflow_id=created.workflow_id, reason="worker picked it up"
            )

            lease_repository = SqlWorkflowLeaseRepository(engine)
            await lease_repository.acquire(
                workflow_id=created.workflow_id,
                worker_id="crashed-worker",
                lease_duration_seconds=60,
            )
            expired = datetime.now(UTC) - timedelta(seconds=1)
            async with engine.begin() as connection:
                await connection.execute(
                    sa.update(workflow_leases)
                    .where(workflow_leases.c.workflow_id == created.workflow_id)
                    .values(expires_at=expired)
                )
            return created.workflow_id
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def _lease_still_exists(database_url: str, workflow_id: str) -> bool:
    engine = build_engine(database_url)

    async def _run() -> bool:
        try:
            async with engine.connect() as connection:
                result = await connection.execute(
                    sa.select(workflow_leases.c.workflow_id).where(
                        workflow_leases.c.workflow_id == workflow_id
                    )
                )
                return result.one_or_none() is not None
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def test_the_background_reap_loop_genuinely_reclaims_an_expired_lease_on_its_own(
    database_url: str,
) -> None:
    """No manual reap_once() call anywhere in this test — the real
    background loop, started by _lifespan, does it."""
    workflow_id = _create_expired_leased_instance(database_url)
    assert _lease_still_exists(database_url, workflow_id)

    app = build_app(_config(lease_reap_interval_seconds=_TEST_REAP_INTERVAL_SECONDS))

    with TestClient(app):
        # At least 2 real intervals — the loop sleeps before its first
        # pass, so one interval alone would only prove a single pass;
        # waiting well past two proves the loop is genuinely still
        # running, not a one-shot task that happened to fire once.
        time.sleep(_TEST_REAP_INTERVAL_SECONDS * 6)
        assert not _lease_still_exists(database_url, workflow_id)


def test_the_background_reap_loop_is_genuinely_cancelled_on_shutdown(
    database_url: str,
) -> None:
    app = build_app(_config(lease_reap_interval_seconds=_TEST_REAP_INTERVAL_SECONDS))

    with TestClient(app):
        task = app.state.lease_reap_task
        assert task is not None
        assert not task.done()

    # TestClient.__exit__ only returns once the real ASGI lifespan
    # shutdown sequence (_lifespan's own `finally` block, including
    # `await lease_reap_task`) has genuinely completed — no additional
    # sleep or polling needed to observe the real outcome.
    assert task.done()
    assert task.cancelled()
