"""Cost and Quality Views route (`P06-S03-M39-T03`, FR-094/FR-095).

See `ai_os_kernel.evaluation_engine.cost_and_quality_views` for the
real aggregation this route only exposes — this file adds no query
logic of its own, mirroring `routes/workflows.py`'s own
"a route reads a pre-built app.state collaborator" shape.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from ai_os_kernel.evaluation_engine.cost_and_quality_views import (
    CostAndQualityReport,
    CostAndQualityViews,
)
from ai_os_kernel.security_manager import EVALUATION_READ, SecurityContext, require_permission

router = APIRouter(prefix="/api/v1", tags=["evaluation"])


def _get_views(request: Request) -> CostAndQualityViews:
    views: CostAndQualityViews | None = getattr(request.app.state, "cost_and_quality_views", None)
    if views is None:
        raise HTTPException(status_code=503, detail="evaluation reporting is not available")
    return views


@router.get("/evaluation/cost-and-quality", response_model=CostAndQualityReport)
async def get_cost_and_quality_report(
    # FastAPI's own documented Depends(...) idiom, not the
    # mutable-default-argument bug B008 otherwise correctly flags — see
    # ai_os_kernel.routes.workflows for the same pattern.
    _security_context: SecurityContext = Depends(require_permission(EVALUATION_READ)),  # noqa: B008
    views: CostAndQualityViews = Depends(_get_views),  # noqa: B008
) -> CostAndQualityReport:
    return await views.get_report()
