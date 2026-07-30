"""A small, bounded job that proactively reclaims expired workflow
leases — closing the one remaining reactive gap in the acquire → renew
→ release → reclaim cycle (data_model.md §4.4, workflow_engine.md
§7.1).

Before this module, an expired lease only got reclaimed as a side
effect of some other worker's next ``acquire()`` call on the same
instance (see :mod:`ai_os_kernel.workflow_engine.lease`'s reclaim
step). If nothing ever calls ``acquire()`` again for that instance —
for example, every worker capable of picking it up has crashed or
moved on — the stale lease row sits there indefinitely. It does no
structural harm (the guarded ``acquire``/``renew`` clauses never trust
an expired row), but it leaves the instance looking permanently
"leased" to anything inspecting lease state directly.

This reaper does exactly one thing: scan for ``workflow_leases`` rows
past ``expires_at`` and delete them, in one bounded pass, with
structured logging of what was reclaimed. :meth:`WorkflowLeaseReaper.reap_once`
itself is not a scheduler — nothing in it decides when or how often to
run.

**``run_reap_loop`` is that scheduler, now real (2026-07-30)** — the
"future worker process framework" this module's own docstring used to
defer to, applying the identical pattern
:func:`~ai_os_kernel.capability_manager.health_poller.run_health_polling_loop`
already proved for the Pack Health Collector: sleep for
``LEASE_REAP_INTERVAL_SECONDS``, call :meth:`reap_once`, repeat, until
cancelled. ``reap_once`` itself is reused completely unchanged — this
is scheduling only, never a second reclaim mechanism.

**The interval, decided here, for the first time.** Neither
``workflow_engine.md`` nor ``kernel_architecture.md`` names a specific
reap cadence — §7.1 documents the mechanism ("a lease that expires
without a heartbeat is reclaimed by another worker"), not a number.
Every real lease duration this codebase currently issues is 30 seconds
(``ai_os_kernel.bootstrap._DEMO_WORKFLOW_LEASE_DURATION_SECONDS`` and
``ai_os_kernel.workflow_engine.delivery_pipeline._LEASE_DURATION_SECONDS``,
both real, independently-arrived-at values) — ``LEASE_REAP_INTERVAL_SECONDS``
(15.0) is set to half that, so a genuinely crashed worker's lease is
proactively reclaimed within, on average, half a lease-duration of its
own expiry, rather than left to however long it takes for some other
worker's own ``acquire()`` call to happen to trigger a reactive
reclaim. ``LEASE_REAP_BATCH_LIMIT`` (100) matches
``ai_os_kernel.routes.workflows._MAX_LIST_LIMIT``, this codebase's own
already-established "reasonable batch size" convention, rather than
inventing a new one.
"""

from __future__ import annotations

import asyncio

from pydantic import BaseModel, ConfigDict

from ai_os_kernel.observability.logging import get_logger
from ai_os_kernel.workflow_engine.lease import WorkflowLease, WorkflowLeaseService

_logger = get_logger(__name__)

LEASE_REAP_INTERVAL_SECONDS = 15.0
LEASE_REAP_BATCH_LIMIT = 100


class LeaseReapResult(BaseModel):
    """What one :meth:`WorkflowLeaseReaper.reap_once` pass reclaimed."""

    model_config = ConfigDict(frozen=True)

    reaped: tuple[WorkflowLease, ...]

    @property
    def count(self) -> int:
        return len(self.reaped)


class WorkflowLeaseReaper:
    """Reclaims expired leases in bounded batches via the injected
    :class:`WorkflowLeaseService`.

    Adds no persistence logic of its own — it is purely a
    structured-logging wrapper over
    :meth:`WorkflowLeaseService.reap_expired`, matching how
    :class:`~ai_os_kernel.workflow_engine.advance_runner.WorkflowAdvanceRunner`
    composes existing services rather than introducing a new
    abstraction layer.
    """

    def __init__(self, lease_service: WorkflowLeaseService) -> None:
        self._lease_service = lease_service

    async def reap_once(self, *, limit: int) -> LeaseReapResult:
        """Reclaim up to ``limit`` expired leases in one bounded pass."""
        reaped = await self._lease_service.reap_expired(limit=limit)
        if reaped:
            _logger.info(
                "workflow_lease_reaper.reaped",
                count=len(reaped),
                workflow_ids=[lease.workflow_id for lease in reaped],
            )
        else:
            _logger.debug("workflow_lease_reaper.no_expired_leases", limit=limit)
        return LeaseReapResult(reaped=tuple(reaped))


async def run_reap_loop(
    *,
    reaper: WorkflowLeaseReaper,
    interval_seconds: float = LEASE_REAP_INTERVAL_SECONDS,
    limit: int = LEASE_REAP_BATCH_LIMIT,
) -> None:
    """Calls :meth:`WorkflowLeaseReaper.reap_once` every
    ``interval_seconds``, until cancelled — see this module's own
    docstring for the full design (why this interval, why it is
    genuinely new infrastructure, how it shuts down cleanly).

    Sleeps *before* each pass, not after, the identical reasoning
    :func:`~ai_os_kernel.capability_manager.health_poller.run_health_polling_loop`
    already established: nothing about lease reaping needs an
    immediate pass the instant this loop starts (a freshly-started
    Kernel has no leases yet to reclaim), so the first real pass lands
    one full interval later, not at t=0.

    A genuine reap-pass failure (a real database error) is logged and
    does not stop the loop — the identical per-pass resilience
    ``run_health_polling_loop`` already established for its own
    per-pack polling failures.
    """
    try:
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                result = await reaper.reap_once(limit=limit)
                if result.count:
                    _logger.info("lease_reaper.reap_loop_reclaimed", count=result.count)
            except Exception as exc:
                _logger.error("lease_reaper.reap_loop_failed", error=str(exc))
    except asyncio.CancelledError:
        _logger.info("lease_reaper.reap_loop_stopped")
        raise
