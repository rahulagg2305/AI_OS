"""Real, end-to-end proof of this step's own deliverable: the
multi-instance worker loop's own real background loop
(``ai_os_kernel.workflow_engine.worker_loop.run_worker_loop``) —
applying the identical, already-proven pattern
``ai_os_kernel.workflow_engine.lease_reaper.run_reap_loop`` established
— genuinely discovers and drives a real, directly-created running
instance to completion on its own, through the real, live ``_lifespan``
composition (``P02-S01-M05-T14``, moving this capability from "proven,
unused" to "proven, running" for the first time), with no manual
``tick_once()`` call anywhere in this test, and is genuinely, cleanly
stopped on shutdown, not merely abandoned.

A ``human_approval``-typed step is used deliberately: it always
completes via ``NoOpStepExecutor`` regardless of which agent/tool
registry ``_lifespan`` happens to build (real or credential-degraded),
so this test needs no LLM credential and is fully deterministic.
Definition resolution genuinely goes through the real
``SqlWorkflowDefinitionCatalog.get()`` this step added — the
definition is registered directly against the database, never handed
to the app in any way; the live worker loop is what discovers it.

Real Postgres via testcontainers (ADR-0015) — no mocking the database.
"""

import asyncio
import os
import time
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from ai_os_kernel.bootstrap import build_app
from ai_os_kernel.configuration_manager import PlatformConfig
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.workflow_engine.definition_catalog import SqlWorkflowDefinitionCatalog
from ai_os_kernel.workflow_engine.instance import WorkflowInstanceStatus
from ai_os_kernel.workflow_engine.models import WorkflowDefinition
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
SCHEMA_PATH = "platform_sdk/schemas/manifest.schema.json"

# Short enough that waiting out several real intervals in a test takes
# well under a second of real wall-clock time — the identical
# reasoning tests/integration/test_lease_reap_loop.py's own
# _TEST_REAP_INTERVAL_SECONDS already establishes.
_TEST_WORKER_POLL_INTERVAL_SECONDS = 0.2

_DEFINITION_ID = "se.worker_loop_lifespan_test"
_DEFINITION_VERSION = "1.0.0"
_DEFINITION_PACK_ID = "se.software_engineering"


def _config(worker_poll_interval_seconds: float | None = None) -> PlatformConfig:
    return PlatformConfig(
        env="test",
        role="api",
        # Isolated from the real capability_packs/ tree — this file's
        # own scope is the worker loop, not pack discovery/health.
        capability_pack_dirs=[],
        manifest_schema_path=SCHEMA_PATH,
        worker_poll_interval_seconds=worker_poll_interval_seconds,
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


def _one_step_definition() -> WorkflowDefinition:
    return WorkflowDefinition.model_validate(
        {
            "id": _DEFINITION_ID,
            "name": "Worker Loop Lifespan Test",
            "description": "Deterministic — a human_approval step needs no agent/LLM.",
            "version": _DEFINITION_VERSION,
            "inputs": {"type": "object"},
            "outputs": {"type": "object"},
            "steps": [{"id": "approve", "type": "human_approval"}],
            "failureHandling": {"onError": "escalate"},
        }
    )


def _create_running_instance(database_url: str) -> str:
    """Registers the real definition and creates a real, running
    instance — built and used entirely within one ``asyncio.run()``
    call, the same dedicated-engine pattern
    ``test_lease_reap_loop.py`` follows to stay clear of the real,
    documented cross-event-loop hazard (the live app under test runs
    on ``TestClient``'s own background event loop)."""
    engine = build_engine(database_url)

    async def _run() -> str:
        try:
            await SqlWorkflowDefinitionCatalog(engine).register(
                definition=_one_step_definition(), pack_id=_DEFINITION_PACK_ID
            )
            repository = SqlWorkflowInstanceRepository(engine)
            created = await repository.create(
                definition_id=_DEFINITION_ID,
                definition_version=_DEFINITION_VERSION,
                inputs={},
                principal_id="user-42",
            )
            await repository.transition_to_running(
                workflow_id=created.workflow_id, reason="worker picked it up"
            )
            return created.workflow_id
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def _instance_status(database_url: str, workflow_id: str) -> WorkflowInstanceStatus | None:
    engine = build_engine(database_url)

    async def _run() -> WorkflowInstanceStatus | None:
        try:
            repository = SqlWorkflowInstanceRepository(engine)
            instance = await repository.get_instance(workflow_id)
            return instance.status if instance is not None else None
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def test_the_background_worker_loop_genuinely_discovers_and_completes_a_real_instance_on_its_own(
    database_url: str,
) -> None:
    """No manual ``tick_once()`` call anywhere in this test — the real
    background loop, started by ``_lifespan``, discovers this instance
    via the real catalog reader and drives it to completion on its
    own."""
    workflow_id = _create_running_instance(database_url)

    app = build_app(_config(worker_poll_interval_seconds=_TEST_WORKER_POLL_INTERVAL_SECONDS))

    with TestClient(app):
        # At least 2 real intervals — a one-step definition needs two
        # real advance() calls (the step itself, then the completing
        # call), and waiting well past two proves the loop is
        # genuinely still running, not a one-shot task that happened
        # to fire once.
        time.sleep(_TEST_WORKER_POLL_INTERVAL_SECONDS * 6)
        assert _instance_status(database_url, workflow_id) == WorkflowInstanceStatus.COMPLETED


def test_the_background_worker_loop_is_genuinely_cancelled_on_shutdown(
    database_url: str,
) -> None:
    app = build_app(_config(worker_poll_interval_seconds=_TEST_WORKER_POLL_INTERVAL_SECONDS))

    with TestClient(app):
        task = app.state.workflow_worker_task
        assert task is not None
        assert not task.done()

    # TestClient.__exit__ only returns once the real ASGI lifespan
    # shutdown sequence (_lifespan's own `finally` block, including
    # `await workflow_worker_task`) has genuinely completed — no
    # additional sleep or polling needed to observe the real outcome.
    assert task.done()
    assert task.cancelled()
