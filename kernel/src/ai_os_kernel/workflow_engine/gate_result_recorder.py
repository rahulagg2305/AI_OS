"""Minimal write path for ``evaluation.gate_results`` — the Evaluation
Engine's (module 12, still schema-only) first real producer.

quality_gate_engine.md §3/§7 names "record all gate executions for
audit and for the Evaluation Engine" as a core responsibility and
"results must be durable and available to the Evaluation Engine" as a
key design rule; §6's own conceptual Gate Result Contract lists
``gate_id``/``status``/``metrics``/``messages``/``duration``/
``timestamp``. None of that had a real writer until now — the full
Quality Gate Engine package (Gate Registry, Gate Executor, Result
Evaluator, Policy Enforcer) remains unbuilt; this is exactly the one
writer §7 names, reduced to the one real gate-evaluating component that
exists, :class:`~ai_os_kernel.workflow_engine.quality_gate.
QualityGateStepExecutor`.

**Placement decision: a separate recorder, composed by
:class:`~ai_os_kernel.workflow_engine.service.WorkflowInstanceService`
after the fact — not inside ``QualityGateStepExecutor`` itself, and not
the identical shape :class:`~ai_os_kernel.llm_gateway.call_recorder.
SqlLLMCallRecorder` uses either, for a stated, opposite reason.**
``SqlLLMCallRecorder`` is separate from ``DispatchingLLMGateway``
specifically because ``LLMRequest``/``LLMResponse`` do not carry the
correlation context (workflow/step) a recorder needs — that gap forces
whichever caller *does* have that context to compose the two calls
explicitly. ``QualityGateStepExecutor.execute()`` has the opposite
problem: it already has every piece of *evaluation* context it needs
(``workflow_id``, the gate's own step id, the source step's real
output) with zero extra plumbing, so putting the write inside it would
have been just as defensible on correlation-context grounds alone.
What actually rules that out is **timing of the one column
``QualityGateStepExecutor`` cannot honestly supply**: ``step``'s own
real, persisted ``attempt`` number. ``execute()`` runs *before*
:meth:`~ai_os_kernel.workflow_engine.repository.
WorkflowInstanceRepository.advance_workflow`/``record_failed_attempt``
compute and write it (both via the identical ``MAX(attempt)+1`` query)
— from inside ``execute()``, the attempt this resolution will become
does not exist as real data yet, only as a number this recorder could
*re-derive* by duplicating that same query speculatively, racing the
real write. :meth:`WorkflowInstanceService.advance` is the one place
that already calls those writers and can therefore read the row *they
just committed* back for real, after the fact — the identical
read-back-what-was-just-written technique :class:`~ai_os_kernel.
workflow_engine.quality_gate.QualityGateStepExecutor`'s own
``_latest_completed_output`` already uses for the *source* step, here
applied to the gate's own just-written row instead. No new
``WorkflowInstanceRepository`` method or return-type change was needed
for this — :meth:`list_steps` (already real, already used by the
executor) is sufficient.

**Column mapping — every value is read from the real, already-persisted
``WorkflowStepRecord`` this recorder is handed, or supplied by the one
caller that has it; nothing is invented or estimated**:

- ``step_id``/``gate_id`` ← ``step.step_name`` (the gate step's own
  declared id — the identical value :meth:`QualityGateStepExecutor.
  execute`'s own successful output already names ``gateId``). No
  separate Gate Registry id exists to use instead of the two being
  identical here.
- ``gate_version`` ← the caller-supplied workflow definition's own
  ``version`` (``WorkflowDefinition.version``, already validated at
  load time) — the one real, sourced proxy available for "which
  version of this gate's own declaration produced this result" with no
  Gate Registry/gate-versioning concept yet to ask instead.
- ``status`` ← ``step.status`` verbatim (``"completed"``/``"failed"``,
  the same vocabulary :mod:`~ai_os_kernel.workflow_engine.step_record`
  already documents as undocumented-value-list, deliberately not
  translated into a separate ``"passed"``/``"failed"`` vocabulary this
  step would otherwise have to invent).
- ``severity`` ← the fixed literal ``"blocking"`` — an honest structural
  constant, not per-row invented data: quality_gate_engine.md §7 names
  ``blocking``/``warning`` as the only two severities this design
  documents, and every gate ``QualityGateStepExecutor`` can evaluate
  today is unconditionally blocking (it always raises
  ``QualityGateFailedError``, halting the run, on failure — no
  warning-severity gate execution path exists in this codebase yet).
  The identical "no field maps to this yet, store the honest constant"
  convention ``SqlLLMCallRecorder``'s own ``degradations=[]`` already
  established.
- ``metrics`` ← ``{"attempt": step.attempt}`` — the one real,
  quantifiable number this resolution genuinely has; no numeric score
  exists anywhere in this design (the check is a single boolean field),
  so nothing else is invented to fill this column.
- ``messages`` ← ``[step.error["message"]]`` when ``step.error`` is not
  ``None`` (the real, already-recorded failure message
  ``WorkflowInstanceRepository.record_failed_attempt`` wrote); ``[]`` on
  a genuine pass, since a passing gate's own real output
  (``{"gateId": ..., "sourceStepId": ..., "passed": True}``) carries no
  free-text message to surface here.
- ``duration_ms`` ← ``(step.completed_at - step.started_at)`` in
  milliseconds. **Honestly always ``0`` today, not a bug specific to
  this writer**: both ``advance_workflow`` and ``record_failed_attempt``
  stamp ``started_at``/``completed_at`` with the identical timestamp at
  write time (confirmed by reading both — neither records the
  executor's own real start/end separately), so this column faithfully
  reports what these two, already-real timestamp columns actually
  contain. A genuinely non-zero measurement would require instrumenting
  ``QualityGateStepExecutor`` itself to time its own real check — out of
  this step's own scope ("sourced from data already genuinely
  available"), and recorded here as a known, honest limitation rather
  than papered over with an invented number.

**An unconfigured ``quality_gate`` step is not recorded.** A step whose
own id is absent from ``QualityGateStepExecutor``'s ``gate_sources`` is
a documented no-op (``execute()`` returns ``{}`` immediately, never
evaluating anything) — recording a "result" for a check that never
genuinely ran would misrepresent it as an evaluation. The caller
detects this the same domain-agnostic way: a real evaluation's own
success output is never empty (``QualityGateStepExecutor.execute()``'s
own contract always returns at least ``gateId``/``sourceStepId``/the
success field on a genuine pass), so an empty ``outputs`` on a
``completed`` gate step is the real, structural signal to skip, not a
hardcoded field-name check.
"""

from __future__ import annotations

from typing import Any, Protocol

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.persistence.evaluation_schema import gate_results
from ai_os_kernel.workflow_engine.errors import GateResultRecordingError
from ai_os_kernel.workflow_engine.ids import new_gate_result_id
from ai_os_kernel.workflow_engine.step_record import WorkflowStepRecord

_SEVERITY_BLOCKING = "blocking"


class GateResultRecorder(Protocol):
    """Persistence boundary for recording one resolved ``quality_gate``
    step's real outcome — the seam a fake implementation substitutes in
    unit tests (ADR-0004: interface-driven, configuration over code)."""

    async def record(
        self, *, workflow_id: str, gate_version: str, step: WorkflowStepRecord
    ) -> None: ...


class SqlGateResultRecorder:
    """The only implementation of :class:`GateResultRecorder` at this
    stage: SQLAlchemy 2.0 Core against Postgres (ADR-0011)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def record(
        self, *, workflow_id: str, gate_version: str, step: WorkflowStepRecord
    ) -> None:
        duration_ms = (
            int((step.completed_at - step.started_at).total_seconds() * 1000)
            if step.completed_at is not None
            else 0
        )
        messages: list[Any] = [step.error["message"]] if step.error is not None else []

        try:
            async with self._engine.begin() as connection:
                await connection.execute(
                    sa.insert(gate_results).values(
                        result_id=new_gate_result_id(),
                        workflow_id=workflow_id,
                        step_id=step.step_name,
                        gate_id=step.step_name,
                        gate_version=gate_version,
                        status=step.status,
                        severity=_SEVERITY_BLOCKING,
                        metrics={"attempt": step.attempt},
                        messages=messages,
                        duration_ms=duration_ms,
                    )
                )
        except sa.exc.SQLAlchemyError as exc:
            raise GateResultRecordingError(
                f"failed to record gate result for workflow '{workflow_id}' "
                f"step '{step.step_name}': {exc}"
            ) from exc
