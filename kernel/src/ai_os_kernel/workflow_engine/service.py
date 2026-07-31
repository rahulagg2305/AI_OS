"""Orchestrates workflow instance creation, state transitions, and
step-by-step progression: validate/resolve, then persist.

Deliberately thin — validation is pure logic
(:mod:`ai_os_kernel.workflow_engine.input_validation`), persistence is
an injected :class:`WorkflowInstanceRepository`, definition registration
is an injected :class:`WorkflowDefinitionCatalog`, and step work is an
injected :class:`StepExecutor` (ADR-0010: explicit composition root, no
DI container — concrete implementations are constructed and handed in
by whatever wires this service up).
"""

from __future__ import annotations

from typing import Any

from ai_os_kernel.workflow_engine.definition_catalog import WorkflowDefinitionCatalog
from ai_os_kernel.workflow_engine.errors import WorkflowInvalidTransitionError
from ai_os_kernel.workflow_engine.gate_result_recorder import GateResultRecorder
from ai_os_kernel.workflow_engine.input_validation import (
    validate_inputs,
    validate_pack_id,
    validate_principal,
    validate_reason,
)
from ai_os_kernel.workflow_engine.instance import WorkflowInstance
from ai_os_kernel.workflow_engine.models import StepType, WorkflowDefinition, WorkflowStep
from ai_os_kernel.workflow_engine.repository import WorkflowInstanceRepository
from ai_os_kernel.workflow_engine.step_executor import StepExecutor


class WorkflowInstanceService:
    """Creates workflow instances, transitions them between states, and
    advances them one declared step at a time.

    Out of scope at this step: real agent/tool invocation, LLM calls,
    leasing, parallel/sub-workflows, and retry/compensation.
    """

    def __init__(
        self,
        repository: WorkflowInstanceRepository,
        step_executor: StepExecutor,
        definition_catalog: WorkflowDefinitionCatalog,
        gate_result_recorder: GateResultRecorder | None = None,
    ) -> None:
        self._repository = repository
        self._step_executor = step_executor
        self._definition_catalog = definition_catalog
        self._gate_result_recorder = gate_result_recorder

    async def create_instance(
        self,
        *,
        definition: WorkflowDefinition,
        inputs: dict[str, Any],
        principal_id: str,
        pack_id: str,
    ) -> WorkflowInstance:
        """Register ``definition`` into the catalog, then create the
        instance that references it.

        Registration happens first, and always — not conditionally on
        whether it looks already-registered — because
        :class:`WorkflowDefinitionCatalog` upserts idempotently (``ON
        CONFLICT ... DO NOTHING``); a definition already on record from
        an earlier instance is a no-op, not a duplicate error. This
        ordering is what makes ``workflow_instances``' foreign key to
        ``catalog.workflow_definitions`` (data_model.md §4.1) safe: by
        the time the instance insert runs, a matching definition row is
        guaranteed to exist.

        The two writes are deliberately **not** one atomic transaction:
        registration only ever inserts-or-no-ops the same content for a
        given ``(definition_id, version)``, so a registration that
        commits and an instance-creation that then fails for an
        unrelated reason leaves nothing incorrect behind — the
        registered definition is still true, and instance creation can
        simply be retried. No document requires atomicity across these
        two tables the way it does for ``workflow_instances``/
        ``workflow_events`` (data_model.md §4: "written in one
        transaction so they can never disagree").
        """
        validate_principal(principal_id)
        validate_pack_id(pack_id)
        validate_inputs(definition, inputs)
        await self._definition_catalog.register(definition=definition, pack_id=pack_id)
        return await self._repository.create(
            definition_id=definition.id,
            definition_version=definition.version,
            inputs=inputs,
            principal_id=principal_id,
        )

    async def start(
        self,
        *,
        workflow_id: str,
        reason: str,
        triggering_event_id: str | None = None,
    ) -> WorkflowInstance:
        """Transition ``workflow_id`` from `created` to `running`.

        The only transition implemented at this step. Any other
        starting status is rejected by the repository's guard, not by
        a status check duplicated here.
        """
        validate_reason(reason)
        return await self._repository.transition_to_running(
            workflow_id=workflow_id,
            reason=reason,
            triggering_event_id=triggering_event_id,
        )

    async def advance(
        self,
        *,
        workflow_id: str,
        definition: WorkflowDefinition,
    ) -> WorkflowInstance:
        """Advance ``workflow_id`` by exactly one declared step, or
        complete it if there is no next step.

        One call, one step (or one completion) — repeated calls drive a
        multi-step workflow to completion; there is no internal loop
        here (a scheduler/orchestrator driving that loop is later
        work, as is leasing). The executor runs before the persistence
        write and outside any database transaction — the correct
        sequencing for when a real executor eventually makes an
        external call (an agent, a tool, an LLM).

        ``workflow_id`` is now also passed to the executor
        (``StepExecutor.execute(next_step, workflow_id=workflow_id)``)
        — the one piece of instance identity a shared, per-definition
        ``WorkflowStep`` cannot carry itself, and the piece
        :class:`~ai_os_kernel.workflow_engine.step_executor.
        AgentStepExecutor` now needs to ask the Context Manager for this
        instance's own state (agent_architecture.md's Invocation
        Lifecycle: "Workflow Engine assembles context via the Context
        Manager"). Every executor defaults this to ``None`` and every
        implementation except ``AgentStepExecutor`` ignores it entirely,
        so this is a pure, additive wiring change, not new orchestration
        logic — see :mod:`ai_os_kernel.workflow_engine.step_executor`'s
        own module docstring.

        **A genuinely failed attempt is now genuinely recorded (added
        2026-07-30) — closing quality_gate_engine.md §9's own "every
        gate execution must record ... error details" requirement,
        which a *raised* step exception used to defeat entirely: this
        method used to call the executor with nothing written if it
        raised, since :meth:`~ai_os_kernel.workflow_engine.repository.
        WorkflowInstanceRepository.advance_workflow` — the only method
        that ever wrote a ``workflow_steps`` row — was never reached.**
        The executor call is now wrapped in a ``try``/``except``: on any
        exception, :meth:`~ai_os_kernel.workflow_engine.repository.
        WorkflowInstanceRepository.record_failed_attempt` writes a real
        ``workflow_steps`` row (``status="failed"``, real error detail,
        a real computed ``attempt`` number from the same
        ``MAX(attempt)+1`` query :meth:`advance_workflow` already uses)
        before the *original* exception is re-raised, byte-for-byte in
        every way that matters (message, type, chained cause) — every
        existing caller (:class:`~ai_os_kernel.workflow_engine.
        advance_runner.WorkflowAdvanceRunner`'s own retry/failure logic)
        sees the exact same exception it always has; only a new, genuine
        side effect (the persisted row) is added. A subsequent
        successful attempt (a bounded retry) still gets its own correct,
        higher ``attempt`` number, since both write paths compute it
        from the same table.

        **The caught exception also gains a generic ``step_id``
        attribute here (added 2026-07-30, the general-step-retry step)
        — set dynamically, on any exception type, not only ones that
        declare it themselves.** This is the one piece of information
        only this method reliably has for *every* exception a step
        executor can raise (``next_step`` is a local variable here, not
        recoverable from the exception object otherwise): which step
        was being attempted. :class:`~ai_os_kernel.workflow_engine.
        advance_runner.WorkflowAdvanceRunner` reads this generic
        attribute — never a type-specific one — to decide whether a
        bounded retry applies, so the retry mechanism itself needs no
        per-exception-type special-casing; only whether the exception
        also declares itself ``retriable`` (see that module's own
        docstring for the category split) gates the decision.
        """
        instance = await self._repository.get_instance(workflow_id)
        if instance is None:
            raise WorkflowInvalidTransitionError(
                f"workflow instance '{workflow_id}' does not exist"
            )

        next_step = self._resolve_next_step(definition, instance.current_step_id)

        outputs: dict[str, Any] = {}
        if next_step is not None:
            try:
                outputs = await self._step_executor.execute(next_step, workflow_id=workflow_id)
            except Exception as exc:
                # setattr (not `exc.step_id = ...`, which mypy --strict
                # correctly rejects — `exc`'s *static* type is the bare
                # `Exception` this `except` clause declares, which has
                # no such attribute) — every real exception type this
                # codebase raises supports the assignment at runtime
                # (none declare `__slots__`); `noqa: B010` is this one,
                # narrow, justified exception to "prefer direct
                # assignment," needed specifically because the direct
                # form fails strict type-checking for a deliberately
                # dynamic attribute.
                setattr(exc, "step_id", next_step.id)  # noqa: B010
                await self._repository.record_failed_attempt(
                    workflow_id=workflow_id,
                    definition_id=definition.id,
                    definition_version=definition.version,
                    expected_current_step_id=instance.current_step_id,
                    step=next_step,
                    error={"type": type(exc).__name__, "message": str(exc)},
                )
                await self._maybe_record_gate_result(
                    workflow_id=workflow_id, definition=definition, step=next_step
                )
                raise

        result = await self._repository.advance_workflow(
            workflow_id=workflow_id,
            definition_id=definition.id,
            definition_version=definition.version,
            expected_current_step_id=instance.current_step_id,
            next_step=next_step,
            outputs=outputs,
        )
        if next_step is not None:
            await self._maybe_record_gate_result(
                workflow_id=workflow_id, definition=definition, step=next_step
            )
        return result

    async def _maybe_record_gate_result(
        self, *, workflow_id: str, definition: WorkflowDefinition, step: WorkflowStep
    ) -> None:
        """Reads back ``step``'s own just-written :class:`~ai_os_kernel.
        workflow_engine.step_record.WorkflowStepRecord` (the highest
        ``attempt`` for its ``step_name`` — guaranteed to be the row
        :meth:`advance_workflow`/``record_failed_attempt`` just
        committed, since attempts only ever increase) and, when it is a
        genuinely-evaluated ``quality_gate`` step, hands it to the
        injected :class:`~ai_os_kernel.workflow_engine.
        gate_result_recorder.GateResultRecorder` — see that module's own
        docstring for the full placement reasoning and column mapping.
        A no-op when no recorder was injected (every existing caller),
        when ``step`` is not a ``quality_gate`` step, or when it is one
        whose own id has no configured source (``QualityGateStepExecutor``'s
        documented no-op case: an empty ``outputs`` on an attempt that
        did *not* fail is the real, structural "never genuinely
        evaluated" signal — a genuine failure always carries real
        ``error`` detail instead, so this never mistakes a failed gate
        for an unconfigured one).
        """
        if step.type is not StepType.QUALITY_GATE or self._gate_result_recorder is None:
            return

        steps = await self._repository.list_steps(workflow_id)
        matching = [s for s in steps if s.step_name == step.id]
        if not matching:
            return
        step_record = max(matching, key=lambda s: s.attempt)
        if step_record.error is None and not step_record.outputs:
            return

        await self._gate_result_recorder.record(
            workflow_id=workflow_id, gate_version=definition.version, step=step_record
        )

    @staticmethod
    def _resolve_next_step(
        definition: WorkflowDefinition, current_step_id: str | None
    ) -> WorkflowStep | None:
        steps = definition.steps
        if current_step_id is None:
            if not steps:
                raise WorkflowInvalidTransitionError(
                    f"workflow definition '{definition.id}' declares no steps"
                )
            return steps[0]

        for index, step in enumerate(steps):
            if step.id == current_step_id:
                return steps[index + 1] if index + 1 < len(steps) else None

        raise WorkflowInvalidTransitionError(
            f"workflow definition '{definition.id}' has no step '{current_step_id}' "
            "(the instance's current step does not belong to this definition)"
        )

    async def retry_after_step_failure(
        self,
        *,
        workflow_id: str,
        definition: WorkflowDefinition,
        retry_from_step_id: str,
        reason: str,
    ) -> WorkflowInstance:
        """Resets ``workflow_id``'s own ``current_step_id`` so the next
        :meth:`advance` call genuinely re-executes ``retry_from_step_id``
        — the bounded step retry :class:`~ai_os_kernel.workflow_engine.
        advance_runner.WorkflowAdvanceRunner` calls after catching *any*
        exception that declares itself ``retriable`` (originally built,
        and originally named ``retry_after_gate_failure``, for exactly
        one such exception, :class:`~ai_os_kernel.workflow_engine.errors.
        QualityGateFailedError` — see that runner's own module docstring
        for the full, now-generalized retriable-vs-not category split)
        it has a configured retry target for. Which step to retry from,
        and how many times, are both the *caller's* own decisions (a
        composition-level mapping and ``definition.retry_policy``,
        respectively) — this method only performs the one, real,
        mechanical part: computing "the step immediately before
        ``retry_from_step_id``" and writing it via
        :meth:`~ai_os_kernel.workflow_engine.repository.
        WorkflowInstanceRepository.reset_current_step`.
        """
        instance = await self._repository.get_instance(workflow_id)
        if instance is None:
            raise WorkflowInvalidTransitionError(
                f"workflow instance '{workflow_id}' does not exist"
            )

        retry_to_step_id = self._step_before(definition, retry_from_step_id)
        return await self._repository.reset_current_step(
            workflow_id=workflow_id,
            definition_id=definition.id,
            definition_version=definition.version,
            expected_current_step_id=instance.current_step_id,
            retry_to_step_id=retry_to_step_id,
            reason=reason,
        )

    @staticmethod
    def _step_before(definition: WorkflowDefinition, step_id: str) -> str | None:
        """The declared step id immediately before ``step_id`` in
        ``definition.steps`` — ``None`` when ``step_id`` is the
        definition's own first step (mirroring ``current_step_id``'s
        existing "haven't started yet" meaning)."""
        steps = definition.steps
        for index, step in enumerate(steps):
            if step.id == step_id:
                return steps[index - 1].id if index > 0 else None

        raise WorkflowInvalidTransitionError(
            f"workflow definition '{definition.id}' has no step '{step_id}' "
            "(a gate_retry_targets/gate_sources mapping refers to a step this "
            "definition does not declare)"
        )
