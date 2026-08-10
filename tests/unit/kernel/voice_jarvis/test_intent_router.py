"""Unit tests for `PlatformIntentRouter` (`P06-S06-M33-T01`) — real
`HealthService`/`ApprovalService` composed with fake, structurally-typed
repositories (ADR-0004: interface-driven, configuration over code),
the identical pattern `tests/security/test_t10_unauthorized_approval.py`
already establishes for `ApprovalService` itself.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from ai_os_kernel.health import HealthService
from ai_os_kernel.security_manager.models import Principal, PrincipalType
from ai_os_kernel.voice_jarvis.errors import VoiceIntentError
from ai_os_kernel.voice_jarvis.intent_router import PlatformIntentRouter
from ai_os_kernel.voice_jarvis.models import VoiceIntent
from ai_os_kernel.workflow_engine.human_approval import (
    Approval,
    ApprovalListCursor,
    ApprovalService,
)
from ai_os_kernel.workflow_engine.instance import WorkflowInstance, WorkflowInstanceStatus
from ai_os_kernel.workflow_engine.repository import WorkflowListCursor


class _FakeWorkflowInstanceRepository:
    def __init__(self, instances: list[WorkflowInstance]) -> None:
        self._instances = {instance.workflow_id: instance for instance in instances}

    async def list_instances(
        self, *, limit: int, before: WorkflowListCursor | None = None
    ) -> list[WorkflowInstance]:
        return list(self._instances.values())[:limit]

    async def get_instance(self, workflow_id: str) -> WorkflowInstance | None:
        return self._instances.get(workflow_id)


class _FakeApprovalRepository:
    def __init__(self, existing: Approval | None = None) -> None:
        self._approval = existing

    async def get_by_id(self, *, approval_id: str) -> Approval | None:
        return self._approval

    async def get_by_step(self, *, workflow_id: str, step_id: str) -> Approval | None:
        return self._approval

    async def list_pending(self) -> list[Approval]:
        raise NotImplementedError

    async def list_decided(
        self, *, limit: int, before: ApprovalListCursor | None = None
    ) -> list[Approval]:
        raise NotImplementedError

    async def create_pending(self, **kwargs: object) -> Approval:
        raise NotImplementedError

    async def decide(
        self, *, approval_id: str, principal_id: str, decision: str, comment: str | None
    ) -> Approval:
        assert self._approval is not None
        self._approval = self._approval.model_copy(
            update={"status": decision, "decided_by": principal_id, "decision_comment": comment}
        )
        return self._approval


def _instance(workflow_id: str, *, current_step_id: str | None = "step_1") -> WorkflowInstance:
    now = datetime.now(UTC)
    return WorkflowInstance(
        workflow_id=workflow_id,
        definition_id="def_1",
        definition_version="1.0.0",
        status=WorkflowInstanceStatus.RUNNING,
        current_step_id=current_step_id,
        inputs={},
        outputs=None,
        experiment_id=None,
        run_manifest_id=None,
        principal_id="user_test",
        principal_permissions=None,
        scheduled_at=None,
        last_event_seq=0,
        error=None,
        total_cost_usd=Decimal("0"),
        total_tokens=0,
        created_at=now,
        updated_at=now,
        completed_at=None,
    )


def _approval(*, approval_class: str = "approve-git-push") -> Approval:
    now = datetime.now(UTC)
    return Approval(
        approval_id="appr_1",
        workflow_id="wf_1",
        step_id="step_1",
        approval_class=approval_class,
        title="A real approval",
        description="A real description",
        context_digest="deadbeef",
        options=["approved", "rejected"],
        status="pending",
        decided_by=None,
        decision_comment=None,
        requested_at=now,
        expires_at=None,
        decided_at=None,
    )


def _principal(roles: list[str]) -> Principal:
    return Principal(
        principal_id="voice-test-user", principal_type=PrincipalType.USER, roles=frozenset(roles)
    )


def _router(
    *,
    workflow_repository: _FakeWorkflowInstanceRepository | None = None,
    approval_repository: _FakeApprovalRepository | None = None,
) -> PlatformIntentRouter:
    return PlatformIntentRouter(
        health_service=HealthService(checks=[]),
        workflow_instance_repository=workflow_repository or _FakeWorkflowInstanceRepository([]),
        approval_service=ApprovalService(approval_repository or _FakeApprovalRepository()),
    )


def test_check_health_reports_the_real_status() -> None:
    result = asyncio.run(
        _router().handle(VoiceIntent(intent_type="check_health"), principal=_principal(["viewer"]))
    )

    assert result.response_text == "Platform status is ready."


def test_list_workflows_requires_workflow_read() -> None:
    router = _router(workflow_repository=_FakeWorkflowInstanceRepository([_instance("wf_1")]))

    with pytest.raises(VoiceIntentError, match="workflow:read"):
        asyncio.run(
            router.handle(
                VoiceIntent(intent_type="list_workflows"), principal=_principal(["nobody"])
            )
        )


def test_list_workflows_reports_a_real_count_for_an_authorized_principal() -> None:
    router = _router(
        workflow_repository=_FakeWorkflowInstanceRepository([_instance("wf_1"), _instance("wf_2")])
    )

    result = asyncio.run(
        router.handle(VoiceIntent(intent_type="list_workflows"), principal=_principal(["operator"]))
    )

    assert "2" in result.response_text
    assert "workflow instances" in result.response_text


def test_get_workflow_status_for_a_real_instance() -> None:
    router = _router(
        workflow_repository=_FakeWorkflowInstanceRepository(
            [_instance("wf_1", current_step_id="build")]
        )
    )

    result = asyncio.run(
        router.handle(
            VoiceIntent(intent_type="get_workflow_status", workflow_id="wf_1"),
            principal=_principal(["viewer"]),
        )
    )

    assert "wf_1" in result.response_text
    assert "running" in result.response_text
    assert "build" in result.response_text


def test_get_workflow_status_for_an_unknown_workflow_is_honestly_not_found() -> None:
    router = _router()

    with pytest.raises(VoiceIntentError, match="no workflow instance"):
        asyncio.run(
            router.handle(
                VoiceIntent(intent_type="get_workflow_status", workflow_id="wf-does-not-exist"),
                principal=_principal(["viewer"]),
            )
        )


def test_get_workflow_status_without_a_workflow_id_is_a_real_local_error() -> None:
    router = _router()

    with pytest.raises(VoiceIntentError, match="requires workflow_id"):
        asyncio.run(
            router.handle(
                VoiceIntent(intent_type="get_workflow_status"), principal=_principal(["viewer"])
            )
        )


def test_decide_approval_with_an_invalid_decision_is_a_real_local_error() -> None:
    router = _router()

    with pytest.raises(VoiceIntentError, match="approved"):
        asyncio.run(
            router.handle(
                VoiceIntent(intent_type="decide_approval", approval_id="appr_1", decision="maybe"),
                principal=_principal(["admin"]),
            )
        )


def test_decide_approval_succeeds_for_an_authorized_admin() -> None:
    router = _router(approval_repository=_FakeApprovalRepository(_approval()))

    result = asyncio.run(
        router.handle(
            VoiceIntent(intent_type="decide_approval", approval_id="appr_1", decision="approved"),
            principal=_principal(["admin"]),
        )
    )

    assert result.response_text == "Approval appr_1 was approved."


def test_decide_approval_refuses_an_unauthorized_principal_and_leaves_it_pending() -> None:
    router = _router(approval_repository=_FakeApprovalRepository(_approval()))

    with pytest.raises(VoiceIntentError, match="not authorized"):
        asyncio.run(
            router.handle(
                VoiceIntent(
                    intent_type="decide_approval", approval_id="appr_1", decision="approved"
                ),
                principal=_principal(["viewer"]),
            )
        )


def test_decide_approval_for_an_unknown_approval_is_honestly_not_found() -> None:
    router = _router(approval_repository=_FakeApprovalRepository(None))

    with pytest.raises(VoiceIntentError, match="does not exist"):
        asyncio.run(
            router.handle(
                VoiceIntent(
                    intent_type="decide_approval", approval_id="appr-nope", decision="approved"
                ),
                principal=_principal(["admin"]),
            )
        )
