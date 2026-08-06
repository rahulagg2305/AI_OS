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

**The real Gate Registry now optionally cross-wires in (``P02-S06-M15-T09``)
— genuinely resolving each step's real, manifest-declared ``gateId``,
never changing the real, currently-working enforcement decision.**
``gate_registry``/``gate_ids`` (both ``None`` by default — every
existing caller/test unaffected) let a composition supply a real
:class:`~ai_os_kernel.quality_gate_engine.registry.GateRegistry` plus
the identical composition-level ``{workflow_step_id: real gateId}``
mapping shape ``gate_sources`` above already establishes, for the same
"cross-step reference belongs in the composition layer" reason —
``WorkflowStep`` has no field of its own linking a step to a
pack-declared gate id either. When both are supplied for a step, this
executor resolves the real definition and uses its real ``id``/
``version`` in the returned output (``gateId``/``gateVersion``) instead
of the workflow-local step id — genuinely richer, real data, not
fabricated. **The evaluation itself is completely unchanged**: it
still comes from the identical ``source_output.get(success_field)``
check below, regardless of whether a registry resolved anything.

**Evaluating a result is now separated from enforcing its severity
(``P02-S06-M15-T07``) — the Policy Enforcer this class's own docstring
above named as unbuilt.** A resolved gate's real ``severity``
(``"blocking"`` when no registry entry resolves, matching every prior
caller's own unchanged behaviour) decides the *consequence* of a
non-passing evaluation, never the evaluation itself: ``"blocking"``
still raises :class:`~ai_os_kernel.workflow_engine.errors.
QualityGateFailedError`, halting the run exactly as before this step;
``"warning"`` returns normally instead, with ``severity: "warning"``
in the real, persisted output — genuinely recorded (see
:mod:`~ai_os_kernel.workflow_engine.gate_result_recorder`'s own,
correspondingly updated column mapping), never silently dropped, and
never blocking progression. Both of the one real pack's own declared
gates are ``severity="blocking"`` today, so this remains a zero-
behaviour-change for `se.delivery_pipeline`'s own real runs; proven for
the new, real ``"warning"`` case with a real, schema-conformant gate
definition in this module's own unit tests (no manifest anywhere
declares one yet — the identical "build real, wire later" precedent
the Gate Registry itself was built under, `P02-S06-M15-T05`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ai_os_kernel.quality_gate_engine.registry import GateRegistry
from ai_os_kernel.workflow_engine.errors import QualityGateFailedError
from ai_os_kernel.workflow_engine.models import StepType, WorkflowStep
from ai_os_kernel.workflow_engine.repository import WorkflowInstanceRepository
from ai_os_kernel.workflow_engine.step_record import WorkflowStepRecord

_SEVERITY_BLOCKING = "blocking"
_SEVERITY_WARNING = "warning"


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
    or when its output's ``success_field`` is not literally ``True``,
    **and the resolved gate's severity is ``"blocking"``** (the default
    when no registry entry resolves — every caller from before
    ``P02-S06-M15-T07`` unaffected). This mirrors
    :class:`~ai_os_kernel.workflow_engine.step_executor.
    AgentStepExecutor`/:class:`~ai_os_kernel.workflow_engine.
    step_executor.ToolStepExecutor`, which already raise
    (:class:`AgentOutputValidationError`/:class:`ToolOutputValidationError`)
    rather than returning a structured failure — the existing failure
    boundary this codebase already has (:class:`WorkflowAdvanceRunner.
    run_to_completion`'s own ``except Exception`` at its loop boundary),
    not new orchestration logic. A ``"warning"``-severity gate's own
    non-passing evaluation instead returns normally, with
    ``severity: "warning"`` in the output — genuinely recorded, never
    blocking (``P02-S06-M15-T07``'s own Policy Enforcer distinction).
    """

    def __init__(
        self,
        repository: WorkflowInstanceRepository,
        *,
        gate_sources: Mapping[str, str],
        success_field: str = "passed",
        gate_registry: GateRegistry | None = None,
        gate_ids: Mapping[str, str] | None = None,
    ) -> None:
        self._repository = repository
        self._gate_sources = dict(gate_sources)
        self._success_field = success_field
        self._gate_registry = gate_registry
        self._gate_ids = dict(gate_ids or {})

    async def execute(
        self,
        step: WorkflowStep,
        *,
        workflow_id: str | None = None,
        principal_permissions: frozenset[str] | None = None,
        workflow_permissions: frozenset[str] | None = None,
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

        gate_id: str = step.id
        gate_version: str | None = None
        severity = _SEVERITY_BLOCKING
        real_gate_id = self._gate_ids.get(step.id)
        if self._gate_registry is not None and real_gate_id is not None:
            definition = await self._gate_registry.resolve_gate(real_gate_id)
            gate_id = definition.id
            gate_version = definition.version
            severity = definition.severity

        steps = await self._repository.list_steps(workflow_id)
        source_output = _latest_completed_output(steps, source_step_id)
        if source_output is None:
            failure_detail = f"source step '{source_step_id}' has no persisted output yet"
            passed = False
        else:
            result = source_output.get(self._success_field)
            passed = result is True
            failure_detail = (
                f"source step '{source_step_id}' reported {self._success_field}={result!r}, "
                "not True"
            )

        if not passed and severity == _SEVERITY_BLOCKING:
            raise QualityGateFailedError(
                f"quality gate step '{step.id}' blocked progression: {failure_detail}",
                gate_step_id=step.id,
            )

        outputs: dict[str, Any] = {
            "gateId": gate_id,
            "sourceStepId": source_step_id,
            self._success_field: passed,
        }
        if gate_version is not None:
            outputs["gateVersion"] = gate_version
        if not passed:
            # Reached only when severity == "warning" (blocking already
            # raised above) — genuinely recorded, never blocks
            # progression. See this class's own docstring.
            outputs["severity"] = _SEVERITY_WARNING
        return outputs
