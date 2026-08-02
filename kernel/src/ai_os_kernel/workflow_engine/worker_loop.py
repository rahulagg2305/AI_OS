"""Drives many workflow instances concurrently, not one call at a
time — `P02-S01-M05-T12`.

Everything real up to this step (`WorkflowInstanceService.advance`,
`WorkflowAdvanceRunner.run_once`/`run_to_completion`) operates on
exactly one, caller-named `workflow_id` per call — a real gap
`workflow_engine.md` §5.13 names as the still-unbuilt "Scheduler"
concern, distinct from the Lease Manager's own already-real proactive
reap loop (`lease_reaper.py`). This module is the first real instance
of that concern: it *discovers* which instances are runnable, not just
advances one a caller already knows about.

**A genuine, previously-missing discovery query, not a parameter added
to an existing one.** `WorkflowInstanceRepository.list_instances` (added
for api_architecture.md §9's paginated, newest-first "browse every
instance" listing) answers a different question than a worker loop
needs — "which `running` instances have no active lease claim right
now" — so `list_runnable_instances` (`repository.py`) is a new,
purpose-built query: `status = 'running'` and no unexpired
`workflow_leases` row, oldest-runnable-first (fairness, unlike the
listing endpoint's newest-first).

**Definition resolution now reads the real catalog (updated
2026-08-02, `P02-S01-M05-T14`) — no longer a composition-level
mapping.** `WorkflowDefinitionCatalog` used to be write-only (see
`definition_catalog.py`'s own docstring for the full history); this
step gave it a real `get(definition_id, version)` reader, reconstructed
losslessly from exactly what `register` already writes. Every
discovered instance's `(definition_id, definition_version)` is now
resolved by calling that reader directly — genuine, system-wide
discovery, not a dict a composition root has to hand-maintain in
advance. (The prior, T12-era design injected a plain
`{(definition_id, definition_version): WorkflowDefinition}` mapping,
the same `gate_sources`/`step_retry_targets` shape this codebase
established elsewhere; that shape remains correct for
`SubWorkflowStepExecutor`'s narrower, single-reference case, but could
never answer "any arbitrary already-running instance," which is this
module's whole point.)

**One step per instance per tick, not `run_to_completion` per
instance.** The whole point of "concurrently, not one per call" is
breadth across many instances, not depth on one — running one
instance to completion per tick would let a single long-running
instance monopolize a worker cycle while every other runnable instance
starves behind it. `tick_once` calls `WorkflowAdvanceRunner.run_once`
for every discovered instance via one real `asyncio.gather`, and an
instance still running is simply discovered again on the next tick —
the identical "repeat until done" shape `run_to_completion` already
uses for a single instance, just spread across many.

**A lost lease race is a normal outcome, not a failure.** Two workers
can discover the same runnable instance in the same tick (the
discovery read is deliberately unguarded — see `list_runnable_instances`'s
own docstring); whichever one's `WorkflowLeaseService.acquire` call
loses raises `WorkflowLeaseUnavailableError`, caught here and recorded
as a skip, never a tick failure. Any other exception for one instance
is logged and skipped too — the identical per-item resilience
`run_health_polling_loop`/`run_reap_loop` already established, so one
instance's genuine failure never stops the rest of the batch or the
loop itself. A resolved-to-`None` definition (a real row genuinely
absent from the catalog) is the identical kind of per-instance skip.

**`run_worker_loop` is the scheduler**, the identical
sleep-then-act-until-cancelled shape
:func:`~ai_os_kernel.workflow_engine.lease_reaper.run_reap_loop` (which
itself names :func:`~ai_os_kernel.capability_manager.health_poller.
run_health_polling_loop` as its own precedent) already proved twice —
and, as of this step, genuinely started in `_lifespan` alongside them
(`bootstrap.py`), the first of the four `P02-S01-M05-T09`–`T12`
capabilities to move from "proven, unused" to "proven, running."

**The interval/batch-size/lease-duration values, decided here.**
Neither `workflow_engine.md` nor any other document names a worker
poll cadence. `WORKER_LEASE_DURATION_SECONDS` (30) matches the two
already-real lease durations this codebase issues
(`bootstrap._DEMO_WORKFLOW_LEASE_DURATION_SECONDS`,
`delivery_pipeline._LEASE_DURATION_SECONDS`), not a new value.
`WORKER_BATCH_LIMIT` (100) matches `LEASE_REAP_BATCH_LIMIT`/
`routes.workflows._MAX_LIST_LIMIT`, this codebase's own established
"reasonable batch size." `WORKER_POLL_INTERVAL_SECONDS` (5.0) is new:
meaningfully shorter than `LEASE_REAP_INTERVAL_SECONDS` (15.0) so
genuinely runnable work is picked up well before a stale lease would
even be reaped, while still coarse enough not to hammer the database
with an empty-result query every event-loop tick.
"""

from __future__ import annotations

import asyncio
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ai_os_kernel.observability.logging import get_logger
from ai_os_kernel.workflow_engine.advance_runner import WorkflowAdvanceRunner
from ai_os_kernel.workflow_engine.definition_catalog import WorkflowDefinitionCatalog
from ai_os_kernel.workflow_engine.errors import WorkflowLeaseUnavailableError
from ai_os_kernel.workflow_engine.instance import WorkflowInstance
from ai_os_kernel.workflow_engine.repository import WorkflowInstanceRepository

_logger = get_logger(__name__)

WORKER_POLL_INTERVAL_SECONDS = 5.0
WORKER_BATCH_LIMIT = 100
WORKER_LEASE_DURATION_SECONDS = 30

_Outcome = Literal["advanced", "lease_unavailable", "no_definition", "failed"]


class WorkerTickResult(BaseModel):
    """What one :meth:`WorkflowWorkerLoop.tick_once` pass did, per
    discovered instance — structured, not re-derived from log lines."""

    model_config = ConfigDict(frozen=True)

    advanced: tuple[str, ...]
    skipped_lease_unavailable: tuple[str, ...]
    skipped_no_definition: tuple[str, ...]
    failed: tuple[str, ...]

    @property
    def discovered(self) -> int:
        return (
            len(self.advanced)
            + len(self.skipped_lease_unavailable)
            + len(self.skipped_no_definition)
            + len(self.failed)
        )


class WorkflowWorkerLoop:
    """Discovers runnable instances and advances each by exactly one
    step, concurrently, via the injected
    :class:`~ai_os_kernel.workflow_engine.advance_runner.WorkflowAdvanceRunner`
    — the same class a single-instance caller already uses, not a
    second execution mechanism. Resolves each instance's definition via
    the injected :class:`~ai_os_kernel.workflow_engine.
    definition_catalog.WorkflowDefinitionCatalog`'s own real `get` —
    genuine, system-wide discovery, not a caller-maintained mapping."""

    def __init__(
        self,
        *,
        repository: WorkflowInstanceRepository,
        advance_runner: WorkflowAdvanceRunner,
        definition_catalog: WorkflowDefinitionCatalog,
        worker_id: str,
    ) -> None:
        self._repository = repository
        self._advance_runner = advance_runner
        self._definition_catalog = definition_catalog
        self._worker_id = worker_id

    async def tick_once(self, *, limit: int, lease_duration_seconds: int) -> WorkerTickResult:
        """Discover up to ``limit`` runnable instances and attempt to
        advance each by one step, concurrently."""
        instances = await self._repository.list_runnable_instances(limit=limit)
        outcomes = await asyncio.gather(
            *(
                self._advance_one(instance, lease_duration_seconds=lease_duration_seconds)
                for instance in instances
            )
        )

        advanced: list[str] = []
        lease_unavailable: list[str] = []
        no_definition: list[str] = []
        failed: list[str] = []
        buckets: dict[_Outcome, list[str]] = {
            "advanced": advanced,
            "lease_unavailable": lease_unavailable,
            "no_definition": no_definition,
            "failed": failed,
        }
        for instance, outcome in zip(instances, outcomes, strict=True):
            buckets[outcome].append(instance.workflow_id)

        result = WorkerTickResult(
            advanced=tuple(advanced),
            skipped_lease_unavailable=tuple(lease_unavailable),
            skipped_no_definition=tuple(no_definition),
            failed=tuple(failed),
        )
        if result.discovered:
            _logger.info(
                "workflow_worker_loop.tick",
                discovered=result.discovered,
                advanced=len(result.advanced),
                skipped_lease_unavailable=len(result.skipped_lease_unavailable),
                skipped_no_definition=len(result.skipped_no_definition),
                failed=len(result.failed),
            )
        return result

    async def _advance_one(
        self, instance: WorkflowInstance, *, lease_duration_seconds: int
    ) -> _Outcome:
        definition = await self._definition_catalog.get(
            definition_id=instance.definition_id, version=instance.definition_version
        )
        if definition is None:
            _logger.warning(
                "workflow_worker_loop.no_definition",
                workflow_id=instance.workflow_id,
                definition_id=instance.definition_id,
                definition_version=instance.definition_version,
            )
            return "no_definition"
        try:
            await self._advance_runner.run_once(
                workflow_id=instance.workflow_id,
                definition=definition,
                worker_id=self._worker_id,
                lease_duration_seconds=lease_duration_seconds,
            )
            return "advanced"
        except WorkflowLeaseUnavailableError:
            return "lease_unavailable"
        except Exception as exc:
            _logger.error(
                "workflow_worker_loop.advance_failed",
                workflow_id=instance.workflow_id,
                error=str(exc),
            )
            return "failed"


async def run_worker_loop(
    *,
    worker: WorkflowWorkerLoop,
    interval_seconds: float = WORKER_POLL_INTERVAL_SECONDS,
    limit: int = WORKER_BATCH_LIMIT,
    lease_duration_seconds: int = WORKER_LEASE_DURATION_SECONDS,
) -> None:
    """Calls :meth:`WorkflowWorkerLoop.tick_once` every
    ``interval_seconds``, until cancelled — see this module's own
    docstring for the full design.

    Sleeps *before* each pass, not after, the identical reasoning
    :func:`~ai_os_kernel.workflow_engine.lease_reaper.run_reap_loop`
    already established: nothing needs an immediate pass the instant
    this loop starts.

    A genuine tick failure (unexpected, since :meth:`tick_once` already
    catches every per-instance exception itself — for example, the
    discovery query's own connection failing) is logged and does not
    stop the loop, the identical per-pass resilience
    ``run_reap_loop``/``run_health_polling_loop`` already established.
    """
    try:
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                await worker.tick_once(limit=limit, lease_duration_seconds=lease_duration_seconds)
            except Exception as exc:
                _logger.error("workflow_worker_loop.tick_failed", error=str(exc))
    except asyncio.CancelledError:
        _logger.info("workflow_worker_loop.stopped")
        raise
