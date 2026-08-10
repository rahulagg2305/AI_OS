"""api_architecture.md §6.4's own documented ``GET /api/v1/gates/results``
("Gate results (filterable)") — real, cursor-paginated (§9's own
blanket "every collection" rule: real gate results accumulate for the
platform's whole life, one row per real evaluation, unlike the
genuinely bounded collections this codebase leaves unpaginated
elsewhere).

Reuses a new :meth:`~ai_os_kernel.workflow_engine.gate_result_recorder.
SqlGateResultRecorder.list_all` — a plain, unguarded read over the same
recorder :class:`~ai_os_kernel.workflow_engine.service.
WorkflowInstanceService` already writes through after a real
``quality_gate`` step resolves (module 15's own first real data
producer). The keyset is `result_id` alone — a real, prefixed ULID,
itself time-sortable by construction, no separate timestamp column
needed.

Gated by ``evaluation:read`` — authentication_authorization.md §4.2's
own `viewer` grant explicitly names "gate results" alongside
"workflows"/"experiments," and `permissions.py`'s own
``EVALUATION_READ`` already exists for exactly this, granted to every
real role. `GET /api/v1/gates/trends` ("Pass/fail over time") remains
genuinely unbuilt — `gate_results` has no timestamp column at all, so
a real trend-over-time view needs its own, separate design decision
this route does not attempt.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.security_manager import EVALUATION_READ, SecurityContext, require_permission
from ai_os_kernel.workflow_engine.gate_result_recorder import (
    GateResultRecord,
    SqlGateResultRecorder,
)

router = APIRouter(prefix="/api/v1", tags=["gates"])

# api_architecture.md §9's own example (`?limit=50&cursor=…`) — the
# same default/max `GET /workflows` already uses.
_DEFAULT_LIST_LIMIT = 50
_MAX_LIST_LIMIT = 100


def _get_engine(request: Request) -> AsyncEngine:
    # The identical `app.state.database_engine` accessor
    # `routes/approvals.py`/`routes/workflows.py`/`routes/agents.py`
    # already establish.
    engine: AsyncEngine | None = getattr(request.app.state, "database_engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="workflow engine is not available")
    return engine


class GateResultListResponse(BaseModel):
    """api_architecture.md §9's documented collection envelope
    (``{"items": [...], "next_cursor": "…" | null}``), the same real
    shape ``GET /workflows`` already uses."""

    items: list[GateResultRecord]
    next_cursor: str | None


@router.get("/gates/results", response_model=GateResultListResponse)
async def list_gate_results(
    request: Request,
    workflow_id: str | None = Query(default=None),
    limit: int = Query(default=_DEFAULT_LIST_LIMIT, gt=0, le=_MAX_LIST_LIMIT),
    cursor: str | None = Query(default=None),
    _security_context: SecurityContext = Depends(require_permission(EVALUATION_READ)),  # noqa: B008
) -> GateResultListResponse:
    engine = _get_engine(request)
    recorder = SqlGateResultRecorder(engine)

    # One extra row requested, never returned — the same "presence
    # alone signals a next page, no separate COUNT" trick
    # `list_workflows` already uses.
    results = await recorder.list_all(workflow_id=workflow_id, limit=limit + 1, before=cursor)
    has_more = len(results) > limit
    page = results[:limit]

    next_cursor = page[-1].result_id if has_more and page else None
    return GateResultListResponse(items=page, next_cursor=next_cursor)
