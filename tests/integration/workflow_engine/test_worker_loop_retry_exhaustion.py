"""Real proof that a permanently-failing step stops retrying
(``P02-S01-M05-T17``, risk register R-016) — against a real Postgres
container (ADR-0015, no mocking the database).

**The defect this closes.** ``WorkflowAdvanceRunner.run_once`` — the
method the worker loop actually calls — has no retry bound of its own. A
raised step exception propagated out, the lease was released, the
instance's ``workflow_instances.status`` was still ``running``, and the
very next poll rediscovered and retried it. Forever, for the life of the
Kernel process, with no persisted attempt count and no terminal state.
``error_handling_retry.md`` §2's "protect against infinite loops" goal
was genuinely violated on the one real, continuously-running production
path.

**Why these tests drive real ticks rather than calling a helper.** The
bound has to survive *across* polls — each ``tick_once`` is a fresh
``run_once`` with no memory of the last, which is precisely why the
in-memory counters the synchronous path uses could not work here. A test
that called the exhaustion check directly would prove nothing about that.
So every test below runs real ticks against a real database and asserts
on the persisted ``workflow_instances.status``.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.workflow_engine.advance_runner import WorkflowAdvanceRunner
from ai_os_kernel.workflow_engine.definition_catalog import SqlWorkflowDefinitionCatalog
from ai_os_kernel.workflow_engine.instance import WorkflowInstanceStatus
from ai_os_kernel.workflow_engine.lease import SqlWorkflowLeaseRepository, WorkflowLeaseService
from ai_os_kernel.workflow_engine.models import WorkflowDefinition, WorkflowStep
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from ai_os_kernel.workflow_engine.service import WorkflowInstanceService
from ai_os_kernel.workflow_engine.step_executor import DispatchingStepExecutor, NoOpStepExecutor
from ai_os_kernel.workflow_engine.worker_loop import DEFAULT_RETRY_POLICY, WorkflowWorkerLoop
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

_DEFINITION_ID = "se.retry_exhaustion_test"
_PACK_ID = "se.software_engineering"
_AGENT_ID = "se.software_engineering/analyst"
_STEP_ID = "always_fails"


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


class _AlwaysFailingStepExecutor:
    """A real ``StepExecutor`` whose step genuinely raises every time —
    a permanently-broken step, which is exactly the case that used to
    retry forever. Not a transient failure: no amount of retrying would
    ever succeed, so a bound is the only thing that can stop it."""

    def __init__(self) -> None:
        self.call_count = 0

    async def execute(
        self,
        step: WorkflowStep,
        *,
        workflow_id: str | None = None,
        principal_permissions: frozenset[str] | None = None,
        workflow_permissions: frozenset[str] | None = None,
    ) -> dict[str, Any]:
        self.call_count += 1
        raise RuntimeError("this step is permanently broken")


def _definition(*, version: str, max_attempts: int | None = None) -> WorkflowDefinition:
    """A one-step definition. ``max_attempts=None`` declares no
    ``retryPolicy`` at all — the case 2 of the 3 real definitions are in,
    and the one that used to retry forever."""
    body: dict[str, Any] = {
        "id": _DEFINITION_ID,
        "name": "Retry Exhaustion Test",
        "description": "test fixture",
        "version": version,
        "inputs": {"type": "object"},
        "outputs": {"type": "object"},
        "steps": [{"id": _STEP_ID, "type": "agent", "agentId": _AGENT_ID}],
        "failureHandling": {"onError": "halt"},
    }
    if max_attempts is not None:
        body["retryPolicy"] = {"maxAttempts": max_attempts, "maxDurationSeconds": 600.0}
    return WorkflowDefinition.model_validate(body)


async def _create_running_instance(engine: AsyncEngine, definition: WorkflowDefinition) -> str:
    await SqlWorkflowDefinitionCatalog(engine).register(definition=definition, pack_id=_PACK_ID)
    repository = SqlWorkflowInstanceRepository(engine)
    created = await repository.create(
        definition_id=definition.id,
        definition_version=definition.version,
        inputs={},
        principal_id="user-42",
    )
    await repository.transition_to_running(
        workflow_id=created.workflow_id, reason="worker picked it up"
    )
    return created.workflow_id


def _make_worker(engine: AsyncEngine, executor: _AlwaysFailingStepExecutor) -> WorkflowWorkerLoop:
    step_executor = DispatchingStepExecutor(
        agent_executor=executor,
        tool_executor=NoOpStepExecutor(),
        default_executor=NoOpStepExecutor(),
    )
    repository = SqlWorkflowInstanceRepository(engine)
    definition_catalog = SqlWorkflowDefinitionCatalog(engine)
    instance_service = WorkflowInstanceService(repository, step_executor, definition_catalog)
    return WorkflowWorkerLoop(
        repository=repository,
        advance_runner=WorkflowAdvanceRunner(
            instance_service, WorkflowLeaseService(SqlWorkflowLeaseRepository(engine))
        ),
        definition_catalog=definition_catalog,
        worker_id="worker-1",
    )


async def _status(engine: AsyncEngine, workflow_id: str) -> str:
    repository = SqlWorkflowInstanceRepository(engine)
    instance = await repository.get_instance(workflow_id)
    assert instance is not None
    return str(instance.status.value)


def test_a_permanently_failing_step_stops_retrying_and_is_persisted_failed(
    database_url: str,
) -> None:
    """R-016's core claim, proven end to end: the instance reaches the
    terminal `failed` state and stops being rediscovered.

    The definition declares no `retryPolicy`, so the platform default
    applies — this is the exact case that previously looped forever.
    """

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            definition = _definition(version="1.0.0")
            workflow_id = await _create_running_instance(engine, definition)
            executor = _AlwaysFailingStepExecutor()
            worker = _make_worker(engine, executor)

            # Tick until the default budget (2 attempts) is spent. A
            # generous ceiling: if the bound never engaged this would
            # keep finding work, which is the bug.
            for _ in range(10):
                await worker.tick_once(limit=100, lease_duration_seconds=60)
                if await _status(engine, workflow_id) != WorkflowInstanceStatus.RUNNING.value:
                    break

            assert await _status(engine, workflow_id) == WorkflowInstanceStatus.FAILED.value
            assert executor.call_count == DEFAULT_RETRY_POLICY.max_attempts, (
                "the step ran a different number of times than the budget allows"
            )
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_failed_instance_is_never_rediscovered_by_a_later_tick(database_url: str) -> None:
    """The property that actually ends the infinite loop: `failed` is
    terminal, and `list_runnable_instances` already filters on a
    non-terminal status, so further ticks find nothing to do."""

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            definition = _definition(version="1.0.1")
            workflow_id = await _create_running_instance(engine, definition)
            executor = _AlwaysFailingStepExecutor()
            worker = _make_worker(engine, executor)

            for _ in range(10):
                await worker.tick_once(limit=100, lease_duration_seconds=60)
                if await _status(engine, workflow_id) != WorkflowInstanceStatus.RUNNING.value:
                    break
            assert await _status(engine, workflow_id) == WorkflowInstanceStatus.FAILED.value

            calls_when_failed = executor.call_count
            for _ in range(3):
                result = await worker.tick_once(limit=100, lease_duration_seconds=60)
                assert workflow_id not in (
                    *result.advanced,
                    *result.failed,
                    *result.skipped_lease_unavailable,
                    *result.skipped_no_definition,
                )

            # The decisive assertion: the step was not invoked again. If
            # the instance were still discoverable this would keep rising
            # forever, which is precisely the pre-fix behaviour.
            assert executor.call_count == calls_when_failed

        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_definition_declaring_its_own_policy_overrides_the_platform_default(
    database_url: str,
) -> None:
    """The default is a fallback, not a cap: a definition that declares
    a larger budget genuinely gets it."""

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            declared_attempts = DEFAULT_RETRY_POLICY.max_attempts + 2
            definition = _definition(version="1.0.2", max_attempts=declared_attempts)
            workflow_id = await _create_running_instance(engine, definition)
            executor = _AlwaysFailingStepExecutor()
            worker = _make_worker(engine, executor)

            for _ in range(10):
                await worker.tick_once(limit=100, lease_duration_seconds=60)
                if await _status(engine, workflow_id) != WorkflowInstanceStatus.RUNNING.value:
                    break

            assert await _status(engine, workflow_id) == WorkflowInstanceStatus.FAILED.value
            assert executor.call_count == declared_attempts, (
                "the declared policy did not override the platform default"
            )
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_the_terminal_transition_is_recorded_in_the_event_log(database_url: str) -> None:
    """§4's "every retry and final failure must be observable": the
    transition is a real `state.transitioned` event carrying the reason,
    not only a log line that vanishes with the process."""

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            definition = _definition(version="1.0.3")
            workflow_id = await _create_running_instance(engine, definition)
            worker = _make_worker(engine, _AlwaysFailingStepExecutor())

            for _ in range(10):
                await worker.tick_once(limit=100, lease_duration_seconds=60)
                if await _status(engine, workflow_id) != WorkflowInstanceStatus.RUNNING.value:
                    break

            async with engine.connect() as connection:
                rows = (
                    (
                        await connection.execute(
                            sa.text(
                                "SELECT payload FROM workflow.workflow_events "
                                "WHERE workflow_id = :wid AND event_type = 'state.transitioned' "
                                "ORDER BY seq"
                            ),
                            {"wid": workflow_id},
                        )
                    )
                    .mappings()
                    .all()
                )

            failed_events = [
                r["payload"]
                for r in rows
                if r["payload"].get("newStatus") == WorkflowInstanceStatus.FAILED.value
            ]
            assert len(failed_events) == 1
            assert failed_events[0]["previousStatus"] == WorkflowInstanceStatus.RUNNING.value
            assert "exhausted its retry budget" in failed_events[0]["reason"]
        finally:
            await engine.dispose()

    asyncio.run(_run())
