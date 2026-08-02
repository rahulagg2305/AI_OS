"""Real, genuine multi-instance concurrent advancement against a real
Postgres container (ADR-0015 — no mocking the database). Proves
``WorkflowWorkerLoop`` (``P02-S01-M05-T12``, updated ``P02-S01-M05-T14``
for real catalog-backed definition resolution) discovers several real,
running instances and advances every one of them within a single
tick, genuinely concurrently — real wall-clock timing, not sequential
execution disguised as concurrent, the identical proof technique
``tests/unit/kernel/workflow_engine/test_parallel_step_executor.py``
already established for concurrent *branches*, applied here across
concurrent *instances* instead; that an instance already leased by
another worker is a genuine skip, not a tick failure; that
``run_worker_loop`` genuinely drives a real instance to completion
across real, separate wall-clock ticks with no manual ``tick_once()``
call anywhere in the test, then stops cleanly on cancellation; and that
definition resolution genuinely round-trips through
``SqlWorkflowDefinitionCatalog`` — a real ``register()`` write, read
back by the worker loop's own real ``get()`` call, never a
composition-injected mapping.
"""

import asyncio
import os
import time
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
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
from ai_os_kernel.workflow_engine.worker_loop import WorkflowWorkerLoop, run_worker_loop
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

# Deliberately its own id, distinct from `se.product_creation` — this
# package's own `conftest.py` autouse fixture already registers that
# id/version pair with an *empty* placeholder graph (just enough to
# satisfy the FK, never meant to be read back). These tests, unlike
# every other test in this package, genuinely read the catalog row
# back through `WorkflowWorkerLoop`'s own real `get()` call, so they
# need their own, real, fully-populated registration instead.
_DEFINITION_ID = "se.worker_loop_catalog_test"
_DEFINITION_VERSION = "1.0.0"
_PACK_ID = "se.software_engineering"
_AGENT_ID = "se.software_engineering/analyst"


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


class _SleepingStepExecutor:
    """A real ``StepExecutor`` whose ``execute()`` genuinely awaits
    ``asyncio.sleep`` before succeeding — used so concurrency across
    real instances is proven by real wall-clock timing against a real
    event loop, never simulated with an executor that resolves
    instantly."""

    def __init__(self, duration: float) -> None:
        self._duration = duration

    async def execute(
        self, step: WorkflowStep, *, workflow_id: str | None = None
    ) -> dict[str, Any]:
        await asyncio.sleep(self._duration)
        return {"status": "ok"}


def _one_step_definition() -> WorkflowDefinition:
    return WorkflowDefinition.model_validate(
        {
            "id": _DEFINITION_ID,
            "name": "Worker Loop Test",
            "description": "test fixture",
            "version": _DEFINITION_VERSION,
            "inputs": {"type": "object"},
            "outputs": {"type": "object"},
            "steps": [{"id": "do_work", "type": "agent", "agentId": _AGENT_ID}],
            "failureHandling": {"onError": "escalate"},
        }
    )


async def _create_running_instance(engine: AsyncEngine) -> str:
    """Registers the real definition (idempotent — `ON CONFLICT DO
    NOTHING`, and this file's own content for `(definition_id,
    version)` never varies) before creating and starting the instance
    that references it, the identical ordering
    `WorkflowInstanceService.create_instance` already establishes."""
    await SqlWorkflowDefinitionCatalog(engine).register(
        definition=_one_step_definition(), pack_id=_PACK_ID
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


def _make_worker(
    engine: AsyncEngine, *, step_duration: float, worker_id: str = "worker-1"
) -> WorkflowWorkerLoop:
    step_executor = DispatchingStepExecutor(
        agent_executor=_SleepingStepExecutor(step_duration),
        tool_executor=NoOpStepExecutor(),
        default_executor=NoOpStepExecutor(),
    )
    repository = SqlWorkflowInstanceRepository(engine)
    definition_catalog = SqlWorkflowDefinitionCatalog(engine)
    instance_service = WorkflowInstanceService(repository, step_executor, definition_catalog)
    lease_service = WorkflowLeaseService(SqlWorkflowLeaseRepository(engine))
    advance_runner = WorkflowAdvanceRunner(instance_service, lease_service)
    return WorkflowWorkerLoop(
        repository=repository,
        advance_runner=advance_runner,
        definition_catalog=definition_catalog,
        worker_id=worker_id,
    )


def test_a_single_tick_genuinely_advances_multiple_real_instances_concurrently(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            repository = SqlWorkflowInstanceRepository(engine)
            workflow_ids = [await _create_running_instance(engine) for _ in range(3)]
            worker = _make_worker(engine, step_duration=0.2)

            started = time.monotonic()
            result = await worker.tick_once(limit=100, lease_duration_seconds=60)
            elapsed = time.monotonic() - started

            assert set(workflow_ids) <= set(result.advanced)
            assert elapsed < 0.4  # well under 3 x 0.2s = 0.6s a sequential tick would take
            assert elapsed >= 0.2  # sanity: real work genuinely happened

            for workflow_id in workflow_ids:
                instance = await repository.get_instance(workflow_id)
                assert instance is not None
                assert instance.current_step_id == "do_work"
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_an_instance_already_leased_by_another_worker_is_not_even_discovered(
    database_url: str,
) -> None:
    """`list_runnable_instances` filters at the SQL level, before any
    `tick_once` call attempts an `acquire` at all — a held, unexpired
    lease means the instance never enters `instances`/any outcome
    bucket in the first place, not that it is discovered and then
    rejected."""

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            repository = SqlWorkflowInstanceRepository(engine)
            held_workflow_id = await _create_running_instance(engine)
            free_workflow_id = await _create_running_instance(engine)

            lease_repository = SqlWorkflowLeaseRepository(engine)
            await lease_repository.acquire(
                workflow_id=held_workflow_id,
                worker_id="another-worker",
                lease_duration_seconds=60,
            )

            worker = _make_worker(engine, step_duration=0.01)
            result = await worker.tick_once(limit=100, lease_duration_seconds=60)

            assert held_workflow_id not in result.advanced
            assert held_workflow_id not in result.skipped_lease_unavailable
            assert free_workflow_id in result.advanced

            held_instance = await repository.get_instance(held_workflow_id)
            assert held_instance is not None
            assert held_instance.current_step_id is None  # untouched, never advanced

            await lease_repository.release(workflow_id=held_workflow_id, worker_id="another-worker")
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_two_workers_racing_for_the_same_freshly_runnable_instance_have_exactly_one_winner(
    database_url: str,
) -> None:
    """Unlike the discovery-level exclusion above, this is a genuine
    race: both workers discover the *same*, still-unleased instance in
    the same tick (the discovery read is deliberately unguarded — see
    `list_runnable_instances`'s own docstring), so only their two real,
    concurrent `acquire()` calls decide the winner — proving
    `WorkflowLeaseUnavailableError` is genuinely caught and reported as
    a skip, not merely a code path nothing ever exercises."""

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            repository = SqlWorkflowInstanceRepository(engine)
            workflow_id = await _create_running_instance(engine)

            worker_a = _make_worker(engine, step_duration=0.05, worker_id="worker-a")
            worker_b = _make_worker(engine, step_duration=0.05, worker_id="worker-b")

            result_a, result_b = await asyncio.gather(
                worker_a.tick_once(limit=100, lease_duration_seconds=60),
                worker_b.tick_once(limit=100, lease_duration_seconds=60),
            )

            advanced_by = [
                worker
                for worker, result in (("a", result_a), ("b", result_b))
                if workflow_id in result.advanced
            ]
            skipped_by = [
                worker
                for worker, result in (("a", result_a), ("b", result_b))
                if workflow_id in result.skipped_lease_unavailable
            ]
            assert len(advanced_by) == 1
            assert len(skipped_by) == 1

            instance = await repository.get_instance(workflow_id)
            assert instance is not None
            assert instance.current_step_id == "do_work"
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_run_worker_loop_genuinely_drives_a_real_instance_to_completion_on_its_own(
    database_url: str,
) -> None:
    """No manual ``tick_once()`` call anywhere in this test — the real
    background loop, across real, separate wall-clock ticks, does it,
    then stops genuinely on cancellation, not merely abandoned."""

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            repository = SqlWorkflowInstanceRepository(engine)
            workflow_id = await _create_running_instance(engine)
            worker = _make_worker(engine, step_duration=0.01)

            task = asyncio.create_task(
                run_worker_loop(
                    worker=worker, interval_seconds=0.05, limit=100, lease_duration_seconds=60
                )
            )
            try:
                # A one-step definition needs two real ticks (do_work,
                # then the completing tick) — well within several 0.05s
                # polls of real wall-clock time.
                await asyncio.sleep(0.05 * 8)
                instance = await repository.get_instance(workflow_id)
                assert instance is not None
                assert instance.status == WorkflowInstanceStatus.COMPLETED
            finally:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_definition_resolution_genuinely_round_trips_through_the_real_catalog(
    database_url: str,
) -> None:
    """The core proof of the new discovery mechanism: nothing here
    injects a `{(id, version): WorkflowDefinition}` mapping — the
    worker loop's own `_advance_one` calls the real
    `SqlWorkflowDefinitionCatalog.get()`, which reconstructs the
    definition from exactly the columns a real, prior `register()` call
    wrote. If that round-trip lost or corrupted anything, the step
    would fail to resolve `agentId` correctly and the instance would
    never reach `do_work`."""

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            repository = SqlWorkflowInstanceRepository(engine)
            definition_catalog = SqlWorkflowDefinitionCatalog(engine)
            workflow_id = await _create_running_instance(engine)

            resolved = await definition_catalog.get(
                definition_id=_DEFINITION_ID, version=_DEFINITION_VERSION
            )
            assert resolved is not None
            assert resolved == _one_step_definition()

            worker = _make_worker(engine, step_duration=0.01)
            result = await worker.tick_once(limit=100, lease_duration_seconds=60)

            assert workflow_id in result.advanced
            instance = await repository.get_instance(workflow_id)
            assert instance is not None
            assert instance.current_step_id == "do_work"
        finally:
            await engine.dispose()

    asyncio.run(_run())
