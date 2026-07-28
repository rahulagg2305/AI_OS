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

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

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
        """
        validate_max_iterations(max_iterations)

        instance: WorkflowInstance | None = None
        for iteration in range(1, max_iterations + 1):
            try:
                instance = await self.run_once(
                    workflow_id=workflow_id,
                    definition=definition,
                    worker_id=worker_id,
                    lease_duration_seconds=lease_duration_seconds,
                )
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
