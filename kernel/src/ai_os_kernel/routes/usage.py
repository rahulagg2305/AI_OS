"""Usage routes (`P06-S01-M36-T04`) — api_architecture.md §6.4.

See :mod:`ai_os_kernel.evaluation_engine.token_usage_views` for the real
aggregation this route only exposes; this file adds no query logic of
its own, the identical "a route reads a pre-built app.state
collaborator" shape :mod:`ai_os_kernel.routes.evaluation` already uses.

**Only ``usage/tokens`` is here, and ``usage/cost`` is deliberately
absent.** §6.4 documents both, but the cost half is already answered:
``GET /api/v1/evaluation/cost-and-quality`` (``P06-S03-M39-T03``,
FR-095) returns exactly "cost by model/workflow/pack" from the same
``evaluation.llm_calls`` data. Adding a second path over the same
aggregation would be duplicate surface, not new capability — so the
divergence is recorded in ``api_architecture.md`` for a product-owner
decision (alias the documented path, or amend the document) rather than
resolved unilaterally here. The token half had no such equivalent: the
cost report carries no cache columns at all.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from ai_os_kernel.evaluation_engine.token_usage_views import TokenUsageReport, TokenUsageViews
from ai_os_kernel.security_manager import EVALUATION_READ, SecurityContext, require_permission

router = APIRouter(prefix="/api/v1", tags=["usage"])


def _get_views(request: Request) -> TokenUsageViews:
    views: TokenUsageViews | None = getattr(request.app.state, "token_usage_views", None)
    if views is None:
        raise HTTPException(status_code=503, detail="usage reporting is not available")
    return views


@router.get("/usage/tokens", response_model=TokenUsageReport)
async def get_token_usage(
    # FastAPI's own documented Depends(...) idiom, not the
    # mutable-default-argument bug B008 otherwise correctly flags — see
    # ai_os_kernel.routes.evaluation for the same pattern.
    _security_context: SecurityContext = Depends(require_permission(EVALUATION_READ)),  # noqa: B008
    views: TokenUsageViews = Depends(_get_views),  # noqa: B008
) -> TokenUsageReport:
    """Gated by the already-real ``evaluation:read`` — the same
    permission ``GET /gates/results``, the traceability reads and
    ``GET /evaluation/cost-and-quality`` all use. §5's own table names
    no dedicated usage permission, and this is read-only analytical
    reporting over the identical data, so no new permission string was
    invented."""
    return await views.get_token_usage()
