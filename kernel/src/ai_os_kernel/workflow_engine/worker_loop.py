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
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ai_os_kernel.observability.logging import get_logger
from ai_os_kernel.workflow_engine.advance_runner import WorkflowAdvanceRunner
from ai_os_kernel.workflow_engine.definition_catalog import WorkflowDefinitionCatalog
from ai_os_kernel.workflow_engine.errors import WorkflowLeaseUnavailableError
from ai_os_kernel.workflow_engine.instance import WorkflowInstance
from ai_os_kernel.workflow_engine.models import RetryPolicy, WorkflowDefinition
from ai_os_kernel.workflow_engine.repository import WorkflowInstanceRepository

_logger = get_logger(__name__)

WORKER_POLL_INTERVAL_SECONDS = 5.0
WORKER_BATCH_LIMIT = 100
WORKER_LEASE_DURATION_SECONDS = 30

# The retry budget applied to a definition that declares no
# `retryPolicy` of its own (R-016, `P02-S01-M05-T17`).
#
# **Why a default exists at all.** `error_handling_retry.md` §2 requires
# the engine to "protect against infinite loops" and §4 that "retries
# must be bounded (maximum attempts + maximum duration)" — both, not
# either. `WorkflowDefinition.retry_policy` is optional, and 2 of the 3
# real definitions declare none, so honouring only declared policies
# would have left those two retrying forever: the violation R-016 names.
#
# **Why these numbers.** Chosen by the product owner rather than
# inferred, and deliberately mirroring the one real policy any
# definition actually declares today (`se.delivery_pipeline`:
# `maxAttempts: 2`, `maxDurationSeconds: 60.0`) instead of inventing a
# different figure. A retry is a real, billable LLM call, so the bound
# is also a cost ceiling. A definition that declares its own policy
# overrides this entirely — the same "real, decided policy constant with
# an explicit override" shape `WORKER_POLL_INTERVAL_SECONDS` above and
# `PlatformConfig`'s own interval fields already establish.
DEFAULT_RETRY_POLICY = RetryPolicy(max_attempts=2, max_duration_seconds=60.0)

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
    genuine, system-wide discovery, not a caller-maintained mapping.

    **One fixed step-executor composition for every instance it
    discovers.** ``advance_runner`` is built once, at construction, from
    one ``DispatchingStepExecutor`` — there is no per-definition
    composition routing. ``exclude_definition_ids`` (``P03-S03-M30-T06``)
    is the real, small escape hatch this implies: a definition whose own
    declared step types (a ``human_approval`` point, a pack-specific
    credential-gated ``agent`` registry) this loop's fixed composition
    cannot correctly execute must opt out of discovery entirely, rather
    than being silently mis-advanced. Empty by default — unchanged
    behaviour for every existing caller.
    """

    def __init__(
        self,
        *,
        repository: WorkflowInstanceRepository,
        advance_runner: WorkflowAdvanceRunner,
        definition_catalog: WorkflowDefinitionCatalog,
        worker_id: str,
        exclude_definition_ids: frozenset[str] = frozenset(),
    ) -> None:
        self._repository = repository
        self._advance_runner = advance_runner
        self._definition_catalog = definition_catalog
        self._worker_id = worker_id
        self._exclude_definition_ids = exclude_definition_ids

    async def tick_once(self, *, limit: int, lease_duration_seconds: int) -> WorkerTickResult:
        """Discover up to ``limit`` runnable instances and attempt to
        advance each by one step, concurrently."""
        instances = await self._repository.list_runnable_instances(
            limit=limit, exclude_definition_ids=self._exclude_definition_ids
        )
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
            await self._fail_if_retries_exhausted(instance, definition=definition, exc=exc)
            return "failed"

    async def _fail_if_retries_exhausted(
        self, instance: WorkflowInstance, *, definition: WorkflowDefinition, exc: Exception
    ) -> None:
        """End the retry loop when the budget is spent (R-016).

        Before this existed, the handler above logged and returned, the
        lease was released, the instance's status was still ``running``,
        and the very next poll rediscovered and retried it — forever, for
        the life of the Kernel process, with no persisted attempt count
        and no terminal state.

        The bound is evaluated exactly as
        ``WorkflowAdvanceRunner._maybe_retry_failed_step`` already
        evaluates it for the synchronous path — attempts *and* duration,
        exhausted when **either** is spent (``error_handling_retry.md``
        §4: "bounded (maximum attempts + maximum duration)"). The one
        real difference is where the counters live: that path keeps them
        in per-call dicts, which is useless here because every poll is a
        fresh call. These come from ``workflow_steps``, where
        ``record_failed_attempt`` has been writing them all along.

        Deliberately best-effort: a failure to record the terminal state
        is logged and swallowed, never raised. This runs inside the
        handler for an exception that already happened, and turning a
        bookkeeping problem into a second exception would lose the
        original failure and take down the tick for every other instance
        in the batch.
        """
        step_id = getattr(exc, "step_id", None)
        if not isinstance(step_id, str):
            # `WorkflowInstanceService.advance` attaches `step_id` to
            # every exception raised from a step. One without it did not
            # come from a step at all (a lease/database problem, say), so
            # there is no per-step budget to judge it against and no
            # persisted attempt row to count — retrying it is correct.
            return

        policy = definition.retry_policy or DEFAULT_RETRY_POLICY
        failure_count, first_failed_at = await self._repository.step_failure_stats(
            workflow_id=instance.workflow_id, step_name=step_id
        )
        if first_failed_at is None:
            return

        within_attempts = failure_count < policy.max_attempts
        elapsed = (datetime.now(UTC) - first_failed_at).total_seconds()
        within_duration = elapsed < policy.max_duration_seconds
        if within_attempts and within_duration:
            return

        reason = (
            f"step '{step_id}' exhausted its retry budget after {failure_count} "
            f"attempt(s) over {elapsed:.1f}s "
            f"(max_attempts={policy.max_attempts}, "
            f"max_duration_seconds={policy.max_duration_seconds})"
        )
        try:
            await self._repository.mark_failed(workflow_id=instance.workflow_id, reason=reason)
        except Exception as mark_exc:  # noqa: BLE001 - see the docstring above
            # A lost race with `cancel`, or any other write problem: the
            # instance is already terminal or unreachable, which is not
            # this loop's problem to solve.
            _logger.warning(
                "workflow_worker_loop.mark_failed_refused",
                workflow_id=instance.workflow_id,
                error=str(mark_exc),
            )
            return

        # §4's "Every retry and final failure must be observable" — a
        # distinct line, not folded into the generic advance_failed
        # above, because "failed again, will retry" and "permanently
        # failed, will never be retried" are different operational facts.
        _logger.error(
            "workflow_worker_loop.retry_exhausted",
            workflow_id=instance.workflow_id,
            step_id=step_id,
            failure_count=failure_count,
            elapsed_seconds=round(elapsed, 1),
            max_attempts=policy.max_attempts,
            max_duration_seconds=policy.max_duration_seconds,
            policy_source="definition" if definition.retry_policy else "platform_default",
        )


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
