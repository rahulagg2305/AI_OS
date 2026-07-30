"""The Workflow Engine's own first real executor for a ``quality_gate``
step — closing the one gap `implementation_status.md`'s own tracking
named as the most-referenced open gap across this project's docs
(module 15, Quality Gate Engine, 0% built): "the `quality_gate` workflow
step type completes as a no-op via `NoOpStepExecutor`."

**Deliberately the smallest real slice, not the full Quality Gate
Engine.** `docs/03_architecture/kernel/quality_gate_engine.md` designs a
much larger component (Gate Registry, Gate Executor, Result Evaluator,
Policy Enforcer, an `evaluation.gate_results` writer, pack-declared gate
definitions with their own `evaluationMethod`/`successCriteria`) — none
of that exists yet, and none of it is required to make ADR-0006's own
"blocking gates cannot be skipped" invariant genuinely true for the one
gate this codebase already has a real, de facto version of: **does the
Test Agent's own run genuinely pass?** `verification.py`'s own
``passed`` output field already answers that question for real, from a
real ``exitCode``/timeout, never from LLM judgment (see its own
docstring) — nothing in the Workflow Engine has ever *read* that field
to decide whether to continue. This executor is exactly that reading,
formalised into a real, declared, blocking workflow step, per this
step's own approved framing: "formalizing that pass/fail into a real,
declared quality_gate-type workflow step that actually blocks
progression on failure, rather than a brand new gate concept."

**Why the source step is composition-level config, not a new field on
`WorkflowStep`.** `WorkflowStep`'s own model docstring (`models.py`) is
explicit that its five invocation fields are "never ... a cross-step
reference," and :class:`~ai_os_kernel.context_manager.resolvers.
WorkflowStepOutputResolver` already established the precedent this
executor follows: a cross-step reference belongs in the composition
layer (a `{consuming_step_id: source_step_id}` mapping the caller
supplies), not as new, workflow-file-facing architecture invented here.
`gate_sources` below is that same shape, applied to gate steps instead
of agent/tool steps — a pipeline-specific `WorkflowStep.id -> str`
mapping supplied by whatever composes this executor (e.g.
:mod:`ai_os_kernel.workflow_engine.delivery_pipeline`), not hardcoded
inside this generic, domain-agnostic class.

**Why the check is a single named field, not an expression language.**
`quality_gate_engine.md` §2 lists "remain domain-agnostic at the Kernel
level" as a real design goal; this executor honours it by looking for
one, named boolean field (``success_field``, defaulting to the
already-shipped ``"passed"`` convention `verification.py` established)
on the source step's own persisted output — the smallest real rule that
is still genuinely data-driven (no pack id, no agent id, no threshold
baked in here) rather than the full Gate Contract's
``evaluationMethod``/``successCriteria`` machinery, which needs a real
Gate Registry this step does not build.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ai_os_kernel.workflow_engine.errors import QualityGateFailedError
from ai_os_kernel.workflow_engine.models import StepType, WorkflowStep
from ai_os_kernel.workflow_engine.repository import WorkflowInstanceRepository
from ai_os_kernel.workflow_engine.step_record import WorkflowStepRecord


def _latest_completed_output(
    steps: Sequence[WorkflowStepRecord], step_name: str
) -> dict[str, Any] | None:
    """The most-recently-attempted ``steps`` row named ``step_name``
    with a real, persisted output — ``None`` when no such row exists
    yet. The identical "highest attempt wins" selection
    :mod:`ai_os_kernel.context_manager.resolvers`'s own private
    ``_latest_completed_output`` already established for the same read
    model — duplicated here, in miniature, rather than imported, since
    that module lives in a different package specifically to read
    *this* package's repository, and its own docstring documents why it
    cannot import ``workflow_engine.repository``/``workflow_engine.
    step_record`` at runtime (a genuine circular import) — importing
    *its* private helper back from here would be the same hazard in
    reverse, for four lines of code."""
    candidates = [
        step for step in steps if step.step_name == step_name and step.outputs is not None
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda step: step.attempt).outputs or {}


class QualityGateStepExecutor:
    """Executes a ``quality_gate``-type step by checking whether its
    configured source step's own real, persisted output reports success.

    A gate step id absent from ``gate_sources`` resolves as a pass with
    empty outputs — the identical "an unconfigured step contributes/
    blocks nothing" shape :class:`~ai_os_kernel.context_manager.
    resolvers.WorkflowStepOutputResolver` already established, so a
    workflow can declare a ``quality_gate`` step this executor does not
    yet know how to evaluate without that step failing by default.

    Raises :class:`QualityGateFailedError` — never returns a "failed"
    result silently — when the source step has no persisted output yet,
    or when its output's ``success_field`` is not literally ``True``.
    This mirrors :class:`~ai_os_kernel.workflow_engine.step_executor.
    AgentStepExecutor`/:class:`~ai_os_kernel.workflow_engine.
    step_executor.ToolStepExecutor`, which already raise
    (:class:`AgentOutputValidationError`/:class:`ToolOutputValidationError`)
    rather than returning a structured failure — the existing failure
    boundary this codebase already has (:class:`WorkflowAdvanceRunner.
    run_to_completion`'s own ``except Exception`` at its loop boundary),
    not new orchestration logic.
    """

    def __init__(
        self,
        repository: WorkflowInstanceRepository,
        *,
        gate_sources: Mapping[str, str],
        success_field: str = "passed",
    ) -> None:
        self._repository = repository
        self._gate_sources = dict(gate_sources)
        self._success_field = success_field

    async def execute(
        self, step: WorkflowStep, *, workflow_id: str | None = None
    ) -> dict[str, Any]:
        if step.type is not StepType.QUALITY_GATE:
            raise ValueError(
                f"QualityGateStepExecutor cannot execute step '{step.id}' of type "
                f"'{step.type.value}' — it only handles quality_gate steps"
            )
        source_step_id = self._gate_sources.get(step.id)
        if source_step_id is None:
            return {}
        if workflow_id is None:
            raise ValueError(
                f"quality gate step '{step.id}' requires a real workflow_id to read "
                "its source step's persisted output"
            )

        steps = await self._repository.list_steps(workflow_id)
        source_output = _latest_completed_output(steps, source_step_id)
        if source_output is None:
            raise QualityGateFailedError(
                f"quality gate step '{step.id}' blocked progression: source step "
                f"'{source_step_id}' has no persisted output yet"
            )

        result = source_output.get(self._success_field)
        if result is not True:
            raise QualityGateFailedError(
                f"quality gate step '{step.id}' blocked progression: source step "
                f"'{source_step_id}' reported {self._success_field}={result!r}, "
                "not True"
            )

        return {"gateId": step.id, "sourceStepId": source_step_id, self._success_field: True}
