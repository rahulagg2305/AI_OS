"""T10 — Unauthorized approval of a governance decision
(security_architecture.md §4/§9). Unlike every other threat in this
package, **no real enforcement exists for T10 today** —
security_architecture.md's own Implementation Status (line 32) confirms
the ADR-0023 monotonic-narrowing chain only computes the principal term
so far, and this codebase has zero runtime code handling a
``human_approval`` step: :class:`~ai_os_kernel.workflow_engine.
step_executor.DispatchingStepExecutor` has no branch for
``StepType.HUMAN_APPROVAL`` at all (it falls through to whatever
``default_executor`` was supplied), and
:class:`~ai_os_kernel.workflow_engine.models.HumanApprovalPoint` has no
field to attribute a decision to anyone.

**These tests are a disclosed, honest tripwire, not a positive control
proof.** They assert the current, real absence of enforcement — so that
the day someone adds real approval-decision handling, at least one of
these tests forces a conscious update (and, with it, a matching security
review), rather than the gap silently persisting unnoticed.
"""

from __future__ import annotations

from typing import Any

import pytest

from ai_os_kernel.workflow_engine.models import HumanApprovalPoint, StepType, WorkflowStep
from ai_os_kernel.workflow_engine.step_executor import DispatchingStepExecutor, NoOpStepExecutor


def test_human_approval_point_has_no_field_to_attribute_a_decision_to_anyone() -> None:
    """No real code today could even record "who decided, and what" —
    the model that would need to carry it does not have the field."""
    fields = set(HumanApprovalPoint.model_fields)

    assert not fields & {"decision", "decided_by", "approved_by", "decided_at", "outcome"}


class _FailIfCalled:
    async def execute(
        self, step: WorkflowStep, *, workflow_id: str | None = None
    ) -> dict[str, Any]:
        raise AssertionError("no executor should specifically handle a human_approval step today")


@pytest.mark.asyncio
async def test_a_human_approval_step_is_currently_executed_as_a_silent_no_op() -> None:
    """The real, current, disclosed gap: a `human_approval` step is
    dispatched to `default_executor` exactly like an unimplemented
    `decision`/`parallel` step — nothing blocks workflow progress
    pending a real decision, and nothing records one. This is the
    concrete state this ticket's own honest framing names: T10 has no
    real control to test yet, only a real absence to guard."""
    dispatcher = DispatchingStepExecutor(
        agent_executor=_FailIfCalled(),
        tool_executor=_FailIfCalled(),
        default_executor=NoOpStepExecutor(),
    )
    step = WorkflowStep(
        id="approve-deployment",
        type=StepType.HUMAN_APPROVAL,
    )

    outputs = await dispatcher.execute(step)

    assert outputs == {}
