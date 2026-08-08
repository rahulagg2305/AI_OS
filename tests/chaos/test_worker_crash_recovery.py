"""Chaos test 1 of 2 (``P07-S03-M42-T01``): kill a worker mid-task,
prove the running system recovers on its own — not merely that a
lease row gets deleted.

**A worker "crash" is genuinely simulated, not merely asserted.** A
real lease is acquired directly (the identical action
``WorkflowAdvanceRunner`` takes at the start of a real tick) and then
simply abandoned — no release, no renewal, no further action from
that worker at all, exactly what a process that dies mid-step actually
does. The proof has two real, separate legs, both required: (1)
:class:`~ai_os_kernel.workflow_engine.lease_reaper.WorkflowLeaseReaper`
genuinely reclaims the abandoned lease once it expires — the
proactive-reclaim mechanism `lease_reaper.py`'s own docstring
describes; (2) a *second*, independent worker, with no special
knowledge that anything went wrong, genuinely picks the now-reclaimed
instance back up and drives it to real completion — the system
recovering, not only its bookkeeping.

Reuses `tests/integration/workflow_engine/test_worker_loop_execution.py`'s
own real fixtures (`_create_running_instance`, `_make_worker`) rather
than a second, duplicate copy — the identical real Postgres, real
`WorkflowWorkerLoop` machinery that file's own docstring already
establishes.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.workflow_engine.instance import WorkflowInstanceStatus
from ai_os_kernel.workflow_engine.lease import SqlWorkflowLeaseRepository, WorkflowLeaseService
from ai_os_kernel.workflow_engine.lease_reaper import WorkflowLeaseReaper
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from tests.integration._postgres_fixture import postgres_container
from tests.integration.workflow_engine.test_worker_loop_execution import (
    _create_running_instance,
    _make_worker,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
_CRASHED_WORKER_ID = "worker-that-crashed"
_RECOVERING_WORKER_ID = "worker-that-recovers-it"
# Short enough that a real test waits well under a second for a
# genuine expiry, long enough that the reaper's own read-then-delete
# pass cannot race the acquisition itself.
_SHORT_LEASE_DURATION_SECONDS = 1


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


def test_a_crashed_workers_abandoned_lease_is_reclaimed_and_a_second_worker_finishes_the_work(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine: AsyncEngine = build_engine(database_url)
        try:
            instance_repository = SqlWorkflowInstanceRepository(engine)
            lease_repository = SqlWorkflowLeaseRepository(engine)
            lease_service = WorkflowLeaseService(lease_repository)
            reaper = WorkflowLeaseReaper(lease_service)

            workflow_id = await _create_running_instance(engine)

            # The crash: a real worker acquires the lease, then simply
            # never does anything else — no release, no renew, no
            # advance. Nothing here is a fake or a shortcut; this is
            # the exact same real `acquire()` a genuine tick makes.
            await lease_repository.acquire(
                workflow_id=workflow_id,
                worker_id=_CRASHED_WORKER_ID,
                lease_duration_seconds=_SHORT_LEASE_DURATION_SECONDS,
            )

            # Before it expires, the instance is genuinely unavailable
            # to any other worker — proving the "crash" really held a
            # real lease, not a no-op.
            recovering_worker_early = _make_worker(
                engine, step_duration=0.01, worker_id=_RECOVERING_WORKER_ID
            )
            early_result = await recovering_worker_early.tick_once(
                limit=100, lease_duration_seconds=60
            )
            assert workflow_id not in early_result.advanced

            # Real wall-clock expiry — no time-mocking; the reaper's
            # own `reap_once` reads a real `expires_at` column against
            # a real `now()`.
            await asyncio.sleep(_SHORT_LEASE_DURATION_SECONDS + 0.5)

            # Recovery leg 1: the abandoned lease is genuinely
            # reclaimed by the proactive reaper — not by luck, not by
            # another worker's own `acquire()` happening to race it.
            reap_result = await reaper.reap_once(limit=100)
            assert workflow_id in [lease.workflow_id for lease in reap_result.reaped]

            # Recovery leg 2: a second, independent worker — with no
            # special knowledge the first one crashed — genuinely picks
            # the now-free instance back up and finishes it for real.
            recovering_worker = _make_worker(
                engine, step_duration=0.01, worker_id=_RECOVERING_WORKER_ID
            )
            for _ in range(10):
                await recovering_worker.tick_once(limit=100, lease_duration_seconds=60)
                instance = await instance_repository.get_instance(workflow_id)
                assert instance is not None
                if instance.status == WorkflowInstanceStatus.COMPLETED:
                    break
            else:
                pytest.fail(
                    f"instance {workflow_id} never reached COMPLETED after real recovery ticks"
                )

            final_instance = await instance_repository.get_instance(workflow_id)
            assert final_instance is not None
            assert final_instance.status == WorkflowInstanceStatus.COMPLETED
        finally:
            await engine.dispose()

    asyncio.run(_run())
