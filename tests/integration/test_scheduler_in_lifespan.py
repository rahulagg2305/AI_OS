"""Real, end-to-end proof of the Scheduler's own deliverable
(workflow_engine.md §5.13, ``P02-S01-M05-T13``): the real background
loop (``ai_os_kernel.workflow_engine.scheduler.run_scheduler_loop``) —
applying the identical, already-proven pattern
``ai_os_kernel.workflow_engine.lease_reaper.run_reap_loop``/
``ai_os_kernel.workflow_engine.worker_loop.run_worker_loop`` established
— genuinely starts a real, directly-created ``created`` instance once
its own real, persisted ``scheduled_at`` is due, through the real, live
``_lifespan`` composition, with no manual ``tick_once()``/``start()``
call anywhere in this test, and is genuinely, cleanly stopped on
shutdown, not merely abandoned.

A ``human_approval``-typed step is used deliberately: it always
completes via ``NoOpStepExecutor`` regardless of which agent/tool
registry ``_lifespan`` happens to build (real or credential-degraded),
so this test needs no LLM credential and is fully deterministic — the
identical reasoning ``test_worker_loop_in_lifespan.py`` already
establishes.

Real Postgres via testcontainers (ADR-0015) — no mocking the database.
"""

import asyncio
import os
import time
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
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
# well under a second of real wall-clock time — the identical reasoning
# tests/integration/test_worker_loop_in_lifespan.py's own
# _TEST_WORKER_POLL_INTERVAL_SECONDS already establishes.
_TEST_SCHEDULER_INTERVAL_SECONDS = 0.2

_DEFINITION_ID = "se.scheduler_lifespan_test"
_DEFINITION_VERSION = "1.0.0"
_DEFINITION_PACK_ID = "se.software_engineering"


def _config(scheduler_interval_seconds: float | None = None) -> PlatformConfig:
    return PlatformConfig(
        env="test",
        role="api",
        # Isolated from the real capability_packs/ tree — this file's
        # own scope is the Scheduler, not pack discovery/health.
        capability_pack_dirs=[],
        manifest_schema_path=SCHEMA_PATH,
        scheduler_interval_seconds=scheduler_interval_seconds,
        # The worker loop (real default: 5s) is what drives a
        # scheduler-started instance from running -> completed —
        # also overridden here, the identical reasoning
        # test_worker_loop_in_lifespan.py's own _config already
        # establishes, so this test does not have to wait out the
        # real production cadence for the *second* half of the proof.
        worker_poll_interval_seconds=scheduler_interval_seconds,
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
            "name": "Scheduler Lifespan Test",
            "description": "Deterministic -- a human_approval step needs no agent/LLM.",
            "version": _DEFINITION_VERSION,
            "inputs": {"type": "object"},
            "outputs": {"type": "object"},
            "steps": [{"id": "approve", "type": "human_approval"}],
            "humanApprovalPoints": [
                {
                    "id": "approve",
                    "name": "Approve",
                    "description": "Approve something.",
                    "context": {},
                    "options": ["approve", "reject"],
                }
            ],
            "failureHandling": {"onError": "escalate"},
        }
    )


def _create_scheduled_instance(database_url: str, *, scheduled_at: datetime) -> str:
    """Registers the real definition and creates a real, ``created``
    (never started) instance with a real ``scheduled_at`` — built and
    used entirely within one ``asyncio.run()`` call, the same
    dedicated-engine pattern ``test_worker_loop_in_lifespan.py`` follows
    to stay clear of the real, documented cross-event-loop hazard."""
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
                scheduled_at=scheduled_at,
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


def test_the_background_scheduler_genuinely_starts_a_due_instance_on_its_own(
    database_url: str,
) -> None:
    """No manual ``start()``/``tick_once()`` call anywhere in this test
    — the real background loop, started by ``_lifespan``, discovers
    this ``created`` instance once its own real ``scheduled_at`` is
    genuinely due and starts it (then the real worker loop, also
    running in this same ``_lifespan``, drives it to completion — the
    identical composition ``test_worker_loop_in_lifespan.py`` already
    proves for that half)."""
    scheduled_at = datetime.now(UTC) + timedelta(seconds=_TEST_SCHEDULER_INTERVAL_SECONDS * 2)
    workflow_id = _create_scheduled_instance(database_url, scheduled_at=scheduled_at)
    assert _instance_status(database_url, workflow_id) == WorkflowInstanceStatus.CREATED

    app = build_app(_config(scheduler_interval_seconds=_TEST_SCHEDULER_INTERVAL_SECONDS))

    with TestClient(app):
        # At least several real intervals — genuinely due only after
        # ~2 intervals, then the worker loop needs its own real tick to
        # complete the single human_approval step.
        time.sleep(_TEST_SCHEDULER_INTERVAL_SECONDS * 20)
        assert _instance_status(database_url, workflow_id) == WorkflowInstanceStatus.COMPLETED


def test_a_not_yet_due_instance_is_left_created(database_url: str) -> None:
    """The real, negative control: an instance scheduled well into the
    future is genuinely left ``created`` — the Scheduler starts only
    what is actually due, never everything with a real ``scheduled_at``
    regardless of value."""
    far_future = datetime.now(UTC) + timedelta(hours=1)
    workflow_id = _create_scheduled_instance(database_url, scheduled_at=far_future)

    app = build_app(_config(scheduler_interval_seconds=_TEST_SCHEDULER_INTERVAL_SECONDS))

    with TestClient(app):
        time.sleep(_TEST_SCHEDULER_INTERVAL_SECONDS * 6)
        assert _instance_status(database_url, workflow_id) == WorkflowInstanceStatus.CREATED


def test_the_background_scheduler_is_genuinely_cancelled_on_shutdown(
    database_url: str,
) -> None:
    app = build_app(_config(scheduler_interval_seconds=_TEST_SCHEDULER_INTERVAL_SECONDS))

    with TestClient(app):
        task = app.state.scheduler_task
        assert task is not None
        assert not task.done()

    # TestClient.__exit__ only returns once the real ASGI lifespan
    # shutdown sequence (_lifespan's own `finally` block, including
    # `await scheduler_task`) has genuinely completed — no additional
    # sleep or polling needed to observe the real outcome.
    assert task.done()
    assert task.cancelled()
