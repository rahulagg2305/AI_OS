"""Real availability/recovery measurements against `nfr.md` §5, against
real infrastructure (real Postgres via testcontainers, ADR-0015) — see
`README.md` for which NFR-03x targets this file covers and which it
explicitly does not.

**Deliberately uses real, production interval/duration constants —
never a test-shortened override** — for NFR-033: the whole point of
this measurement is the real worst-case wall-clock number a real
worker crash would produce, so shortening the lease duration or the
reap interval here would measure a different, faster scenario than the
one `nfr.md` actually bounds. This makes this file's own tests
genuinely slow (tens of seconds) — expected and correct, matching
`nfr.md` §13's own "CI nightly" cadence for this whole suite.
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
from tests.integration._postgres_fixture import postgres_container

from ai_os_kernel.bootstrap import build_app
from ai_os_kernel.configuration_manager import PlatformConfig
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.schema import workflow_leases
from ai_os_kernel.workflow_engine.lease import SqlWorkflowLeaseRepository
from ai_os_kernel.workflow_engine.lease_reaper import LEASE_REAP_INTERVAL_SECONDS
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from ai_os_kernel.workflow_engine.worker_loop import WORKER_LEASE_DURATION_SECONDS

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
SCHEMA_PATH = "platform_sdk/schemas/manifest.schema.json"

_DEFINITION_ID = "se.product_creation"
_DEFINITION_VERSION = "1.0.0"
_DEFINITION_PACK_ID = "se.software_engineering"


def _config() -> PlatformConfig:
    # No lease_reap_interval_seconds/worker_poll_interval_seconds
    # override — this file's own point is the real, undiscounted
    # production cadence.
    return PlatformConfig(
        env="test",
        role="api",
        capability_pack_dirs=[],
        manifest_schema_path=SCHEMA_PATH,
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


async def _ensure_default_workflow_definition_registered(database_url: str) -> None:
    engine = build_engine(database_url)
    try:
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
    finally:
        await engine.dispose()


def test_nfr033_workflow_resumption_after_a_real_simulated_worker_crash(
    database_url: str,
) -> None:
    """NFR-033: workflow resumption after worker crash — target ≤ 60 s
    (lease expiry + reclaim). Real worst case: a lease is acquired with
    the real, production `WORKER_LEASE_DURATION_SECONDS`, then never
    renewed or released again (the real "worker crashed the instant
    after acquiring" scenario) — the real, undiscounted
    `LEASE_REAP_INTERVAL_SECONDS` background loop, started by the real
    `_lifespan`, is what genuinely reclaims it, timed end to end with
    no manual `reap_once()` call anywhere in this test.
    """
    asyncio.run(_ensure_default_workflow_definition_registered(database_url))

    engine = build_engine(database_url)

    async def _create_and_crash() -> str:
        try:
            repository = SqlWorkflowInstanceRepository(engine)
            created = await repository.create(
                definition_id=_DEFINITION_ID,
                definition_version=_DEFINITION_VERSION,
                inputs={},
                principal_id="perf-test",
            )
            await repository.transition_to_running(
                workflow_id=created.workflow_id, reason="perf test crash simulation"
            )
            lease_repository = SqlWorkflowLeaseRepository(engine)
            # Real production lease duration -- acquired, then never
            # renewed/released again: the real crash-the-instant-after
            # scenario, the worst real case this target bounds.
            await lease_repository.acquire(
                workflow_id=created.workflow_id,
                worker_id="perf-test-crashed-worker",
                lease_duration_seconds=WORKER_LEASE_DURATION_SECONDS,
            )
            return created.workflow_id
        finally:
            await engine.dispose()

    workflow_id = asyncio.run(_create_and_crash())

    def _lease_still_exists() -> bool:
        check_engine = build_engine(database_url)

        async def _check() -> bool:
            try:
                async with check_engine.connect() as connection:
                    result = await connection.execute(
                        sa.select(workflow_leases.c.workflow_id).where(
                            workflow_leases.c.workflow_id == workflow_id
                        )
                    )
                    return result.one_or_none() is not None
            finally:
                await check_engine.dispose()

        return asyncio.run(_check())

    app = build_app(_config())
    started = time.perf_counter()
    with TestClient(app):
        deadline = started + WORKER_LEASE_DURATION_SECONDS + LEASE_REAP_INTERVAL_SECONDS + 30.0
        while time.perf_counter() < deadline and _lease_still_exists():
            time.sleep(1.0)
    elapsed = time.perf_counter() - started

    print(
        f"\nNFR-033 real crash -> reclaim: {elapsed:.1f}s "
        f"(lease_duration={WORKER_LEASE_DURATION_SECONDS}s + "
        f"reap_interval={LEASE_REAP_INTERVAL_SECONDS}s, target <= 60s)"
    )
    assert not _lease_still_exists()
    assert elapsed <= 60.0


def test_nfr036_graceful_shutdown_drain_time(database_url: str) -> None:
    """NFR-036: graceful shutdown drain — target up to 300 s for
    in-flight steps before forced termination. Measures the real time
    a normal shutdown (five real background tasks, none genuinely
    stuck) actually takes — `TestClient.__exit__` only returns once
    the real ASGI lifespan shutdown sequence (`_lifespan`'s own
    `finally` block, including every real `GracefulShutdownCoordinator.
    shutdown()` call) has genuinely completed.
    """
    app = build_app(_config())
    client = TestClient(app)
    client.__enter__()  # Real startup -- excluded from the measurement below.
    started = time.perf_counter()
    client.__exit__(None, None, None)  # Real shutdown -- this is what NFR-036 bounds.
    elapsed = time.perf_counter() - started

    print(f"\nNFR-036 graceful shutdown (no stuck jobs): {elapsed:.2f}s (target <= 300s)")
    assert elapsed <= 300.0
