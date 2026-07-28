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
structured logging of what was reclaimed. It is not a scheduler —
nothing here decides when or how often to run. A future worker process
framework would call :meth:`WorkflowLeaseReaper.reap_once` on a timer
or in a loop, deciding scheduling for itself.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from ai_os_kernel.observability.logging import get_logger
from ai_os_kernel.workflow_engine.lease import WorkflowLease, WorkflowLeaseService

_logger = get_logger(__name__)


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
