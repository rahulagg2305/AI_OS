"""T10 — Unauthorized approval of a governance decision
(security_architecture.md §4/§9: "Ungoverned irreversible action" —
defenses: "§9 approval classes, attributable decisions, timeout never
approves").

**Real, positive control now exists for all three defenses named
above.** Before `P03-S05-M14-T04`/`T05` (2026-08-02), no real code
anywhere handled a `human_approval` step at all
(:class:`~ai_os_kernel.workflow_engine.step_executor.
DispatchingStepExecutor` had no branch for it) and
:class:`~ai_os_kernel.workflow_engine.models.HumanApprovalPoint` had no
field to attribute a decision to anyone — these tests used to assert
exactly that real absence, so that the day someone added real
approval-decision handling, at least one test would force a conscious
update (this one) rather than the gap silently persisting unnoticed.
`decide()` requires a real, non-empty, attributable `principal_id`
(never anonymous) and a real timeout never implies approval (nothing
anywhere converts an elapsed `expires_at` into an implicit decision —
see the real, Postgres-backed proof in
`tests/integration/workflow_engine/test_human_approval_execution.py`).

**"Approval classes are granted separately" is now real too
(`P03-S05-M14-T06`, 2026-08-02).**
:class:`~ai_os_kernel.workflow_engine.human_approval.ApprovalService`
sits in front of the repository's own `decide()` and enforces
ADR-0023's own documented per-class `approver` grant —
`approver:<approval_class>` or `admin` — via
:func:`~ai_os_kernel.security_manager.approval_authorization.
is_authorized_to_decide_approval`, refusing an unauthorized attempt
*before* any write, real proof below. This was a deliberate, disclosed,
product-owner-approved sequencing (build the Workflow-Engine-level
pause/resume + attributable-decision mechanism first, close RBAC as its
own, immediately-following step before any deploy-capability work
opens), not an oversight — see `human_approval.py`'s own module
docstring for the full reasoning and the options considered at each
step.

**Still real, disclosed, deferred scope**: no HTTP route/Bearer-token
wiring for this call site (service-layer `ApprovalService.decide()`
only), and no role *administration* — who may grant/revoke
`approver:<class>` itself is `admin`-only per ADR-0023 and unbuilt.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from ai_os_kernel.security_manager.errors import ApprovalNotAuthorizedError
from ai_os_kernel.security_manager.models import Principal, PrincipalType
from ai_os_kernel.workflow_engine.errors import HumanApprovalPendingError
from ai_os_kernel.workflow_engine.human_approval import (
    Approval,
    ApprovalService,
    HumanApprovalStepExecutor,
)
from ai_os_kernel.workflow_engine.instance import WorkflowInstance, WorkflowInstanceStatus
from ai_os_kernel.workflow_engine.models import (
    HumanApprovalPoint,
    StepType,
    WorkflowDefinition,
    WorkflowStep,
)
from ai_os_kernel.workflow_engine.step_executor import DispatchingStepExecutor, NoOpStepExecutor

_DEFINITION_ID = "se.t10_test"
_DEFINITION_VERSION = "1.0.0"
_STEP_ID = "approve-deployment"


def test_a_real_decision_is_now_attributable_to_a_principal() -> None:
    """The real, positive proof: unlike `HumanApprovalPoint` (still
    correctly bare — it only ever *declares* an approval point, never
    records a decision), `Approval` (`workflow.approvals`, real as of
    this step) genuinely carries who decided, when, and what —
    human_approval_points.md §6: "All human decisions must be
    attributable"."""
    fields = set(Approval.model_fields)
    assert {"decided_by", "decision_comment", "decided_at", "status"} <= fields

    # HumanApprovalPoint itself is correctly still bare — it declares
    # the approval point, never a decision; attribution genuinely
    # lives on the separate, real `Approval` model above.
    point_fields = set(HumanApprovalPoint.model_fields)
    assert not point_fields & {"decision", "decided_by", "approved_by", "decided_at", "outcome"}


def _definition() -> WorkflowDefinition:
    return WorkflowDefinition.model_validate(
        {
            "id": _DEFINITION_ID,
            "name": "T10 Test",
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
                    "context": {},
                    "options": ["approve", "reject"],
                }
            ],
            "failureHandling": {"onError": "halt"},
        }
    )


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
        last_event_seq=2,
        error=None,
        total_cost_usd=Decimal("0"),
        total_tokens=0,
        created_at=now,
        updated_at=now,
        completed_at=None,
    )


class _FailIfCalled:
    async def execute(
        self,
        step: WorkflowStep,
        *,
        workflow_id: str | None = None,
        principal_permissions: frozenset[str] | None = None,
        workflow_permissions: frozenset[str] | None = None,
    ) -> dict[str, Any]:
        raise AssertionError("no executor should specifically handle a human_approval step today")


async def test_a_human_approval_step_is_still_a_silent_no_op_when_unconfigured() -> None:
    """The one real absence that genuinely remains: `human_approval`
    routes to `NoOpStepExecutor` exactly like an unwired `decision`/
    `parallel` step for any caller that does not supply a real
    `human_approval_executor` — the identical "unconfigured means
    unaffected" shape `quality_gate_executor`/`decision_executor`/
    `parallel_executor`/`sub_workflow_executor` already established.
    This is a real, disclosed composition choice now, not an absence
    of any real alternative — see the next test."""
    dispatcher = DispatchingStepExecutor(
        agent_executor=_FailIfCalled(),
        tool_executor=_FailIfCalled(),
        default_executor=NoOpStepExecutor(),
    )
    step = WorkflowStep(id=_STEP_ID, type=StepType.HUMAN_APPROVAL)

    outputs = await dispatcher.execute(step)

    assert outputs == {}


class _FakeApprovalRepository:
    """Real approval-repository semantics (pending until a real
    decision arrives), fake persistence — no Postgres required to prove
    this control genuinely blocks."""

    def __init__(self, existing: Approval | None = None) -> None:
        self.create_calls = 0
        self._approval = existing

    async def get_by_step(self, *, workflow_id: str, step_id: str) -> Approval | None:
        return self._approval

    async def get_by_id(self, *, approval_id: str) -> Approval | None:
        return self._approval

    async def create_pending(
        self, *, workflow_id: str, step_id: str, point: HumanApprovalPoint
    ) -> Approval:
        self.create_calls += 1
        now = datetime.now(UTC)
        self._approval = Approval(
            approval_id="appr_fake",
            workflow_id=workflow_id,
            step_id=step_id,
            approval_class=point.id,
            title=point.name,
            description=point.description,
            context_digest="deadbeef",
            options=point.options,
            status="pending",
            decided_by=None,
            decision_comment=None,
            requested_at=now,
            expires_at=None,
            decided_at=None,
        )
        return self._approval

    async def decide(
        self,
        *,
        approval_id: str,
        principal_id: str,
        decision: str,
        comment: str | None,
    ) -> Approval:
        assert self._approval is not None and self._approval.approval_id == approval_id
        self._approval = self._approval.model_copy(
            update={
                "status": decision,
                "decided_by": principal_id,
                "decision_comment": comment,
                "decided_at": datetime.now(UTC),
            }
        )
        return self._approval


class _RefuseIfDecided:
    """Stands in for :class:`~ai_os_kernel.workflow_engine.human_approval.
    ApprovalRepository` in the unauthorized-attempt test — its own
    :meth:`decide` fails loudly if ever reached, proving
    :class:`~ai_os_kernel.workflow_engine.human_approval.ApprovalService`
    refuses *before* any write is attempted, not merely that a write
    happens to be rejected downstream."""

    def __init__(self, approval: Approval) -> None:
        self._approval = approval

    async def get_by_id(self, *, approval_id: str) -> Approval | None:
        return self._approval

    async def get_by_step(self, *, workflow_id: str, step_id: str) -> Approval | None:
        return self._approval

    async def create_pending(self, **kwargs: Any) -> Approval:
        raise NotImplementedError("not exercised by this test")

    async def decide(self, **kwargs: Any) -> Approval:
        raise AssertionError(
            "ApprovalService must refuse an unauthorized decision before ever "
            "calling the repository's own decide()"
        )


class _FakeInstanceRepository:
    async def get_instance(self, workflow_id: str) -> WorkflowInstance | None:
        return _instance()


class _FakeDefinitionCatalog:
    async def register(self, **kwargs: Any) -> None:
        raise NotImplementedError("not exercised by this test")

    async def get(self, *, definition_id: str, version: str) -> WorkflowDefinition | None:
        return _definition()

    async def get_declared_permissions(self, *, definition_id: str, version: str) -> frozenset[str]:
        return frozenset()


async def test_a_real_human_approval_step_genuinely_blocks_when_configured() -> None:
    """The real, positive control this file's own docstring promises:
    when a caller genuinely wires
    :class:`~ai_os_kernel.workflow_engine.human_approval.
    HumanApprovalStepExecutor` in (unlike the unconfigured case above),
    a `human_approval` step genuinely, repeatedly blocks — never
    silently completes — until a real decision is recorded. No
    Postgres needed: the repositories below are fakes, but the
    executor's own real control-flow logic is exercised directly,
    unmocked."""
    approval_repository = _FakeApprovalRepository()
    executor = HumanApprovalStepExecutor(
        approval_repository=approval_repository,
        instance_repository=_FakeInstanceRepository(),  # type: ignore[arg-type]
        definition_catalog=_FakeDefinitionCatalog(),
    )
    dispatcher = DispatchingStepExecutor(
        agent_executor=_FailIfCalled(),
        tool_executor=_FailIfCalled(),
        default_executor=NoOpStepExecutor(),
        human_approval_executor=executor,
    )
    step = WorkflowStep(id=_STEP_ID, type=StepType.HUMAN_APPROVAL)

    # Genuinely blocks on first arrival, and genuinely keeps blocking
    # on every later attempt while still undecided — never a coin
    # flip, never a second attempt "just working."
    for _ in range(3):
        with pytest.raises(HumanApprovalPendingError):
            await dispatcher.execute(step, workflow_id="wf_fake")

    # Exactly one real pending row was ever created — the second and
    # third attempts found it still pending, not duplicated.
    assert approval_repository.create_calls == 1


def _pending_approval(*, approval_class: str = _STEP_ID) -> Approval:
    now = datetime.now(UTC)
    return Approval(
        approval_id="appr_fake",
        workflow_id="wf_fake",
        step_id=_STEP_ID,
        approval_class=approval_class,
        title="Approve Deployment",
        description="Approve the production deployment.",
        context_digest="deadbeef",
        options=["approve", "reject"],
        status="pending",
        decided_by=None,
        decision_comment=None,
        requested_at=now,
        expires_at=None,
        decided_at=None,
    )


async def test_an_authorized_class_scoped_approver_can_decide() -> None:
    """The real, positive RBAC proof: a principal holding the exact
    class-scoped role ADR-0023 documents (`approver:<approval_class>`)
    genuinely, successfully decides — through
    :class:`~ai_os_kernel.workflow_engine.human_approval.ApprovalService`,
    not by calling the repository directly."""
    approval = _pending_approval(approval_class="approve-deployment")
    repository = _FakeApprovalRepository(existing=approval)
    service = ApprovalService(repository)
    principal = Principal(
        principal_id="user-99",
        principal_type=PrincipalType.USER,
        roles=frozenset({"approver:approve-deployment"}),
    )

    decided = await service.decide(
        approval_id=approval.approval_id,
        principal=principal,
        decision="approved",
        comment="Looks good to ship.",
    )

    assert decided.status == "approved"
    assert decided.decided_by == "user-99"


async def test_an_admin_can_decide_any_approval_class() -> None:
    """`admin` shortcuts every class-scoped check (ADR-0023: "All,
    including security policy, role assignment, and secret
    management")."""
    approval = _pending_approval(approval_class="approve-architecture")
    repository = _FakeApprovalRepository(existing=approval)
    service = ApprovalService(repository)
    principal = Principal(
        principal_id="root-99", principal_type=PrincipalType.USER, roles=frozenset({"admin"})
    )

    decided = await service.decide(
        approval_id=approval.approval_id,
        principal=principal,
        decision="approved",
        comment=None,
    )

    assert decided.status == "approved"


async def test_an_unauthorized_principal_is_refused_and_the_approval_stays_pending() -> None:
    """The real, negative RBAC proof: a principal holding an unrelated
    (or no) `approver:<class>` role is refused — and, critically, the
    approval is never touched. `_RefuseIfDecided`'s own `decide()`
    raises `AssertionError` if ever reached, so this test proves the
    refusal happens *before* any write is attempted, not that a write
    merely rolls back."""
    approval = _pending_approval(approval_class="approve-deployment")
    repository = _RefuseIfDecided(approval)
    service = ApprovalService(repository)

    # Wrong class entirely — authority to approve architecture is not
    # authority to approve a deployment (ADR-0023's own example).
    wrong_class_principal = Principal(
        principal_id="user-1",
        principal_type=PrincipalType.USER,
        roles=frozenset({"approver:approve-architecture"}),
    )
    with pytest.raises(ApprovalNotAuthorizedError):
        await service.decide(
            approval_id=approval.approval_id,
            principal=wrong_class_principal,
            decision="approved",
            comment=None,
        )

    # No role at all.
    no_role_principal = Principal(
        principal_id="user-2", principal_type=PrincipalType.USER, roles=frozenset()
    )
    with pytest.raises(ApprovalNotAuthorizedError):
        await service.decide(
            approval_id=approval.approval_id,
            principal=no_role_principal,
            decision="approved",
            comment=None,
        )

    # A bare, unscoped "approver" role — ADR-0023's own examples are
    # all class-scoped; an unscoped grant is not a documented fallback.
    bare_approver_principal = Principal(
        principal_id="user-3", principal_type=PrincipalType.USER, roles=frozenset({"approver"})
    )
    with pytest.raises(ApprovalNotAuthorizedError):
        await service.decide(
            approval_id=approval.approval_id,
            principal=bare_approver_principal,
            decision="approved",
            comment=None,
        )

    # The approval itself is still, genuinely, exactly as it started —
    # not silently resolved by any of the three refused attempts above.
    still_pending = await repository.get_by_id(approval_id=approval.approval_id)
    assert still_pending is not None
    assert still_pending.status == "pending"
    assert still_pending.decided_by is None
