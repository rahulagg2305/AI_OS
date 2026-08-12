"""Real support for the ``human_approval`` step type
(``P03-S05-M14-T04``/``T05``) — the last of the seven step types to
genuinely execute, closing R-001's own permanent hard rule ("no
deployment capability may ship before the Human Approval guardrail
exists," ``risk_register.md``).

**A workflow genuinely pauses — real, durable, resumable, never a
polling wait.** :class:`HumanApprovalStepExecutor` creates a real,
persisted ``pending`` row in ``workflow.approvals`` (schema-only until
this step; see ``persistence/schema.py``'s own docstring) the first
time it reaches a ``human_approval`` step, then raises
:class:`~ai_os_kernel.workflow_engine.errors.HumanApprovalPendingError`
— caught specially by :meth:`~ai_os_kernel.workflow_engine.service.
WorkflowInstanceService.advance` (not a failure), which transitions the
instance to ``waiting_for_human`` via the new
:meth:`~ai_os_kernel.workflow_engine.repository.
WorkflowInstanceRepository.mark_waiting_for_human`, leaving
``current_step_id`` genuinely unchanged (the step has not completed).
``list_runnable_instances`` (``P02-S01-M05-T12``) already filters on
``status = 'running'``, so a waiting instance is simply never
discovered again by the multi-instance worker loop — no new exclusion
logic needed. ``WorkflowLeaseService.acquire`` already refuses a
non-``running`` instance too (``lease.py``'s own existing guard), so a
caller driving this instance directly (``run_to_completion``) cannot
accidentally re-poll it into a spurious failure either — see
:mod:`ai_os_kernel.workflow_engine.advance_runner`'s own module
docstring for the new ``WorkflowRunOutcome.WAITING_FOR_HUMAN`` value
that makes this an honest, distinct outcome there, never ``FAILED``.

**Resume happens only through one real, service-layer write —
:meth:`SqlApprovalRepository.decide` — never a timeout.** Nothing in
this module, or anywhere else in this codebase, ever inspects
``expires_at``/``timeout`` to imply approval; a pending approval that
outlives its own declared timeout simply stays ``pending`` forever
until a real ``decide()`` call arrives (or an operator cancels it
through a later, separate mechanism — out of this step's own scope,
see below). ``decide()`` requires a real, non-empty, attributable
``principal_id`` (human_approval_points.md §6: "All human decisions
must be attributable") and atomically (one transaction) both updates
the ``approvals`` row (guarded ``UPDATE ... WHERE status = 'pending'``,
:class:`~ai_os_kernel.workflow_engine.errors.ApprovalNotPendingError`
on a double-decide) and flips the instance back to ``running`` (the
identical guarded-CAS shape :meth:`mark_waiting_for_human` uses in
reverse) — the *next* real ``advance()`` call re-invokes
:class:`HumanApprovalStepExecutor` for the identical step, which this
time finds a real, decided row and resolves normally (``approved`` →
a real output dict, completing the step exactly like any other
successful step) or raises
:class:`~ai_os_kernel.workflow_engine.errors.HumanApprovalRejectedError`
(``rejected`` — a genuine failure, halting the pipeline through the
existing failure boundary; human_approval_points.md §5's "may
terminate," compensation not built).

**Scoped deliberately smaller than the full framework document
(product-owner decision — see the design options presented and
`decide()`'s own docstring).** No HTTP route, no Bearer-token
authentication for *this* call site — a real, tested, callable
:class:`ApprovalService` is this step's whole scope, matching the
identical "build the Workflow-Engine-level mechanism first, defer
HTTP/production wiring" precedent every other step type this session
already established (``P02-S01-M05-T09`` through ``T15``); the
dashboard/API surface (``P06-S03-M39-T02``) is real, separate, later
work. Only ``approved``/``rejected`` decisions are accepted —
``changes_requested`` (no "loop back to an earlier step" target is
specified anywhere in the Contract) and automatic
``timed_out``/``cancelled`` transitions (no reaper/escalation-policy job
exists, mirroring how ``WorkflowLeaseReaper`` needed its own, later,
dedicated step) are real, valid, disclosed, deferred scope — not
silently dropped.

**RBAC is real too (``P03-S05-M14-T06``): :class:`ApprovalService`
enforces ADR-0023's own documented per-class ``approver`` grant before
any decision is recorded.** ``decide()`` at the repository level still
only proves *attribution* (a real, non-empty ``principal_id``); a real
*authorization* check now sits in front of it —
:func:`~ai_os_kernel.security_manager.approval_authorization.
is_authorized_to_decide_approval` requires the ``admin`` role or the
exact class-scoped role ``approver:<approval_class>`` (ADR-0023's own
example: ``approver:release`` distinct from ``approver:architecture``)
— reusing :class:`~ai_os_kernel.security_manager.models.Principal`
unchanged, not a parallel permission mechanism; see that module's own
docstring for why a standalone function, not a
:mod:`~ai_os_kernel.security_manager.permissions` addition. An
unauthorized attempt is refused *before* any write — the approval stays
genuinely, verifiably ``pending``, not rolled back. Still real,
disclosed, deferred scope: no HTTP route/Bearer-token wiring for this
call site (unchanged from the paragraph above), and no role
*administration* (who may grant/revoke `approver:<class>` itself is
out of scope — ADR-0023's own role assignment is `admin`-only and
unbuilt).

**``approval_class`` (data_model.md §4.5's own column, with no defined
source anywhere in the Human Approval Point Contract, §4).** Reuses the
human approval point's own ``id`` — the same "no new field, no
invented taxonomy" reasoning behind the id-based step↔point linkage
:mod:`ai_os_kernel.workflow_engine.models`'s own new cross-validator
already establishes (see its docstring). ``context_digest`` is a real
``sha256`` of exactly the point's own ``name``/``description``/
``context``/``options`` at the moment the pending row was created
(data_model.md §4.5: "sha256 of exactly what was shown at decision
time") — a tamper-evident record, not a placeholder.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Protocol

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.event_bus.outbox_writer import write_outbox_event
from ai_os_kernel.observability import get_logger
from ai_os_kernel.persistence.schema import approvals, workflow_events, workflow_instances
from ai_os_kernel.security_manager.approval_authorization import is_authorized_to_decide_approval
from ai_os_kernel.security_manager.errors import ApprovalNotAuthorizedError
from ai_os_kernel.security_manager.models import Principal
from ai_os_kernel.security_manager.role_administration import (
    RoleGrantRepository,
    resolve_effective_roles,
)
from ai_os_kernel.workflow_engine.definition_catalog import WorkflowDefinitionCatalog
from ai_os_kernel.workflow_engine.errors import (
    ApprovalNotPendingError,
    HumanApprovalPendingError,
    HumanApprovalRejectedError,
    WorkflowInstanceCreationError,
)
from ai_os_kernel.workflow_engine.ids import new_approval_id, new_event_id
from ai_os_kernel.workflow_engine.instance import WorkflowInstanceStatus
from ai_os_kernel.workflow_engine.models import HumanApprovalPoint, StepType, WorkflowStep
from ai_os_kernel.workflow_engine.repository import WorkflowInstanceRepository

_STATE_TRANSITIONED_EVENT_TYPE = "state.transitioned"
_STATE_TRANSITIONED_SCHEMA_VERSION = 1

# Outboxed Event Bus event types (`P02-S07-M17-T05`). The `approval.`
# prefix is not incidental: `notification.service._notification_type_for`
# classifies on exactly that prefix, and `event_bus.md` §5's own decision
# table assigns "approvals" to the **transactional outbox**, not the
# loss-tolerable in-process bus — so both are written through
# `write_outbox_event` inside the very transaction that records the
# approval, never published directly.
_APPROVAL_REQUESTED_EVENT_TYPE = "approval.requested"
_APPROVAL_DECIDED_EVENT_TYPE = "approval.decided"

logger = get_logger("ai_os_kernel.security_manager")

Decision = Literal["approved", "rejected"]


class Approval(BaseModel):
    """One ``workflow.approvals`` row (data_model.md §4.5)."""

    model_config = ConfigDict(frozen=True)

    approval_id: str
    workflow_id: str
    step_id: str
    approval_class: str
    title: str
    description: str
    context_digest: str
    options: list[str]
    status: str
    decided_by: str | None
    decision_comment: str | None
    requested_at: datetime
    expires_at: datetime | None
    decided_at: datetime | None


def _context_digest(point: HumanApprovalPoint) -> str:
    payload = {
        "name": point.name,
        "description": point.description,
        "context": point.context,
        "options": point.options,
    }
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class ApprovalListCursor(BaseModel):
    """A keyset position in :meth:`ApprovalRepository.list_decided`'s
    ``decided_at`` DESC, ``approval_id`` DESC ordering — matches the
    new ``ix_approvals_decided_at`` index (migration
    ``0037_approvals_decided_at_index``), the identical
    :class:`~ai_os_kernel.workflow_engine.repository.WorkflowListCursor`
    shape ``list_instances`` already establishes, applied here since
    decided approvals accumulate for the platform's whole life (unlike
    the genuinely bounded pending queue), so this needs real pagination,
    not a speculative unpaginated list."""

    model_config = ConfigDict(frozen=True)

    decided_at: datetime
    approval_id: str


class ApprovalRepository(Protocol):
    """Persistence boundary for ``workflow.approvals`` — the seam a
    fake implementation substitutes in unit tests (ADR-0004:
    interface-driven, configuration over code)."""

    async def get_by_step(self, *, workflow_id: str, step_id: str) -> Approval | None: ...

    async def get_by_id(self, *, approval_id: str) -> Approval | None: ...

    async def list_pending(self) -> list[Approval]: ...

    async def list_decided(
        self, *, limit: int, before: ApprovalListCursor | None = None
    ) -> list[Approval]: ...

    async def create_pending(
        self, *, workflow_id: str, step_id: str, point: HumanApprovalPoint
    ) -> Approval: ...

    async def decide(
        self,
        *,
        approval_id: str,
        principal_id: str,
        decision: Decision,
        comment: str | None,
    ) -> Approval: ...


class SqlApprovalRepository:
    """The only implementation of :class:`ApprovalRepository` at this
    stage: SQLAlchemy 2.0 Core against Postgres (ADR-0011)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def get_by_step(self, *, workflow_id: str, step_id: str) -> Approval | None:
        """A plain, unguarded read — the identical "no leasing/locking
        here" shape every other real read in this package already
        establishes (:meth:`~ai_os_kernel.workflow_engine.repository.
        SqlWorkflowInstanceRepository.get_instance`, etc.). Real
        exclusivity for the one write that matters
        (:meth:`decide`, never double-applied) lives in that method's
        own guarded ``UPDATE``, not here."""
        async with self._engine.connect() as connection:
            result = await connection.execute(
                sa.select(approvals).where(
                    approvals.c.workflow_id == workflow_id, approvals.c.step_id == step_id
                )
            )
            row = result.mappings().one_or_none()
        return Approval.model_validate(dict(row)) if row is not None else None

    async def get_by_id(self, *, approval_id: str) -> Approval | None:
        """A plain, unguarded read — see :meth:`get_by_step`'s own
        reasoning. Used by :class:`ApprovalService` to resolve an
        approval's own ``approval_class`` *before* deciding, so an
        unauthorized attempt can be refused without ever reaching
        :meth:`decide`'s guarded ``UPDATE``."""
        async with self._engine.connect() as connection:
            result = await connection.execute(
                sa.select(approvals).where(approvals.c.approval_id == approval_id)
            )
            row = result.mappings().one_or_none()
        return Approval.model_validate(dict(row)) if row is not None else None

    async def list_pending(self) -> list[Approval]:
        """Every real, currently ``pending`` row — api_architecture.md
        §6.2's own documented ``GET /api/v1/approvals`` ("Pending
        approvals"), and the real gap `human_approval.py`'s own module
        docstring named as "real, separate, later work"
        (``P06-S03-M39-T02``). Oldest-first (``requested_at`` ascending)
        — the same fairness convention
        :meth:`~ai_os_kernel.workflow_engine.repository.
        SqlWorkflowInstanceRepository.list_runnable_instances` already
        establishes for an actionable queue: a decision-maker should see
        the longest-waiting approval first, not have it buried under
        newer ones. Unpaginated by design — a real, disclosed, narrower
        scope than ``GET /workflows``'s own cursor-paginated listing
        (api_architecture.md §9): the set of *pending* approvals is
        genuinely small and bounded in practice (workflows spend most of
        their time `running`, not waiting on a human), so a real cursor
        mechanism here would be speculative complexity for a collection
        that does not need one."""
        async with self._engine.connect() as connection:
            result = await connection.execute(
                sa.select(approvals)
                .where(approvals.c.status == "pending")
                .order_by(approvals.c.requested_at.asc())
            )
            rows = result.mappings().all()
        return [Approval.model_validate(dict(row)) for row in rows]

    async def list_decided(
        self, *, limit: int, before: ApprovalListCursor | None = None
    ) -> list[Approval]:
        """api_architecture.md §6.2's own documented ``GET
        /api/v1/approvals/history`` ("Past decisions") — every real row
        no longer ``pending``, newest-decision-first (``decided_at``
        DESC, ``approval_id`` DESC — matches the new
        ``ix_approvals_decided_at`` index), keyset-paginated exactly
        like :meth:`~ai_os_kernel.workflow_engine.repository.
        SqlWorkflowInstanceRepository.list_instances` — the real,
        disclosed, deliberate opposite of :meth:`list_pending`'s own
        unpaginated shape: decided approvals accumulate for the
        platform's whole life, a growing collection api_architecture.md
        §9 rules offset pagination out for, not a genuinely small,
        bounded one."""
        query = (
            sa.select(approvals)
            .where(approvals.c.status != "pending")
            .order_by(approvals.c.decided_at.desc(), approvals.c.approval_id.desc())
            .limit(limit)
        )
        if before is not None:
            query = query.where(
                sa.tuple_(approvals.c.decided_at, approvals.c.approval_id)
                < (before.decided_at, before.approval_id)
            )
        async with self._engine.connect() as connection:
            result = await connection.execute(query)
            rows = result.mappings().all()
        return [Approval.model_validate(dict(row)) for row in rows]

    async def create_pending(
        self, *, workflow_id: str, step_id: str, point: HumanApprovalPoint
    ) -> Approval:
        approval_id = new_approval_id()
        requested_at = datetime.now(UTC)
        expires_at = (
            requested_at + timedelta(seconds=point.timeout) if point.timeout is not None else None
        )
        try:
            async with self._engine.begin() as connection:
                result = await connection.execute(
                    sa.insert(approvals)
                    .values(
                        approval_id=approval_id,
                        workflow_id=workflow_id,
                        step_id=step_id,
                        approval_class=point.id,
                        title=point.name,
                        description=point.description,
                        context_digest=_context_digest(point),
                        options=point.options,
                        status="pending",
                        decided_by=None,
                        decision_comment=None,
                        requested_at=requested_at,
                        expires_at=expires_at,
                        decided_at=None,
                    )
                    .returning(*approvals.columns)
                )
                row = result.mappings().one()
                # A human is now the blocking dependency of this run, and
                # until this step nothing told anyone (`P02-S07-M17-T05`).
                # Written inside the same transaction as the `pending` row
                # itself, so ADR-0012's guarantee holds both ways: a
                # committed request always produces a notification, and a
                # rolled-back one never announces an approval nobody can
                # actually find.
                #
                # `workflow_id`/`step_id` travel in the payload because
                # `platform.event_outbox` has no such columns, so the
                # relay rebuilds every `Event.workflow_id` as `None` — a
                # real, pre-existing schema limitation `outbox_relay`'s
                # own docstring documents. `expires_at` is stringified
                # because the column is JSONB and a `datetime` is not
                # JSON-serialisable.
                await write_outbox_event(
                    connection,
                    event_type=_APPROVAL_REQUESTED_EVENT_TYPE,
                    payload={
                        "approval_id": approval_id,
                        "workflow_id": workflow_id,
                        "step_id": step_id,
                        "approval_class": point.id,
                        "title": point.name,
                        "expires_at": expires_at.isoformat() if expires_at is not None else None,
                    },
                )
        except sa.exc.SQLAlchemyError as exc:
            raise WorkflowInstanceCreationError(
                f"failed to create a pending approval for workflow instance "
                f"'{workflow_id}' step '{step_id}': {exc}"
            ) from exc
        return Approval.model_validate(dict(row))

    async def decide(
        self,
        *,
        approval_id: str,
        principal_id: str,
        decision: Decision,
        comment: str | None,
    ) -> Approval:
        """Records a real, attributable decision and, in the identical
        transaction, resumes the real instance it belongs to — see this
        module's own docstring for the full "resume happens only
        through this one write, never a timeout" reasoning.

        Guarded by ``WHERE status = 'pending'``: a second ``decide()``
        against an already-decided (or nonexistent) approval affects
        zero rows, raising :class:`ApprovalNotPendingError` rather than
        silently overwriting an already-recorded, attributable
        decision.
        """
        if not principal_id.strip():
            raise ValueError("decide() requires a real, non-empty, attributable principal_id")

        decided_at = datetime.now(UTC)
        try:
            async with self._engine.begin() as connection:
                approval_result = await connection.execute(
                    sa.update(approvals)
                    .where(approvals.c.approval_id == approval_id, approvals.c.status == "pending")
                    .values(
                        status=decision,
                        decided_by=principal_id,
                        decision_comment=comment,
                        decided_at=decided_at,
                    )
                    .returning(*approvals.columns)
                )
                approval_row = approval_result.mappings().one_or_none()
                if approval_row is None:
                    raise ApprovalNotPendingError(
                        f"approval '{approval_id}' is not pending — already decided, "
                        "or does not exist"
                    )

                workflow_id = approval_row["workflow_id"]
                instance_result = await connection.execute(
                    sa.update(workflow_instances)
                    .where(
                        workflow_instances.c.workflow_id == workflow_id,
                        workflow_instances.c.status
                        == WorkflowInstanceStatus.WAITING_FOR_HUMAN.value,
                    )
                    .values(
                        status=WorkflowInstanceStatus.RUNNING.value,
                        last_event_seq=workflow_instances.c.last_event_seq + 1,
                        updated_at=sa.func.now(),
                    )
                    .returning(
                        workflow_instances.c.last_event_seq, workflow_instances.c.definition_id
                    )
                )
                instance_row = instance_result.mappings().one_or_none()
                if instance_row is None:
                    raise WorkflowInstanceCreationError(
                        f"approval '{approval_id}' was decided, but workflow instance "
                        f"'{workflow_id}' was not genuinely waiting for a human — "
                        "its own state must have changed concurrently"
                    )

                await connection.execute(
                    sa.insert(workflow_events).values(
                        event_id=new_event_id(),
                        workflow_id=workflow_id,
                        seq=instance_row["last_event_seq"],
                        event_type=_STATE_TRANSITIONED_EVENT_TYPE,
                        schema_version=_STATE_TRANSITIONED_SCHEMA_VERSION,
                        payload={
                            "previousStatus": WorkflowInstanceStatus.WAITING_FOR_HUMAN.value,
                            "newStatus": WorkflowInstanceStatus.RUNNING.value,
                            "reason": f"approval '{approval_id}' decided '{decision}' "
                            f"by '{principal_id}'",
                        },
                        occurred_at=decided_at,
                    )
                )
                # The other half of the pair: whoever was told a decision
                # was needed is now told it was made, and by whom
                # (`P02-S07-M17-T05`). Same transaction as both the
                # decision and the resume above, so this event can never
                # describe a decision that did not commit — the exact
                # failure mode ADR-0012 exists to prevent, and one that
                # matters more here than anywhere else in the platform:
                # R-001 makes attributable human approval a permanent
                # hard rule, so an announced-but-uncommitted decision
                # would be a governance defect, not merely a stale
                # notification.
                await write_outbox_event(
                    connection,
                    event_type=_APPROVAL_DECIDED_EVENT_TYPE,
                    payload={
                        "approval_id": approval_id,
                        "workflow_id": workflow_id,
                        "decision": decision,
                        "decided_by": principal_id,
                    },
                )
        except sa.exc.SQLAlchemyError as exc:
            raise WorkflowInstanceCreationError(
                f"failed to record decision for approval '{approval_id}': {exc}"
            ) from exc

        return Approval.model_validate(dict(approval_row))


class ApprovalService:
    """The real authorization boundary in front of
    :meth:`ApprovalRepository.decide` — ``decide()`` itself only proves
    *attribution* (a real, non-blank ``principal_id``); this is where
    *authorization* is enforced (human_approval_points.md §7: "Security
    Manager ensures only authorized humans can approve"), reusing
    :class:`~ai_os_kernel.security_manager.models.Principal` and
    :func:`~ai_os_kernel.security_manager.approval_authorization.
    is_authorized_to_decide_approval` unchanged rather than inventing a
    parallel permission mechanism — see that module's own docstring for
    why this is a standalone check, not a
    :mod:`~ai_os_kernel.security_manager.permissions` addition.

    Deliberately not folded into :class:`SqlApprovalRepository` itself:
    that class is a pure persistence seam (its own docstring), and
    keeping the authorization gate here lets it be exercised, and
    proven refusing, without a real database (see
    ``tests/security/test_t10_unauthorized_approval.py``).

    **``role_grant_repository`` (``P03-S05-M14-T07``) is optional,
    defaulting to ``None`` — unchanged behaviour for every existing
    caller.** When supplied, real, persisted grants are unioned into
    ``principal.roles`` via
    :func:`~ai_os_kernel.security_manager.role_administration.resolve_effective_roles`
    (``P07-S02-M14-T02`` — the same real union this method used to
    inline directly, now shared with the general
    :func:`~ai_os_kernel.security_manager.dependencies.authenticate`
    path too, so a persisted grant of any of the five documented roles
    takes effect everywhere, not only here) before the unchanged
    :func:`~ai_os_kernel.security_manager.approval_authorization.
    is_authorized_to_decide_approval` check runs — the same "a caller
    without the real backing object gets the identical, existing
    behaviour" shape :func:`~ai_os_kernel.sdk_adapters.pack_context.
    build_pack_context`'s own optional capabilities already establish.
    """

    def __init__(
        self,
        approval_repository: ApprovalRepository,
        *,
        role_grant_repository: RoleGrantRepository | None = None,
    ) -> None:
        self._approval_repository = approval_repository
        self._role_grant_repository = role_grant_repository

    async def decide(
        self,
        *,
        approval_id: str,
        principal: Principal,
        decision: Decision,
        comment: str | None,
    ) -> Approval:
        approval = await self._approval_repository.get_by_id(approval_id=approval_id)
        if approval is None:
            raise ApprovalNotPendingError(f"approval '{approval_id}' does not exist")
        principal = await resolve_effective_roles(principal, self._role_grant_repository)
        if not is_authorized_to_decide_approval(principal, approval.approval_class):
            logger.warning(
                "security_manager.authorization_denied",
                principal_id=principal.principal_id,
                approval_id=approval_id,
                approval_class=approval.approval_class,
                required="admin or approver:" + approval.approval_class,
            )
            raise ApprovalNotAuthorizedError(
                f"principal '{principal.principal_id}' (roles: "
                f"{sorted(principal.roles)}) is not authorized to decide approval "
                f"'{approval_id}' (class '{approval.approval_class}') — requires the "
                f"'admin' role or 'approver:{approval.approval_class}'"
            )
        decided = await self._approval_repository.decide(
            approval_id=approval_id,
            principal_id=principal.principal_id,
            decision=decision,
            comment=comment,
        )
        logger.info(
            "security_manager.approval_decided",
            principal_id=principal.principal_id,
            approval_id=approval_id,
            approval_class=approval.approval_class,
            decision=decision,
        )
        return decided


class HumanApprovalStepExecutor:
    """Executes a ``human_approval``-type step by genuinely pausing the
    real workflow instance until a real, attributable decision is
    recorded — see this module's own docstring for the full design.

    Resolves which :class:`~ai_os_kernel.workflow_engine.models.
    HumanApprovalPoint` a step belongs to via the real
    :class:`~ai_os_kernel.workflow_engine.definition_catalog.
    WorkflowDefinitionCatalog` reader (``P02-S01-M05-T14``) — reading
    the instance's own ``definition_id``/``definition_version`` back
    and fetching the full, real definition, rather than a
    composition-injected mapping (the shape ``P02-S01-M05-T11``'s
    ``SubWorkflowStepExecutor`` used *before* a real reader existed).
    """

    def __init__(
        self,
        *,
        approval_repository: ApprovalRepository,
        instance_repository: WorkflowInstanceRepository,
        definition_catalog: WorkflowDefinitionCatalog,
    ) -> None:
        self._approval_repository = approval_repository
        self._instance_repository = instance_repository
        self._definition_catalog = definition_catalog

    async def execute(
        self,
        step: WorkflowStep,
        *,
        workflow_id: str | None = None,
        principal_permissions: frozenset[str] | None = None,
        workflow_permissions: frozenset[str] | None = None,
    ) -> dict[str, Any]:
        if step.type is not StepType.HUMAN_APPROVAL:
            raise ValueError(
                f"HumanApprovalStepExecutor cannot execute step '{step.id}' of type "
                f"'{step.type.value}' — it only handles human_approval steps"
            )
        if workflow_id is None:
            raise ValueError(
                f"human_approval step '{step.id}' requires a real workflow_id to "
                "resolve its own approval point and instance"
            )

        instance = await self._instance_repository.get_instance(workflow_id)
        if instance is None:
            raise ValueError(f"workflow instance '{workflow_id}' does not exist")

        definition = await self._definition_catalog.get(
            definition_id=instance.definition_id, version=instance.definition_version
        )
        if definition is None:
            raise ValueError(
                f"workflow instance '{workflow_id}' references definition "
                f"'{instance.definition_id}@{instance.definition_version}', which is not "
                "registered in the catalog"
            )
        point = next((p for p in definition.human_approval_points if p.id == step.id), None)
        if point is None:
            # Unreachable given WorkflowDefinition's own
            # `_human_approval_steps_reference_a_real_point` validator —
            # narrowed here only so a missing point fails loudly rather
            # than with an AttributeError, never silently.
            raise ValueError(
                f"step '{step.id}': no matching humanApprovalPoints entry in "
                f"'{definition.id}@{definition.version}'"
            )

        approval = await self._approval_repository.get_by_step(
            workflow_id=workflow_id, step_id=step.id
        )
        if approval is None:
            approval = await self._approval_repository.create_pending(
                workflow_id=workflow_id, step_id=step.id, point=point
            )

        if approval.status == "pending":
            raise HumanApprovalPendingError(
                f"human_approval step '{step.id}' is still awaiting a real decision "
                f"(approval '{approval.approval_id}')"
            )
        if approval.status == "approved":
            return {
                "decision": approval.status,
                "decidedBy": approval.decided_by,
                "decisionComment": approval.decision_comment,
                "decidedAt": approval.decided_at.isoformat() if approval.decided_at else None,
            }
        if approval.status == "rejected":
            raise HumanApprovalRejectedError(
                f"human_approval step '{step.id}' was rejected by "
                f"'{approval.decided_by}' (approval '{approval.approval_id}')"
            )
        raise ValueError(
            f"human_approval step '{step.id}': approval '{approval.approval_id}' has "
            f"status '{approval.status}', which this executor does not yet resolve — "
            "only 'approved'/'rejected' decisions are supported today"
        )
