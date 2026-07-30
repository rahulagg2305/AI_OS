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
from ai_os_kernel.workflow_engine.input_validation import (
    validate_inputs,
    validate_pack_id,
    validate_principal,
    validate_reason,
)
from ai_os_kernel.workflow_engine.instance import WorkflowInstance
from ai_os_kernel.workflow_engine.models import WorkflowDefinition, WorkflowStep
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
    ) -> None:
        self._repository = repository
        self._step_executor = step_executor
        self._definition_catalog = definition_catalog

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
        before the *original* exception is re-raised, byte-for-byte
        unchanged (bare ``raise``) — every existing caller
        (:class:`~ai_os_kernel.workflow_engine.advance_runner.
        WorkflowAdvanceRunner`'s own retry/failure logic) sees the exact
        same exception it always has; only a new, genuine side effect
        (the persisted row) is added. A subsequent successful attempt
        (a bounded retry, or any future general step retry) still gets
        its own correct, higher ``attempt`` number, since both write
        paths compute it from the same table.
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
                await self._repository.record_failed_attempt(
                    workflow_id=workflow_id,
                    definition_id=definition.id,
                    definition_version=definition.version,
                    expected_current_step_id=instance.current_step_id,
                    step=next_step,
                    error={"type": type(exc).__name__, "message": str(exc)},
                )
                raise

        return await self._repository.advance_workflow(
            workflow_id=workflow_id,
            definition_id=definition.id,
            definition_version=definition.version,
            expected_current_step_id=instance.current_step_id,
            next_step=next_step,
            outputs=outputs,
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

    async def retry_after_gate_failure(
        self,
        *,
        workflow_id: str,
        definition: WorkflowDefinition,
        retry_from_step_id: str,
        reason: str,
    ) -> WorkflowInstance:
        """Resets ``workflow_id``'s own ``current_step_id`` so the next
        :meth:`advance` call genuinely re-executes ``retry_from_step_id``
        — the bounded quality-gate retry
        :class:`~ai_os_kernel.workflow_engine.advance_runner.
        WorkflowAdvanceRunner` calls after catching a
        :class:`~ai_os_kernel.workflow_engine.errors.QualityGateFailedError`
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
