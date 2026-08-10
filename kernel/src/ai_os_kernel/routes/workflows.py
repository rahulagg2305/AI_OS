"""The Workflow Engine's HTTP routes (api_architecture.md §6.1):
``POST /api/v1/workflows`` (the authenticated write, fronting the
composition root's ``app.state.trigger_prompted_agent_workflow``), the
cursor-paginated collection route ``GET /api/v1/workflows``, and four
read-only instance routes — ``GET /api/v1/workflows/{id}``,
``.../steps``, ``.../events``, ``.../run_manifest`` — all reusing
the same ``WorkflowInstanceRepository`` read accessors
(:meth:`~ai_os_kernel.workflow_engine.repository.WorkflowInstanceRepository.get_instance`/
:meth:`~ai_os_kernel.workflow_engine.repository.WorkflowInstanceRepository.list_steps`/
:meth:`~ai_os_kernel.workflow_engine.repository.WorkflowInstanceRepository.list_events`/
:meth:`~ai_os_kernel.workflow_engine.repository.WorkflowInstanceRepository.list_instances`)
the Workflow Engine itself already had (or, for ``list_instances``,
gained this step with no new persistence concept — see that method's
own docstring), via ``app.state.workflow_instance_repository`` (built
in :mod:`ai_os_kernel.bootstrap`, see its module docstring).

**The write route is deliberately narrower than the full documented
contract.** §6.1 documents ``definition_id``/``definition_version``/
``experiment_id`` request fields, an ``Idempotency-Key`` header, and a
``202`` fire-and-forget response naming an instance the caller polls
for status. None of that exists here: there is exactly one real
workflow definition (``platform.prompted_agent_smoke_test``, see
``bootstrap.py``), no experiment support, no idempotency-key store, and
— because there is still no multi-instance worker loop (a standing,
already-documented gap) — the trigger itself runs the instance to
completion synchronously before returning. Returning ``202`` for work
that has, in fact, already finished by the time the handler returns
would misrepresent what this endpoint does; this returns ``200`` with
the real, structured outcome instead — a deliberate, documented
reduction, not an oversight.

**The read routes return the real domain models directly**
(:class:`~ai_os_kernel.workflow_engine.instance.WorkflowInstance`,
:class:`~ai_os_kernel.workflow_engine.step_record.WorkflowStepRecord`,
:class:`~ai_os_kernel.workflow_engine.event_record.WorkflowEventRecord`)
— unlike ``StartWorkflowResponse`` below, none of these three carry a
field (a raw exception, an internal-only shape) that needs filtering
before crossing the API boundary, so no separate response DTO is
invented for them (ADR-0004: a seam is justified when it does
something a direct return does not). The `/steps`/`/events` routes
return the complete list, not the cursor-paginated shape §9 documents
for collections generally — a per-instance history is bounded by that
one instance's own execution, unlike the top-level collection below,
so cursor pagination there would be premature. A ``workflow_id`` naming
no real instance returns ``404`` from all three instance-scoped routes
— a plain, unguarded repository read that returns nothing is not the
same as "the Workflow Engine is unavailable" (``503``, when there is no
repository constructed at all).

**``GET /workflows`` is cursor-paginated (api_architecture.md §9),
never offset-paginated** — the collection grows continuously, and an
offset would skip or duplicate a row inserted between two page
requests, exactly the failure mode §9 rules offset out for. The cursor
is an opaque, base64-encoded JSON envelope around a
:class:`~ai_os_kernel.workflow_engine.repository.WorkflowListCursor`
(``created_at`` + ``workflow_id``, the repository's own keyset —
encoding it is this module's job, comparing it is the repository's).
Deliberately no ``status``/``definition_id``/``created_after`` query
filters — §5's explicit filter examples — and no free-form query DSL:
the approved framing for this step is a *correct list endpoint*, not
search; a filtered list is a distinct, later step layered on the same
cursor mechanism.

**Updated (2026-08-10, `P06-S01-M36-T04`): ``GET .../run_manifest`` and
``GET /workflow_definitions`` are real too** — the two routes §6.1's
own text above still named missing. Both reuse an existing recorder's
own seam, extended with one new read method each
(``SqlRunManifestRecorder.get_by_workflow_id``;
``SqlWorkflowDefinitionCatalog.list_all``) — no new persistence
concept, the identical "repository already has the seam, just no HTTP
caller yet" shape ``list_instances``/`GET /approvals/history` both
already established. ``workflow_definitions`` is deliberately
unpaginated (a genuinely small, bounded set — one row per real,
distinct definition version a pack ever declares, not per run).

**Updated (2026-08-10, later step): ``POST .../cancel`` is real too —
the last of §6.1's own routes, and workflow_engine.md §7's
``cancelled`` state, genuinely reached for the first time.** Gated by a
new ``workflow:control`` permission (authentication_authorization.md
§4.2's own documented row, granted identically to ``workflow:start``:
``operator``/``maintainer``/``admin``). See
:meth:`~ai_os_kernel.workflow_engine.repository.
SqlWorkflowInstanceRepository.cancel`'s own docstring for the real,
disclosed scope this stops short of: prevents future re-discovery by
the worker loop, does not forcibly interrupt an already-in-flight
step.

**Updated (``P03-S05-M14-T09``): ``start_workflow`` now forwards
``security_context.permissions`` into ``trigger()``, not only
``.principal.principal_id``.** Previously this real, computed
``SecurityContext`` was built and then discarded past the
``require_permission`` gate — the exact gap
:mod:`ai_os_kernel.security_manager.narrowing`'s own docstring long
disclosed ("``SecurityContext`` is never threaded into resolution").
This one call site now captures it once, at trigger time, into the new
``workflow_instances.principal_permissions`` column; every later
``AgentStepExecutor``/``ToolStepExecutor`` resolution for this instance
narrows against it — see :mod:`ai_os_kernel.workflow_engine.registry`'s
own docstring for the resolution-time enforcement and
:mod:`ai_os_kernel.workflow_engine.service`'s ``create_instance`` for
why a snapshot, not a live object, is what travels past this request.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.security_manager import (
    WORKFLOW_CONTROL,
    WORKFLOW_READ,
    WORKFLOW_START,
    SecurityContext,
    require_permission,
)
from ai_os_kernel.workflow_engine.advance_runner import WorkflowRunOutcome
from ai_os_kernel.workflow_engine.definition_catalog import SqlWorkflowDefinitionCatalog
from ai_os_kernel.workflow_engine.errors import WorkflowInvalidTransitionError
from ai_os_kernel.workflow_engine.event_record import WorkflowEventRecord
from ai_os_kernel.workflow_engine.instance import WorkflowInstance
from ai_os_kernel.workflow_engine.models import WorkflowDefinition
from ai_os_kernel.workflow_engine.repository import WorkflowInstanceRepository, WorkflowListCursor
from ai_os_kernel.workflow_engine.run_manifest_recorder import (
    SqlRunManifestRecorder,
    StoredRunManifest,
)
from ai_os_kernel.workflow_engine.step_record import WorkflowStepRecord

router = APIRouter(prefix="/api/v1", tags=["workflows"])

# api_architecture.md §9's own example (`?limit=50&cursor=…`) — the
# default, not a hardcoded response shape; a caller can always ask for
# a different limit up to _MAX_LIST_LIMIT.
_DEFAULT_LIST_LIMIT = 50
_MAX_LIST_LIMIT = 100


class StartWorkflowRequest(BaseModel):
    """Deliberately just ``inputs`` — see module docstring for the
    fields the full documented contract has that this does not yet."""

    inputs: dict[str, Any] = Field(default_factory=dict)


class StartWorkflowResponse(BaseModel):
    """A reduced, JSON-safe projection of
    :class:`~ai_os_kernel.workflow_engine.advance_runner.WorkflowRunResult`
    — not that model itself, since its ``last_instance``/``error`` fields
    carry internal shapes (a full ``WorkflowInstance``, a raw exception
    object) that are not this endpoint's documented response and should
    not cross the API boundary unfiltered."""

    workflow_id: str
    outcome: WorkflowRunOutcome
    iterations: int
    error: str | None


@router.post("/workflows", response_model=StartWorkflowResponse)
async def start_workflow(
    request: Request,
    body: StartWorkflowRequest,
    # FastAPI's own documented Depends(...) idiom, not the
    # mutable-default-argument bug B008 otherwise correctly flags — see
    # ai_os_kernel.security_manager.dependencies for the same pattern.
    security_context: SecurityContext = Depends(require_permission(WORKFLOW_START)),  # noqa: B008
) -> StartWorkflowResponse:
    trigger = getattr(request.app.state, "trigger_prompted_agent_workflow", None)
    if trigger is None:
        raise HTTPException(status_code=503, detail="workflow engine is not available")

    result = await trigger(
        body.inputs,
        security_context.principal.principal_id,
        principal_permissions=security_context.permissions,
    )
    return StartWorkflowResponse(
        workflow_id=result.workflow_id,
        outcome=result.outcome,
        iterations=result.iterations,
        error=str(result.error) if result.error is not None else None,
    )


def _get_repository(request: Request) -> WorkflowInstanceRepository:
    repository: WorkflowInstanceRepository | None = getattr(
        request.app.state, "workflow_instance_repository", None
    )
    if repository is None:
        raise HTTPException(status_code=503, detail="workflow engine is not available")
    return repository


def _get_engine(request: Request) -> AsyncEngine:
    # The identical `app.state.database_engine` accessor
    # `routes/approvals.py`'s own `_get_engine` already establishes —
    # `run_manifests` has no repository-level seam of its own yet
    # (`SqlRunManifestRecorder` is constructed directly, mirroring
    # `SqlApprovalRepository`'s own on-demand construction there).
    engine: AsyncEngine | None = getattr(request.app.state, "database_engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="workflow engine is not available")
    return engine


async def _get_instance_or_404(
    repository: WorkflowInstanceRepository, workflow_id: str
) -> WorkflowInstance:
    instance = await repository.get_instance(workflow_id)
    if instance is None:
        raise HTTPException(status_code=404, detail=f"no workflow instance with id '{workflow_id}'")
    return instance


def _encode_cursor(cursor: WorkflowListCursor) -> str:
    payload = {"created_at": cursor.created_at.isoformat(), "workflow_id": cursor.workflow_id}
    return base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")


def _decode_cursor(raw: str) -> WorkflowListCursor:
    try:
        payload = json.loads(base64.urlsafe_b64decode(raw.encode("ascii")))
        return WorkflowListCursor(
            created_at=datetime.fromisoformat(payload["created_at"]),
            workflow_id=payload["workflow_id"],
        )
    except Exception as exc:
        # A cursor is opaque client-supplied input, not a value this
        # service ever hands back malformed — any failure decoding it
        # (bad base64, invalid JSON, a missing/mistyped field) is the
        # same "malformed request" condition, not worth distinguishing
        # by exception type.
        raise HTTPException(status_code=400, detail="invalid cursor") from exc


class WorkflowListResponse(BaseModel):
    """api_architecture.md §9's documented collection envelope:
    ``{"items": [...], "next_cursor": "…" | null}``."""

    items: list[WorkflowInstance]
    next_cursor: str | None


@router.get("/workflows", response_model=WorkflowListResponse)
async def list_workflows(
    limit: int = Query(default=_DEFAULT_LIST_LIMIT, gt=0, le=_MAX_LIST_LIMIT),
    cursor: str | None = Query(default=None),
    # Declared before `repository` — see get_workflow's identical
    # comment: authentication/authorization must resolve before this
    # route can reveal whether the Workflow Engine itself is available.
    _security_context: SecurityContext = Depends(require_permission(WORKFLOW_READ)),  # noqa: B008
    repository: WorkflowInstanceRepository = Depends(_get_repository),  # noqa: B008
) -> WorkflowListResponse:
    before = _decode_cursor(cursor) if cursor is not None else None

    # One extra row requested, never returned: its presence is exactly
    # what distinguishes "there is a next page" from "this was the last
    # page", without a separate COUNT query.
    instances = await repository.list_instances(limit=limit + 1, before=before)
    has_more = len(instances) > limit
    page = instances[:limit]

    next_cursor = None
    if has_more and page:
        last = page[-1]
        next_cursor = _encode_cursor(
            WorkflowListCursor(created_at=last.created_at, workflow_id=last.workflow_id)
        )

    return WorkflowListResponse(items=page, next_cursor=next_cursor)


class CancelWorkflowRequest(BaseModel):
    """Deliberately just an optional ``reason`` — no documented request
    body shape exists for this route beyond api_architecture.md §6.1's
    own one-line table entry. Mirrors ``DecideApprovalRequest``'s own
    "required body, optional field inside" shape (``routes/approvals.py``)
    rather than inventing a second, "body itself is optional"
    convention nothing else in this API uses."""

    reason: str | None = None


@router.post("/workflows/{workflow_id}/cancel", response_model=WorkflowInstance, status_code=202)
async def cancel_workflow(
    workflow_id: str,
    body: CancelWorkflowRequest,
    # Declared before `repository` — the identical "authorization
    # resolves before this route can reveal whether the Workflow Engine
    # itself is available" ordering every other route here establishes.
    _security_context: SecurityContext = Depends(require_permission(WORKFLOW_CONTROL)),  # noqa: B008
    repository: WorkflowInstanceRepository = Depends(_get_repository),  # noqa: B008
) -> WorkflowInstance:
    """api_architecture.md §6.1's own documented ``POST
    /api/v1/workflows/{id}/cancel`` ("Request cancellation") —
    workflow_engine.md §7's ``cancelled`` state, genuinely reached for
    the first time. See :meth:`~ai_os_kernel.workflow_engine.repository.
    SqlWorkflowInstanceRepository.cancel`'s own docstring for the real,
    disclosed scope: this prevents the instance from ever being
    *discovered* again by the worker loop, it does not forcibly
    interrupt an already-in-flight step a worker is mid-executing right
    now. `404` if the workflow never existed; `409` if it exists but is
    already in a terminal state (``completed``/``failed``/``cancelled``)
    or a real, declared-but-unreached one (never both conflated with
    "not found")."""
    await _get_instance_or_404(repository, workflow_id)
    try:
        return await repository.cancel(
            workflow_id=workflow_id, reason=body.reason or "cancelled via API"
        )
    except WorkflowInvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/workflows/{workflow_id}", response_model=WorkflowInstance)
async def get_workflow(
    workflow_id: str,
    # Declared before `repository` so FastAPI resolves it first: a
    # request must be authenticated/authorized before this route reveals
    # anything about whether the Workflow Engine itself is available —
    # otherwise an unauthenticated caller could get 503 instead of 401.
    _security_context: SecurityContext = Depends(require_permission(WORKFLOW_READ)),  # noqa: B008
    repository: WorkflowInstanceRepository = Depends(_get_repository),  # noqa: B008
) -> WorkflowInstance:
    return await _get_instance_or_404(repository, workflow_id)


@router.get("/workflows/{workflow_id}/steps", response_model=list[WorkflowStepRecord])
async def get_workflow_steps(
    workflow_id: str,
    _security_context: SecurityContext = Depends(require_permission(WORKFLOW_READ)),  # noqa: B008
    repository: WorkflowInstanceRepository = Depends(_get_repository),  # noqa: B008
) -> list[WorkflowStepRecord]:
    await _get_instance_or_404(repository, workflow_id)
    return await repository.list_steps(workflow_id)


@router.get("/workflows/{workflow_id}/events", response_model=list[WorkflowEventRecord])
async def get_workflow_events(
    workflow_id: str,
    _security_context: SecurityContext = Depends(require_permission(WORKFLOW_READ)),  # noqa: B008
    repository: WorkflowInstanceRepository = Depends(_get_repository),  # noqa: B008
) -> list[WorkflowEventRecord]:
    await _get_instance_or_404(repository, workflow_id)
    return await repository.list_events(workflow_id)


@router.get("/workflows/{workflow_id}/run_manifest", response_model=StoredRunManifest)
async def get_workflow_run_manifest(
    request: Request,
    workflow_id: str,
    _security_context: SecurityContext = Depends(require_permission(WORKFLOW_READ)),  # noqa: B008
    repository: WorkflowInstanceRepository = Depends(_get_repository),  # noqa: B008
) -> StoredRunManifest:
    """api_architecture.md §6.1's own documented ``GET
    /api/v1/workflows/{id}/run_manifest`` ("Reproducibility manifest")
    — ADR-0022's own complete pinned-conditions bundle.
    ``SqlRunManifestRecorder.record`` is real production-wired
    (``bootstrap.py``/``delivery_pipeline.py``) and writes exactly once
    per genuinely completed run; a `404` here means either the
    workflow itself does not exist, or it exists but has not
    (yet, or ever) genuinely completed — a plain, honest absence, never
    a fabricated empty manifest."""
    await _get_instance_or_404(repository, workflow_id)
    engine = _get_engine(request)
    manifest = await SqlRunManifestRecorder(engine).get_by_workflow_id(workflow_id=workflow_id)
    if manifest is None:
        raise HTTPException(
            status_code=404, detail=f"no run manifest recorded for workflow '{workflow_id}'"
        )
    return manifest


@router.get("/workflow_definitions", response_model=list[WorkflowDefinition])
async def list_workflow_definitions(
    request: Request,
    _security_context: SecurityContext = Depends(require_permission(WORKFLOW_READ)),  # noqa: B008
) -> list[WorkflowDefinition]:
    """api_architecture.md §6.1's own documented ``GET
    /api/v1/workflow_definitions`` ("Registered definitions") — every
    real, registered ``catalog.workflow_definitions`` row, reusing
    :meth:`~ai_os_kernel.workflow_engine.definition_catalog.
    SqlWorkflowDefinitionCatalog.get`'s own lossless reconstruction via
    the new :meth:`~ai_os_kernel.workflow_engine.definition_catalog.
    SqlWorkflowDefinitionCatalog.list_all`. Deliberately unpaginated,
    like ``GET /approvals`` (the pending queue) — a real, disclosed,
    narrower shape than §9's cursor envelope: a workflow *definition*
    registers once per real, distinct version a pack ever declares, a
    genuinely small, bounded collection, unlike the *instances* the
    plain ``GET /workflows`` route lists."""
    engine = _get_engine(request)
    return await SqlWorkflowDefinitionCatalog(engine).list_all()
