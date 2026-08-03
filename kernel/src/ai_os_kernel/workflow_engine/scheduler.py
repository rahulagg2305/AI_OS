"""The Scheduler (workflow_engine.md §5.13, functional_requirements.md
§5.13: "Supports delayed and scheduled workflow starts") — the one real
component this document's own Implementation Status named as "not
built at all," distinct from both the Lease Manager's own reap
scheduling and the multi-instance worker loop, neither of which decides
*when* a not-yet-started instance should begin (``P02-S01-M05-T13``).

Applies the identical, already-proven pattern
:mod:`ai_os_kernel.workflow_engine.lease_reaper` established for the
Lease Reaper: a small, bounded per-tick pass
(:meth:`WorkflowScheduler.tick_once`) plus a real, continuously-running
loop (:func:`run_scheduler_loop`) that calls it on an interval, until
cancelled. Nothing here is a second "start a workflow" mechanism —
:meth:`WorkflowScheduler.tick_once` reuses
:meth:`~ai_os_kernel.workflow_engine.repository.WorkflowInstanceRepository.
transition_to_running` exactly as any other real caller
(:meth:`~ai_os_kernel.workflow_engine.service.WorkflowInstanceService.start`)
already does.

**A ``created`` instance with a real, due ``scheduled_at``
(``WorkflowInstanceRepository.create``'s own new, nullable column,
migration ``0032_scheduled_at``) is what this component discovers and
starts** — an instance created without one (every caller before this
step) is entirely unaffected: it still requires some other, explicit
:meth:`~ai_os_kernel.workflow_engine.service.WorkflowInstanceService.start`
call, exactly as before this module existed.

**Racing another caller is a real, expected case, not an error.**
:meth:`~ai_os_kernel.workflow_engine.repository.WorkflowInstanceRepository.
transition_to_running`'s own ``WHERE status = 'created'`` clause is one
atomic check-and-transition; if some other caller (a second scheduler
tick after a slow first one, a real HTTP caller starting the same
instance manually) already moved it to ``running`` first, this raises
:class:`~ai_os_kernel.workflow_engine.errors.WorkflowInvalidTransitionError`,
which this module treats as "someone else already started it" — a
skip, never a per-tick failure.
"""

from __future__ import annotations

import asyncio

from pydantic import BaseModel, ConfigDict

from ai_os_kernel.observability.logging import get_logger
from ai_os_kernel.workflow_engine.errors import WorkflowInvalidTransitionError
from ai_os_kernel.workflow_engine.repository import WorkflowInstanceRepository

_logger = get_logger(__name__)

# No document names a specific scheduling cadence (workflow_engine.md
# §5.13 documents the mechanism, not a number) — reusing the identical,
# already-decided cadence
# ai_os_kernel.workflow_engine.worker_loop.WORKER_POLL_INTERVAL_SECONDS
# uses for its own "discover eligible instances, act, repeat" loop,
# rather than inventing a second, arbitrary number for a structurally
# identical kind of decision.
SCHEDULER_INTERVAL_SECONDS = 5.0
# Matches ai_os_kernel.workflow_engine.lease_reaper.LEASE_REAP_BATCH_LIMIT /
# ai_os_kernel.routes.workflows._MAX_LIST_LIMIT, this codebase's own
# already-established "reasonable batch size" convention.
SCHEDULER_BATCH_LIMIT = 100


class WorkflowSchedulerResult(BaseModel):
    """What one :meth:`WorkflowScheduler.tick_once` pass started."""

    model_config = ConfigDict(frozen=True)

    started: tuple[str, ...]

    @property
    def count(self) -> int:
        return len(self.started)


class WorkflowScheduler:
    """Starts due, scheduled ``created`` instances in bounded batches
    via the injected :class:`WorkflowInstanceRepository`.

    Adds no persistence logic of its own — purely a structured-logging
    wrapper over :meth:`WorkflowInstanceRepository.list_startable_instances`/
    :meth:`~WorkflowInstanceRepository.transition_to_running`, the
    identical shape :class:`~ai_os_kernel.workflow_engine.lease_reaper.
    WorkflowLeaseReaper` already establishes over its own injected
    :class:`~ai_os_kernel.workflow_engine.lease.WorkflowLeaseService`.
    """

    def __init__(self, repository: WorkflowInstanceRepository) -> None:
        self._repository = repository

    async def tick_once(self, *, limit: int) -> WorkflowSchedulerResult:
        """Start up to ``limit`` due, scheduled instances in one
        bounded pass."""
        due = await self._repository.list_startable_instances(limit=limit)
        started: list[str] = []
        for instance in due:
            try:
                await self._repository.transition_to_running(
                    workflow_id=instance.workflow_id,
                    reason="scheduled start",
                )
                started.append(instance.workflow_id)
            except WorkflowInvalidTransitionError:
                # Lost a race with another caller that already started
                # this instance first — see this module's own
                # docstring for why that is a real, expected skip, not
                # a per-tick failure.
                continue
        if started:
            _logger.info("workflow_scheduler.started", count=len(started), workflow_ids=started)
        else:
            _logger.debug("workflow_scheduler.no_due_instances", limit=limit)
        return WorkflowSchedulerResult(started=tuple(started))


async def run_scheduler_loop(
    *,
    scheduler: WorkflowScheduler,
    interval_seconds: float = SCHEDULER_INTERVAL_SECONDS,
    limit: int = SCHEDULER_BATCH_LIMIT,
) -> None:
    """Calls :meth:`WorkflowScheduler.tick_once` every
    ``interval_seconds``, until cancelled — see this module's own
    docstring for the full design.

    Sleeps *before* each pass, not after, the identical reasoning
    :func:`~ai_os_kernel.workflow_engine.lease_reaper.run_reap_loop`
    already established: nothing about a freshly-started Kernel needs
    an immediate pass at t=0.

    A genuine per-tick failure (a real database error) is logged and
    does not stop the loop — the identical per-pass resilience
    :func:`~ai_os_kernel.capability_manager.health_poller.
    run_health_polling_loop`/:func:`run_reap_loop` already establish.
    """
    try:
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                result = await scheduler.tick_once(limit=limit)
                if result.count:
                    _logger.info("workflow_scheduler.loop_started", count=result.count)
            except Exception as exc:
                _logger.error("workflow_scheduler.loop_tick_failed", error=str(exc))
    except asyncio.CancelledError:
        _logger.info("workflow_scheduler.loop_stopped")
        raise
