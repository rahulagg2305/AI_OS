"""Composes lease acquisition with one
:meth:`WorkflowInstanceService.advance` call and lease release — turning
the acquire → advance → release pattern into one reusable,
production-usable unit — and a bounded loop over that unit for driving
a single workflow instance to completion.

Not a worker loop, not a scheduler: everything here operates on exactly
one workflow instance, synchronously, in the calling coroutine. A
future multi-instance worker loop would call
:meth:`WorkflowAdvanceRunner.run_to_completion` (or `run_once`)
repeatedly across many instances, deciding for itself how to schedule
and poll for work — that loop, and any renewal decision for a single
long-running step, are separate, later work (out of scope here).
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from ai_os_kernel.workflow_engine.errors import QualityGateFailedError
from ai_os_kernel.workflow_engine.input_validation import validate_max_iterations
from ai_os_kernel.workflow_engine.instance import WorkflowInstance, WorkflowInstanceStatus
from ai_os_kernel.workflow_engine.lease import WorkflowLeaseService
from ai_os_kernel.workflow_engine.models import WorkflowDefinition
from ai_os_kernel.workflow_engine.service import WorkflowInstanceService


class WorkflowRunOutcome(StrEnum):
    """How a :meth:`WorkflowAdvanceRunner.run_to_completion` call ended."""

    COMPLETED = "completed"
    MAX_ITERATIONS_REACHED = "max_iterations_reached"
    FAILED = "failed"


class WorkflowRunResult(BaseModel):
    """A structured summary of one `run_to_completion` call — never
    raised, always returned, so a caller can inspect what happened
    without wrapping every call in its own `try`/`except`."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    workflow_id: str
    outcome: WorkflowRunOutcome
    iterations: int
    last_instance: WorkflowInstance | None
    error: BaseException | None = None


class WorkflowAdvanceRunner:
    """Claims a `running` instance's lease, advances it by exactly one
    step (or to completion), and releases the lease.

    Release always runs, via ``finally`` — whether ``advance()``
    succeeds or raises. If lease acquisition itself fails (for example,
    another worker already holds the lease), ``advance()`` is never
    called and there is nothing to release.
    """

    def __init__(
        self,
        instance_service: WorkflowInstanceService,
        lease_service: WorkflowLeaseService,
    ) -> None:
        self._instance_service = instance_service
        self._lease_service = lease_service

    async def run_once(
        self,
        *,
        workflow_id: str,
        definition: WorkflowDefinition,
        worker_id: str,
        lease_duration_seconds: int,
    ) -> WorkflowInstance:
        await self._lease_service.acquire(
            workflow_id=workflow_id,
            worker_id=worker_id,
            lease_duration_seconds=lease_duration_seconds,
        )
        try:
            return await self._instance_service.advance(
                workflow_id=workflow_id, definition=definition
            )
        finally:
            await self._lease_service.release(workflow_id=workflow_id, worker_id=worker_id)

    async def run_to_completion(
        self,
        *,
        workflow_id: str,
        definition: WorkflowDefinition,
        worker_id: str,
        lease_duration_seconds: int,
        max_iterations: int,
        gate_retry_targets: Mapping[str, str] | None = None,
    ) -> WorkflowRunResult:
        """Call :meth:`run_once` repeatedly for this one instance until
        it reaches `completed`, ``max_iterations`` calls have been made
        without completing, or a call raises.

        Unlike `run_once`, this method never raises for a workflow-level
        failure — it is a deliberate boundary that converts whatever
        `run_once` raises into a structured, inspectable
        :class:`WorkflowRunResult` instead of propagating a stack trace.
        (``WorkflowInputValidationError`` from an invalid
        ``max_iterations`` is the one exception: a caller programming
        error, checked before the loop starts, not a workflow-runtime
        outcome.)

        **Bounded quality-gate retry (added 2026-07-30).** ``gate_retry_targets``
        (``{gate_step_id: retry_from_step_id}``, defaulted ``None`` — every
        existing caller keeps the exact prior behaviour) is composition-level
        config, the identical shape :mod:`~ai_os_kernel.workflow_engine.
        quality_gate`'s own ``gate_sources`` already establishes: which step
        a failed gate should retry from is pipeline-specific knowledge, not
        a field this generic runner invents. When a :class:`~ai_os_kernel.
        workflow_engine.errors.QualityGateFailedError` is caught **and**
        its ``gate_step_id`` has a configured target **and**
        ``definition.retry_policy`` is declared, this method calls
        :meth:`~ai_os_kernel.workflow_engine.service.WorkflowInstanceService.
        retry_after_gate_failure` (resetting ``current_step_id`` so the next
        iteration genuinely re-executes from ``retry_from_step_id``) instead
        of returning ``FAILED`` immediately — bounded on *both* axes
        ``error_handling_retry.md`` §4 requires ("maximum attempts +
        maximum duration"): a per-gate attempt counter checked against
        ``retry_policy.max_attempts``, and a per-gate deadline
        (``time.monotonic()`` at the first failure of this gate, plus
        ``retry_policy.max_duration_seconds``) checked against the current
        time. Either bound reached, or no retry configured at all, falls
        through to the exact same ``FAILED`` result this method already
        returned before this feature existed — genuinely bounded, never an
        unconditional or unlimited retry. This is deliberately scoped to
        *gate* failures only; any other exception still fails the run
        immediately, exactly as before (general step-level retry per any
        error category remains future work, error_handling_retry.md §4's
        own still-open item).
        """
        validate_max_iterations(max_iterations)
        gate_retry_targets = gate_retry_targets or {}
        gate_failure_counts: dict[str, int] = {}
        gate_retry_deadlines: dict[str, float] = {}

        instance: WorkflowInstance | None = None
        for iteration in range(1, max_iterations + 1):
            try:
                instance = await self.run_once(
                    workflow_id=workflow_id,
                    definition=definition,
                    worker_id=worker_id,
                    lease_duration_seconds=lease_duration_seconds,
                )
            except QualityGateFailedError as exc:
                retried_instance = await self._maybe_retry_gate_failure(
                    exc,
                    workflow_id=workflow_id,
                    definition=definition,
                    gate_retry_targets=gate_retry_targets,
                    gate_failure_counts=gate_failure_counts,
                    gate_retry_deadlines=gate_retry_deadlines,
                )
                if retried_instance is None:
                    return WorkflowRunResult(
                        workflow_id=workflow_id,
                        outcome=WorkflowRunOutcome.FAILED,
                        iterations=iteration,
                        last_instance=instance,
                        error=exc,
                    )
                instance = retried_instance
                continue
            except Exception as exc:  # deliberate boundary, see docstring above
                return WorkflowRunResult(
                    workflow_id=workflow_id,
                    outcome=WorkflowRunOutcome.FAILED,
                    iterations=iteration,
                    last_instance=instance,
                    error=exc,
                )

            if instance.status is WorkflowInstanceStatus.COMPLETED:
                return WorkflowRunResult(
                    workflow_id=workflow_id,
                    outcome=WorkflowRunOutcome.COMPLETED,
                    iterations=iteration,
                    last_instance=instance,
                )

        return WorkflowRunResult(
            workflow_id=workflow_id,
            outcome=WorkflowRunOutcome.MAX_ITERATIONS_REACHED,
            iterations=max_iterations,
            last_instance=instance,
        )

    async def _maybe_retry_gate_failure(
        self,
        exc: QualityGateFailedError,
        *,
        workflow_id: str,
        definition: WorkflowDefinition,
        gate_retry_targets: Mapping[str, str],
        gate_failure_counts: dict[str, int],
        gate_retry_deadlines: dict[str, float],
    ) -> WorkflowInstance | None:
        """Returns the reset instance when a bounded retry genuinely
        applies; ``None`` when it does not (no target configured for
        this gate, no ``retry_policy`` declared, or a bound is already
        exhausted) — the caller falls through to ``FAILED`` in that
        case, unchanged from this feature's own "before" behaviour."""
        retry_from_step_id = gate_retry_targets.get(exc.gate_step_id)
        retry_policy = definition.retry_policy
        if retry_from_step_id is None or retry_policy is None:
            return None

        gate_failure_counts[exc.gate_step_id] = gate_failure_counts.get(exc.gate_step_id, 0) + 1
        failure_count = gate_failure_counts[exc.gate_step_id]

        now = time.monotonic()
        if exc.gate_step_id not in gate_retry_deadlines:
            gate_retry_deadlines[exc.gate_step_id] = now + retry_policy.max_duration_seconds

        within_attempts = failure_count < retry_policy.max_attempts
        within_duration = now < gate_retry_deadlines[exc.gate_step_id]
        if not (within_attempts and within_duration):
            return None

        return await self._instance_service.retry_after_gate_failure(
            workflow_id=workflow_id,
            definition=definition,
            retry_from_step_id=retry_from_step_id,
            reason=(
                f"quality gate '{exc.gate_step_id}' failed (attempt {failure_count} of "
                f"{retry_policy.max_attempts}) — retrying from '{retry_from_step_id}'"
            ),
        )
