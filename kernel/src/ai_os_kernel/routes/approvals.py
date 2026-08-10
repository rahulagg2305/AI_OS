"""The real, Bearer-authenticated HTTP route (``P03-S03-M30-T06``) that
lets an authorized human submit a decision against a real, paused
workflow instance — closing the one disclosed gap
:mod:`ai_os_kernel.workflow_engine.human_approval`'s own module
docstring has named since it was built: "no HTTP route/Bearer-token
wiring for this call site."

**Authentication only at the route boundary — no flat permission
check, by design, not omission.** A first version of this route gated
on ``require_permission(APPROVAL_DECIDE)`` and was found genuinely
broken against a real request: a principal legitimately holding
*only* the class-scoped role ADR-0023 itself documents as the real
grant (``approver:approve-git-push``, never a separate bare
``approver``) was refused with a ``403`` before ever reaching real
authorization, because ``permissions_for_roles``'s own flat,
exact-string role lookup has no way to recognize a class-scoped role
as implying anything. Fixed by using
:func:`~ai_os_kernel.security_manager.authenticate` directly — real
Bearer/JWT verification, no permission check — and deferring the
entire authorization decision to
:class:`~ai_os_kernel.workflow_engine.human_approval.ApprovalService`,
which already gets this right via
:func:`~ai_os_kernel.security_manager.approval_authorization.
is_authorized_to_decide_approval`. See
:mod:`ai_os_kernel.security_manager.permissions`'s own docstring for
the fuller record of why a flat permission cannot express this.

**Resumption is real, synchronous, and scoped to the one real workflow
that can pause today — deliberately not the generic multi-instance
worker loop.** Investigation (``P03-S03-M30-T06``) found that loop's
own fixed composition (``bootstrap.py``'s ``_lifespan``) cannot
correctly advance a real ``se.delivery_pipeline`` instance at all — it
has no ``quality_gate``/``decision``/``human_approval`` executor, and
uses the platform demo's own ``agent_registry``, which does not know
this pack's agents. Rather than teach that system-wide loop
per-definition composition routing (real, but substantially larger
scope), ``bootstrap.py`` now excludes ``se.delivery_pipeline`` from its
discovery entirely (``WorkflowWorkerLoop``'s new
``exclude_definition_ids``), and this route itself calls
:func:`~ai_os_kernel.workflow_engine.delivery_pipeline.
resume_pipeline_after_approval` synchronously — the identical
one-shot-HTTP-call shape :mod:`ai_os_kernel.routes.delivery_pipeline`'s
own ``trigger`` route already uses, with the real,
credential/``git_service``-threaded registry
(``app.state.se_delivery_pipeline_agent_registry``), never the wrong
one. A decision against any other workflow's approval still records
correctly (real, attributable, authorized) but is not automatically
resumed — a real, disclosed, honest limit: no second real resumable
workflow exists yet to generalize this against.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.context_manager.resolvers import KnowledgeResolver
from ai_os_kernel.security_manager import (
    APPROVAL_READ,
    SecurityContext,
    authenticate,
    require_permission,
)
from ai_os_kernel.security_manager.errors import ApprovalNotAuthorizedError
from ai_os_kernel.security_manager.role_administration import SqlRoleGrantRepository
from ai_os_kernel.workflow_engine.advance_runner import WorkflowRunOutcome
from ai_os_kernel.workflow_engine.delivery_pipeline import (
    DEFINITION_ID as SE_DELIVERY_PIPELINE_DEFINITION_ID,
)
from ai_os_kernel.workflow_engine.delivery_pipeline import resume_pipeline_after_approval
from ai_os_kernel.workflow_engine.errors import ApprovalNotPendingError
from ai_os_kernel.workflow_engine.human_approval import (
    Approval,
    ApprovalService,
    SqlApprovalRepository,
)
from ai_os_kernel.workflow_engine.registry import AgentRegistry
from ai_os_kernel.workflow_engine.repository import WorkflowInstanceRepository

router = APIRouter(prefix="/api/v1", tags=["approvals"])


class DecideApprovalRequest(BaseModel):
    """Mirrors :class:`~ai_os_kernel.workflow_engine.human_approval.
    Decision` — only ``approved``/``rejected`` are real decisions today
    (``human_approval.py``'s own disclosed scope: no ``changes_requested``
    handling exists)."""

    decision: Literal["approved", "rejected"]
    comment: str | None = None


class DecideApprovalResponse(BaseModel):
    """The real, recorded decision, plus whether — and how — this
    specific workflow was genuinely resumed. ``resumed`` is ``False``
    whenever the decided workflow is not ``se.delivery_pipeline`` (the
    one real, wired resumption target today) — a real, honest signal,
    not a placeholder."""

    approval_id: str
    workflow_id: str
    decision: str
    decided_by: str
    resumed: bool
    resumed_outcome: WorkflowRunOutcome | None
    resumed_error: str | None


def _get_engine(request: Request) -> AsyncEngine:
    engine: AsyncEngine | None = getattr(request.app.state, "database_engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="workflow engine is not available")
    return engine


def _get_instance_repository(request: Request) -> WorkflowInstanceRepository:
    repository: WorkflowInstanceRepository | None = getattr(
        request.app.state, "workflow_instance_repository", None
    )
    if repository is None:
        raise HTTPException(status_code=503, detail="workflow engine is not available")
    return repository


class PendingApprovalsResponse(BaseModel):
    """api_architecture.md §6.2's own documented ``GET /api/v1/approvals``
    ("Pending approvals") — the real gap this module's own sibling,
    ``human_approval.py``, named as "real, separate, later work"
    (``P06-S03-M39-T02``). Deliberately unpaginated — see
    :meth:`~ai_os_kernel.workflow_engine.human_approval.
    SqlApprovalRepository.list_pending`'s own docstring for why the
    pending queue does not need the cursor-paginated envelope
    ``GET /workflows`` uses."""

    approvals: list[Approval]


@router.get("/approvals", response_model=PendingApprovalsResponse)
async def list_pending_approvals(
    request: Request,
    # Declared before `engine` — the identical "authorization resolves
    # before this route can reveal whether the Workflow Engine itself is
    # available" ordering `routes/workflows.py`'s own list route already
    # establishes.
    _security_context: SecurityContext = Depends(require_permission(APPROVAL_READ)),  # noqa: B008
) -> PendingApprovalsResponse:
    engine = _get_engine(request)
    approval_repository = SqlApprovalRepository(engine)
    pending = await approval_repository.list_pending()
    return PendingApprovalsResponse(approvals=pending)


@router.post(
    "/workflows/{workflow_id}/approvals/{approval_id}/decisions",
    response_model=DecideApprovalResponse,
)
async def decide_approval(
    request: Request,
    workflow_id: str,
    approval_id: str,
    body: DecideApprovalRequest,
    # FastAPI's own documented Depends(...) idiom, not the
    # mutable-default-argument bug B008 otherwise correctly flags — see
    # ai_os_kernel.routes.workflows's identical pattern.
    security_context: SecurityContext = Depends(authenticate),  # noqa: B008
) -> DecideApprovalResponse:
    engine = _get_engine(request)
    approval_repository = SqlApprovalRepository(engine)
    instance_repository = _get_instance_repository(request)

    approval = await approval_repository.get_by_id(approval_id=approval_id)
    if approval is None or approval.workflow_id != workflow_id:
        raise HTTPException(
            status_code=404,
            detail=f"no approval '{approval_id}' for workflow '{workflow_id}'",
        )

    # A real, persisted grant (P03-S05-M14-T07) is consulted here too —
    # not only the bearer token's own roles claim — via
    # ApprovalService's own optional role_grant_repository.
    approval_service = ApprovalService(
        approval_repository, role_grant_repository=SqlRoleGrantRepository(engine)
    )
    try:
        decided = await approval_service.decide(
            approval_id=approval_id,
            principal=security_context.principal,
            decision=body.decision,
            comment=body.comment,
        )
    except ApprovalNotAuthorizedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ApprovalNotPendingError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    instance = await instance_repository.get_instance(workflow_id)
    resumed_outcome: WorkflowRunOutcome | None = None
    resumed_error: str | None = None
    resumed = False
    if instance is not None and instance.definition_id == SE_DELIVERY_PIPELINE_DEFINITION_ID:
        agent_registry: AgentRegistry | None = getattr(
            request.app.state, "se_delivery_pipeline_agent_registry", None
        )
        knowledge_resolver: KnowledgeResolver | None = getattr(
            request.app.state, "se_delivery_pipeline_knowledge_resolver", None
        )
        if agent_registry is not None:
            result = await resume_pipeline_after_approval(
                engine, agent_registry, workflow_id, knowledge_resolver=knowledge_resolver
            )
            resumed = True
            resumed_outcome = result.outcome
            resumed_error = str(result.error) if result.error is not None else None

    return DecideApprovalResponse(
        approval_id=decided.approval_id,
        workflow_id=decided.workflow_id,
        decision=decided.status,
        decided_by=decided.decided_by or "",
        resumed=resumed,
        resumed_outcome=resumed_outcome,
        resumed_error=resumed_error,
    )
