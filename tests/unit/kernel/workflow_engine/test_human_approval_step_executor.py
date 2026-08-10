"""Unit tests for ``HumanApprovalStepExecutor``'s own logic — fake
``approval_repository``/``instance_repository``/``definition_catalog``
throughout, isolating point resolution, pending/approved/rejected
dispatch, and idempotent pending-row creation from what a real
``SqlApprovalRepository``/``SqlWorkflowInstanceRepository``/
``SqlWorkflowDefinitionCatalog`` do internally, which is already
proven, real, end to end, against a real Postgres container by
``tests/integration/workflow_engine/test_human_approval_execution.py``
(``P03-S05-M14-T04``/``T05``)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from ai_os_kernel.workflow_engine.errors import (
    HumanApprovalPendingError,
    HumanApprovalRejectedError,
)
from ai_os_kernel.workflow_engine.human_approval import Approval, HumanApprovalStepExecutor
from ai_os_kernel.workflow_engine.instance import WorkflowInstance, WorkflowInstanceStatus
from ai_os_kernel.workflow_engine.models import (
    HumanApprovalPoint,
    StepType,
    WorkflowDefinition,
    WorkflowStep,
)

_DEFINITION_ID = "se.approval_test"
_DEFINITION_VERSION = "1.0.0"
_STEP_ID = "approve-deployment"


def _definition() -> WorkflowDefinition:
    return WorkflowDefinition.model_validate(
        {
            "id": _DEFINITION_ID,
            "name": "Approval Test",
            "description": "test fixture",
            "version": _DEFINITION_VERSION,
            "inputs": {"type": "object"},
            "outputs": {"type": "object"},
            "steps": [{"id": _STEP_ID, "type": "human_approval"}],
            "humanApprovalPoints": [
                {
                    "id": _STEP_ID,
                    "name": "Approve Deployment",
                    "description": "Approve the production deployment.",
                    "context": {"target": "prod"},
                    "options": ["approve", "reject"],
                }
            ],
            "failureHandling": {"onError": "halt"},
        }
    )


def _step() -> WorkflowStep:
    return WorkflowStep(id=_STEP_ID, type=StepType.HUMAN_APPROVAL)


def _instance() -> WorkflowInstance:
    now = datetime.now(UTC)
    return WorkflowInstance(
        workflow_id="wf_fake",
        definition_id=_DEFINITION_ID,
        definition_version=_DEFINITION_VERSION,
        status=WorkflowInstanceStatus.RUNNING,
        current_step_id=None,
        inputs={},
        outputs=None,
        experiment_id=None,
        run_manifest_id=None,
        principal_id="user-42",
        principal_permissions=None,
        scheduled_at=None,
        last_event_seq=2,
        error=None,
        total_cost_usd=Decimal("0"),
        total_tokens=0,
        created_at=now,
        updated_at=now,
        completed_at=None,
    )


def _approval(*, status: str, decided_by: str | None = None) -> Approval:
    now = datetime.now(UTC)
    return Approval(
        approval_id="appr_fake",
        workflow_id="wf_fake",
        step_id=_STEP_ID,
        approval_class=_STEP_ID,
        title="Approve Deployment",
        description="Approve the production deployment.",
        context_digest="deadbeef",
        options=["approve", "reject"],
        status=status,
        decided_by=decided_by,
        decision_comment=None,
        requested_at=now,
        expires_at=None,
        decided_at=now if decided_by else None,
    )


class _FakeApprovalRepository:
    def __init__(self, existing: Approval | None = None) -> None:
        self._existing = existing
        self.create_calls: list[dict[str, Any]] = []

    async def get_by_step(self, *, workflow_id: str, step_id: str) -> Approval | None:
        return self._existing

    async def get_by_id(self, *, approval_id: str) -> Approval | None:
        return self._existing

    async def list_pending(self) -> list[Approval]:
        raise NotImplementedError("not exercised by these tests")

    async def create_pending(
        self, *, workflow_id: str, step_id: str, point: HumanApprovalPoint
    ) -> Approval:
        self.create_calls.append({"workflow_id": workflow_id, "step_id": step_id, "point": point})
        self._existing = _approval(status="pending")
        return self._existing

    async def decide(self, **kwargs: Any) -> Approval:
        raise NotImplementedError("not exercised by these tests")


class _FakeInstanceRepository:
    def __init__(self, instance: WorkflowInstance | None) -> None:
        self._instance = instance

    async def get_instance(self, workflow_id: str) -> WorkflowInstance | None:
        return self._instance


class _FakeDefinitionCatalog:
    def __init__(self, definition: WorkflowDefinition | None) -> None:
        self._definition = definition

    async def register(self, **kwargs: Any) -> None:
        raise NotImplementedError("not exercised by these tests")

    async def get(self, *, definition_id: str, version: str) -> WorkflowDefinition | None:
        return self._definition

    async def get_declared_permissions(self, *, definition_id: str, version: str) -> frozenset[str]:
        return frozenset()


_UNSET = object()


def _executor(
    *,
    approval_repository: _FakeApprovalRepository,
    instance: WorkflowInstance | None = None,
    definition: WorkflowDefinition | None | object = _UNSET,
) -> HumanApprovalStepExecutor:
    resolved_definition = _definition() if definition is _UNSET else definition
    return HumanApprovalStepExecutor(
        approval_repository=approval_repository,
        instance_repository=_FakeInstanceRepository(  # type: ignore[arg-type]
            instance if instance is not None else _instance()
        ),
        definition_catalog=_FakeDefinitionCatalog(resolved_definition),  # type: ignore[arg-type]
    )


async def test_the_first_arrival_creates_a_real_pending_approval_and_pauses() -> None:
    approval_repository = _FakeApprovalRepository(existing=None)
    executor = _executor(approval_repository=approval_repository)

    with pytest.raises(HumanApprovalPendingError):
        await executor.execute(_step(), workflow_id="wf_fake")

    assert len(approval_repository.create_calls) == 1
    call = approval_repository.create_calls[0]
    assert call["workflow_id"] == "wf_fake"
    assert call["step_id"] == _STEP_ID
    assert call["point"].id == _STEP_ID


async def test_a_still_pending_approval_keeps_pausing_without_creating_a_duplicate() -> None:
    approval_repository = _FakeApprovalRepository(existing=_approval(status="pending"))
    executor = _executor(approval_repository=approval_repository)

    with pytest.raises(HumanApprovalPendingError):
        await executor.execute(_step(), workflow_id="wf_fake")

    assert approval_repository.create_calls == []


async def test_an_approved_decision_resolves_with_a_real_output() -> None:
    approval_repository = _FakeApprovalRepository(
        existing=_approval(status="approved", decided_by="user-99")
    )
    executor = _executor(approval_repository=approval_repository)

    outputs = await executor.execute(_step(), workflow_id="wf_fake")

    assert outputs["decision"] == "approved"
    assert outputs["decidedBy"] == "user-99"


async def test_a_rejected_decision_raises_a_genuine_failure() -> None:
    approval_repository = _FakeApprovalRepository(
        existing=_approval(status="rejected", decided_by="user-99")
    )
    executor = _executor(approval_repository=approval_repository)

    with pytest.raises(HumanApprovalRejectedError):
        await executor.execute(_step(), workflow_id="wf_fake")


async def test_a_missing_workflow_id_is_refused() -> None:
    executor = _executor(approval_repository=_FakeApprovalRepository())

    with pytest.raises(ValueError, match="requires a real workflow_id"):
        await executor.execute(_step())


async def test_it_refuses_a_step_of_any_other_type() -> None:
    executor = _executor(approval_repository=_FakeApprovalRepository())
    not_human_approval = WorkflowStep(id="analyze", type=StepType.AGENT, agent_id="se.pack/agent")

    with pytest.raises(ValueError, match="only handles human_approval steps"):
        await executor.execute(not_human_approval, workflow_id="wf_fake")


async def test_a_definition_missing_from_the_catalog_fails_clearly() -> None:
    executor = _executor(approval_repository=_FakeApprovalRepository(), definition=None)

    with pytest.raises(ValueError, match="not registered in the catalog"):
        await executor.execute(_step(), workflow_id="wf_fake")
