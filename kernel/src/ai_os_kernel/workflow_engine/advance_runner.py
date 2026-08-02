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

**Bounded step retry, generalized beyond quality gates (added
2026-07-30).** This module first proved the retry mechanism (attempt/
duration tracking, resetting ``current_step_id`` backward) against
exactly one exception type, :class:`~ai_os_kernel.workflow_engine.
errors.QualityGateFailedError`. It now retries *any* step-executor
exception that declares itself retriable — the identical, already-real
``retriable`` self-declaration :class:`~ai_os_kernel.llm_gateway.
errors.LLMProviderError` already carries for exactly this purpose
(``category``/``retriable`` per error_handling_retry.md §3's own
taxonomy) — rather than a hardcoded list of exception class names.

**The retriable-vs-not split, and why.** ``run_to_completion`` retries
an exception if and only if ``getattr(exc, "retriable", None) is True``
— an explicit, per-instance self-declaration, never inferred from the
exception's class alone:

- **Retriable by default, because they already declare it themselves**:
  :class:`QualityGateFailedError` (``retriable = True`` unconditionally
  — see its own docstring for why a gate failure's retry is genuine
  corrective work, not a blind re-evaluation) and
  :class:`~ai_os_kernel.llm_gateway.errors.LLMProviderError` with its
  own ``retriable`` left at its documented default (``True`` —
  ``error_taxonomy.py``'s own ``CHAIN_EXHAUSTED``/``CIRCUIT_OPEN``
  classifications: a provider call that just exhausted the Gateway's
  *own* immediate retry/fallback/circuit-breaker chain may still
  succeed on a *later*, coarser retry once conditions change — the
  identical reasoning a Kubernetes Job retry applies on top of a
  container's own internal HTTP retries, not "retrying the same thing
  twice").
- **Never retriable, because they declare it themselves** (an explicit
  ``retriable = False``, e.g. :class:`LLMRefusalError`, or an
  ``LLMProviderError`` classified ``budget``/most ``permanent``/most
  ``infrastructure`` conditions): the *caller's own* request or
  configuration is the problem, not a transient condition of the
  provider — retrying would reliably reproduce the identical failure.
- **Never retriable by default, because they declare nothing at all**
  (every other Workflow Engine step-executor exception today —
  :class:`AgentOutputValidationError`, :class:`ToolOutputValidationError`,
  :class:`ToolSandboxRequiredError`, :class:`AgentNotRegisteredError`,
  :class:`ToolNotRegisteredError`, :class:`EntrypointLoadError`,
  :class:`PackNotActivatedError`, :class:`PromptedAgentInputError`):
  each represents a structural or configuration problem (a malformed
  output, a missing registration, an unimportable entrypoint, a caller
  omitting a required field) that retrying the *identical* call would
  reproduce exactly, every time — error_handling_retry.md §3's own
  ``permanent`` category ("Will not succeed with the same input").
  ``getattr(exc, "retriable", None)`` on any of these is ``None``, not
  ``True``, so they fall through to the exact same immediate-``FAILED``
  behavior this codebase already had before gate retry existed.
- **Retriable per real cause, decided explicitly, not left undecided**
  (added 2026-07-31, resolving the gap the retry-widening step itself
  named): :class:`AgentRegistryError`/:class:`ToolRegistryError` now
  each carry the identical ``retriable`` constructor parameter
  :class:`~ai_os_kernel.llm_gateway.errors.LLMProviderError` already
  established, defaulted ``False`` (the *opposite* default, since three
  of this exception's four real causes are structural/permanent — a
  loaded entrypoint failing the ``Agent``/``Tool`` Protocol check, a
  tool's own ``trust_tier`` disagreeing with its catalog row, or a
  missing backing object for a declared permission — and only one, a
  genuine persistence-layer failure during the catalog lookup itself,
  is transient). **Investigation found a real, structural way to tell
  the causes apart after all** — the "no way to tell them apart
  structurally" framing two steps ago undersold it: every raise site in
  :mod:`~ai_os_kernel.workflow_engine.registry` already knows exactly
  which real cause it represents, so each sets ``retriable`` explicitly
  at the one place that already has the answer, the identical
  per-instance pattern ``LLMProviderError`` uses across its own several
  real causes. No type split: nothing in this codebase catches either
  exception any narrower than its own type today, so splitting into two
  classes would add real code with no real consumer to justify it.

Which step a retriable failure retries *from* remains exactly the
composition-level config :mod:`~ai_os_kernel.workflow_engine.
quality_gate` already established (``step_retry_targets``, the
generalized name for what was ``gate_retry_targets``) — a step whose
own id is absent from that mapping is never retried, regardless of
``retriable``, the identical "unconfigured means unaffected" shape this
mechanism has had from the start.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
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
    WAITING_FOR_HUMAN = "waiting_for_human"
    """A real, honest outcome (added 2026-08-02, ``P03-S05-M14-T04``) —
    the instance genuinely reached a ``human_approval`` step and is
    now durably paused, not failed. Without this, `run_to_completion`'s
    own loop would attempt a *second* `run_once` on an instance that
    is no longer `running`, hit `WorkflowLeaseService.acquire`'s
    existing "must be running" guard, and misreport a genuine pause as
    `FAILED` — see this class's own docstring below for exactly where
    the loop now returns early instead."""


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
        step_retry_targets: Mapping[str, str] | None = None,
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

        **Bounded step retry, generalized beyond quality gates (added
        2026-07-30, widened from the gate-only ``gate_retry_targets`` this
        parameter used to be called).** ``step_retry_targets``
        (``{failed_step_id: retry_from_step_id}``, defaulted ``None`` —
        every existing caller keeps the exact prior behaviour) is
        composition-level config, the identical shape
        :mod:`~ai_os_kernel.workflow_engine.quality_gate`'s own
        ``gate_sources`` already establishes: which step a failure
        should retry from is pipeline-specific knowledge, not a field
        this generic runner invents. When *any* exception is caught
        whose own ``getattr(exc, "retriable", None) is True`` — see this
        module's own docstring for the full retriable-vs-not category
        split — **and** its ``step_id`` (set by
        :meth:`~ai_os_kernel.workflow_engine.service.
        WorkflowInstanceService.advance` on every exception it catches)
        has a configured target **and** ``definition.retry_policy`` is
        declared, this method calls :meth:`~ai_os_kernel.workflow_engine.
        service.WorkflowInstanceService.retry_after_step_failure`
        (resetting ``current_step_id`` so the next iteration genuinely
        re-executes from ``retry_from_step_id``) instead of returning
        ``FAILED`` immediately — bounded on *both* axes
        ``error_handling_retry.md`` §4 requires ("maximum attempts +
        maximum duration"): a per-step attempt counter checked against
        ``retry_policy.max_attempts``, and a per-step deadline
        (``time.monotonic()`` at the first failure of this step, plus
        ``retry_policy.max_duration_seconds``) checked against the current
        time. Either bound reached, a non-retriable exception, or no
        retry configured at all, falls through to the exact same
        ``FAILED`` result this method already returned before gate
        retry ever existed — genuinely bounded, never an unconditional
        or unlimited retry.
        """
        validate_max_iterations(max_iterations)
        step_retry_targets = step_retry_targets or {}
        step_failure_counts: dict[str, int] = {}
        step_retry_deadlines: dict[str, float] = {}

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
                retried_instance = await self._maybe_retry_failed_step(
                    exc,
                    workflow_id=workflow_id,
                    definition=definition,
                    step_retry_targets=step_retry_targets,
                    step_failure_counts=step_failure_counts,
                    step_retry_deadlines=step_retry_deadlines,
                )
                if retried_instance is None:
                    # Before reporting a real failure, check whether
                    # `run_once` never even reached `advance()` — its
                    # own `WorkflowLeaseService.acquire` call rejected a
                    # genuinely already-`waiting_for_human` instance
                    # (this call's *own* prior iteration paused it, or
                    # a separate, later `run_to_completion` call is
                    # simply checking in on it again — see
                    # `WorkflowRunOutcome.WAITING_FOR_HUMAN`'s own
                    # docstring for why the `COMPLETED`-style early
                    # return below cannot catch this on its own: this
                    # rejection happens *before* `run_once` ever
                    # returns an instance to inspect). A real lease
                    # rejection from genuine contention, or any other
                    # cause, still falls through to `FAILED` unchanged.
                    current = await self._instance_service.get_instance(workflow_id)
                    if (
                        current is not None
                        and current.status is WorkflowInstanceStatus.WAITING_FOR_HUMAN
                    ):
                        return WorkflowRunResult(
                            workflow_id=workflow_id,
                            outcome=WorkflowRunOutcome.WAITING_FOR_HUMAN,
                            iterations=iteration,
                            last_instance=current,
                        )
                    return WorkflowRunResult(
                        workflow_id=workflow_id,
                        outcome=WorkflowRunOutcome.FAILED,
                        iterations=iteration,
                        last_instance=instance,
                        error=exc,
                    )
                instance = retried_instance
                continue

            if instance.status is WorkflowInstanceStatus.COMPLETED:
                return WorkflowRunResult(
                    workflow_id=workflow_id,
                    outcome=WorkflowRunOutcome.COMPLETED,
                    iterations=iteration,
                    last_instance=instance,
                )

            if instance.status is WorkflowInstanceStatus.WAITING_FOR_HUMAN:
                # Return immediately, the identical "an honest terminal
                # outcome for this call" reasoning the COMPLETED branch
                # above already applies — trying again would only hit
                # WorkflowLeaseService.acquire's own "must be running"
                # guard and misreport a genuine pause as FAILED (see
                # WorkflowRunOutcome.WAITING_FOR_HUMAN's own docstring).
                return WorkflowRunResult(
                    workflow_id=workflow_id,
                    outcome=WorkflowRunOutcome.WAITING_FOR_HUMAN,
                    iterations=iteration,
                    last_instance=instance,
                )

        return WorkflowRunResult(
            workflow_id=workflow_id,
            outcome=WorkflowRunOutcome.MAX_ITERATIONS_REACHED,
            iterations=max_iterations,
            last_instance=instance,
        )

    async def _maybe_retry_failed_step(
        self,
        exc: Exception,
        *,
        workflow_id: str,
        definition: WorkflowDefinition,
        step_retry_targets: Mapping[str, str],
        step_failure_counts: dict[str, int],
        step_retry_deadlines: dict[str, float],
    ) -> WorkflowInstance | None:
        """Returns the reset instance when a bounded retry genuinely
        applies; ``None`` when it does not (``exc`` does not declare
        itself ``retriable``, carries no ``step_id``, that step has no
        configured target, no ``retry_policy`` is declared, or a bound
        is already exhausted) — the caller falls through to ``FAILED``
        in that case, unchanged from this mechanism's own "before"
        behaviour, gate-only or otherwise.

        ``exc``'s own type is deliberately never checked here — only
        two generic, self-declared attributes are: ``retriable`` (see
        this module's own docstring for the full category split) and
        ``step_id`` (set uniformly, on any exception, by
        :meth:`~ai_os_kernel.workflow_engine.service.
        WorkflowInstanceService.advance`). This is what makes the
        mechanism itself require zero changes to gain a new retriable
        exception type in the future — only that type's own
        self-declaration.
        """
        if getattr(exc, "retriable", None) is not True:
            return None
        step_id = getattr(exc, "step_id", None)
        if not isinstance(step_id, str):
            return None

        retry_from_step_id = step_retry_targets.get(step_id)
        retry_policy = definition.retry_policy
        if retry_from_step_id is None or retry_policy is None:
            return None

        step_failure_counts[step_id] = step_failure_counts.get(step_id, 0) + 1
        failure_count = step_failure_counts[step_id]

        now = time.monotonic()
        if step_id not in step_retry_deadlines:
            step_retry_deadlines[step_id] = now + retry_policy.max_duration_seconds

        within_attempts = failure_count < retry_policy.max_attempts
        within_duration = now < step_retry_deadlines[step_id]
        if not (within_attempts and within_duration):
            return None

        return await self._instance_service.retry_after_step_failure(
            workflow_id=workflow_id,
            definition=definition,
            retry_from_step_id=retry_from_step_id,
            reason=(
                f"step '{step_id}' failed with a retriable {type(exc).__name__} "
                f"(attempt {failure_count} of {retry_policy.max_attempts}) — "
                f"retrying from '{retry_from_step_id}'"
            ),
        )
