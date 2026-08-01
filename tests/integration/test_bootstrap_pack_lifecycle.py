"""Deterministic, real-database verification of this step's own
deliverable: the real composition root (``bootstrap.build_app()`` +
``_lifespan``) genuinely constructs and attaches
``app.state.pack_lifecycle_repository`` — not a test constructing a
:class:`~ai_os_kernel.capability_manager.repository.SqlPackLifecycleRepository`
directly, as ``tests/integration/capability_manager/test_pack_lifecycle.py``
does.

**Exercises pack-lifecycle operations through a dedicated engine, not
``app.state.pack_lifecycle_repository`` directly** (fixed
``P01-S06-M43-T04``, root-caused via a real, live CI hang: run
``30682840924``/``30685613509``/``30686983934``). ``app.state``'s own
repository is built on ``TestClient``'s own background event loop
(``_lifespan`` runs there); calling its async methods from this test's
own separate ``asyncio.run()`` call — a second, independently-running
event loop on the main thread — is exactly the cross-event-loop hazard
``test_lease_reap_loop.py``'s own docstring already documents and
works around the identical way. Both loops share the same real
Postgres connection pool underneath; two event loops concurrently
checking connections out of one asyncpg pool is a genuine hang risk,
not merely a style preference — confirmed live: adding a third
background loop to ``_lifespan`` (the audit-chain verification job,
``P01-S04-M03-T06``) tipped this latent, pre-existing hazard into an
actual, reproducible ~20-minute stall for the first time. This file's
own two affected tests now assert ``app.state.pack_lifecycle_repository``
is real and constructed (this file's own stated purpose) via a cheap,
synchronous, no-event-loop-crossing check, and separately exercise real
register/activate/deactivate/get_pack behaviour through a dedicated
``SqlPackLifecycleRepository`` over its own engine, against the same
real, ``_lifespan``-migrated database — both intents preserved, one
hazard removed.

Real Postgres via testcontainers (ADR-0015) — no mocking the database.
"""

import asyncio
import os
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from ai_os_kernel.bootstrap import build_app
from ai_os_kernel.capability_manager.errors import (
    InvalidPackTransitionError,
    PackNotFoundError,
)
from ai_os_kernel.capability_manager.repository import SqlPackLifecycleRepository
from ai_os_kernel.configuration_manager import PlatformConfig
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.workflow_engine.pack_state import PackState
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
SCHEMA_PATH = "platform_sdk/schemas/manifest.schema.json"


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


def _config() -> PlatformConfig:
    return PlatformConfig(
        env="test",
        role="api",
        capability_pack_dirs=[],
        manifest_schema_path=SCHEMA_PATH,
    )


def test_the_real_composition_root_registers_and_activates_a_pack(database_url: str) -> None:
    app = build_app(_config())

    with TestClient(app):
        # AIOS_DATABASE_URL is set by the database_url fixture above, so
        # _lifespan's real DatabaseSettings()/build_engine() calls
        # resolve to this real, migrated container — the composition
        # root's own env-driven wiring, not a test-supplied override.
        # Asserted here, synchronously, never awaited from this test's
        # own separate event loop below (see this module's own
        # docstring for the cross-event-loop hazard that would create).
        assert isinstance(app.state.pack_lifecycle_repository, SqlPackLifecycleRepository)

    # A dedicated engine, never app.state's own, against the same real,
    # already-migrated database — the identical pattern
    # test_lease_reap_loop.py already establishes.
    engine = build_engine(database_url)

    async def _run() -> None:
        repository = SqlPackLifecycleRepository(engine)
        try:
            registered = await repository.register(
                pack_id="test.bootstrap_wired_pack",
                version="1.0.0",
                manifest={"name": "bootstrap-wired-pack"},
                sdk_version="1.0.0",
                min_kernel_version="1.0.0",
                actor="test-actor",
                reason="initial install",
            )
            assert registered.state is PackState.INSTALLED

            activated = await repository.activate(
                pack_id="test.bootstrap_wired_pack", actor="test-actor", reason="go live"
            )
            assert activated.state is PackState.ACTIVATED

            deactivated = await repository.deactivate(
                pack_id="test.bootstrap_wired_pack", actor="test-actor", reason="withdraw"
            )
            assert deactivated.state is PackState.DEACTIVATED

            fetched = await repository.get_pack("test.bootstrap_wired_pack")
            assert fetched == deactivated
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_the_real_composition_roots_repository_rejects_invalid_transitions(
    database_url: str,
) -> None:
    app = build_app(_config())

    with TestClient(app):
        assert isinstance(app.state.pack_lifecycle_repository, SqlPackLifecycleRepository)

    engine = build_engine(database_url)

    async def _run() -> None:
        repository = SqlPackLifecycleRepository(engine)
        try:
            with pytest.raises(PackNotFoundError):
                await repository.activate(
                    pack_id="test.bootstrap_never_registered",
                    actor="test-actor",
                    reason="go live",
                )

            await repository.register(
                pack_id="test.bootstrap_invalid_transition",
                version="1.0.0",
                manifest={},
                sdk_version="1.0.0",
                min_kernel_version="1.0.0",
                actor="test-actor",
                reason="initial install",
            )
            with pytest.raises(InvalidPackTransitionError):
                # installed, not activated — cannot deactivate yet.
                await repository.deactivate(
                    pack_id="test.bootstrap_invalid_transition",
                    actor="test-actor",
                    reason="withdraw",
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_bare_test_client_never_configures_the_pack_lifecycle_repository(
    database_url: str,
) -> None:
    # The identical bare-TestClient-never-triggers-the-lifespan
    # invariant test_bootstrap.py's own test already establishes for
    # agent_registry — verified here for this attribute too.
    app = build_app(_config())
    client = TestClient(app)

    client.get("/api/v1/health/live")

    assert not hasattr(app.state, "pack_lifecycle_repository")
