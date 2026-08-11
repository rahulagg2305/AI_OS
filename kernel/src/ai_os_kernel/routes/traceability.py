"""api_architecture.md §6.6's own documented Traceability read routes —
``GET /api/v1/traceability/impact/{id}`` ("Impact analysis") and
``GET /api/v1/traceability/coverage`` ("Gaps, e.g. reqs w/o tests").

These close the *read* half of the Traceability Engine's own "proven
but idle" gap (risk register R-018): `P04-S02-M16-T04` gave the engine
its first real production *writer* (`routes/delivery_pipeline.py` now
records a real ``workflow_run --produced--> documentation`` link), so
there is genuinely something to read — a route over a permanently-empty
table would have been the same hollow shape this thread is closing.
Each route is a thin read over an already-real, already-tested query
(`traceability_engine.impact_query.find_affected_artifacts` /
`coverage_query.find_uncovered_requirements`), the identical
"expose an already-real reader through a thin route" shape
``GET /api/v1/gates/results`` established — no new query logic here.

**``impact/{id}`` carries the artifact's ``external_id`` in the path
and its ``artifact_type`` as a required query parameter.** The real
query identifies an artifact by the ``(artifact_type, external_id)``
pair (`ids.compute_artifact_key` hashes both — two different types
sharing one ``external_id`` are genuinely different artifacts), but
§6.6 documents a single ``{id}`` path segment. Rather than deviate to
two path segments, ``{id}`` is the ``external_id`` and ``artifact_type``
is a required query param — a real, disclosed shape choice, the same
"honor the documented path, name the extra dimension explicitly" call
made elsewhere (e.g. ``POST /api/v1/packs``'s own disclosed addition).
Defaulting ``artifact_type`` would be a hidden assumption, so it is
required, not optional.

**``traceability/query`` (the raw link graph) is deliberately not built
here** — its shape is a real, separate design decision (`P04-S02-M16-T05`
names it explicitly); impact and coverage are the two routes with an
already-real query behind them.

Gated by ``evaluation:read`` — no dedicated ``traceability:read``
permission is documented anywhere (§5's table, authentication_
authorization.md §4.2), and a traceability impact/coverage report is
read-only analytical reporting over run-produced data, the identical
family ``EVALUATION_READ`` already covers for ``GET /gates/results``
(granted to every real role). Reusing it rather than inventing a new
permission string mirrors that route's own already-accepted decision.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.security_manager import EVALUATION_READ, SecurityContext, require_permission
from ai_os_kernel.traceability_engine.coverage_query import find_uncovered_requirements
from ai_os_kernel.traceability_engine.impact_query import find_affected_artifacts
from ai_os_kernel.traceability_engine.models import TraceArtifact

router = APIRouter(prefix="/api/v1", tags=["traceability"])


def _get_engine(request: Request) -> AsyncEngine:
    # The identical `app.state.database_engine` accessor
    # `routes/gates.py`/`routes/agents.py` already establish.
    engine: AsyncEngine | None = getattr(request.app.state, "database_engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="traceability engine is not available")
    return engine


class TraceArtifactListResponse(BaseModel):
    """The documented collection envelope (``{"items": [...]}``), the
    same real shape ``GET /gates/results`` uses. Deliberately unpaginated:
    both the impact set (artifacts reachable from one real artifact) and
    the coverage set (uncovered requirements) are genuinely small,
    bounded results at this codebase's own scale — the identical "small,
    bounded collection stays unpaginated" reasoning ``GET /approvals``
    (the pending queue) already uses, not §9's cursor envelope."""

    items: list[TraceArtifact]


@router.get("/traceability/impact/{external_id}", response_model=TraceArtifactListResponse)
async def get_impact(
    request: Request,
    external_id: str,
    artifact_type: str = Query(...),
    _security_context: SecurityContext = Depends(require_permission(EVALUATION_READ)),  # noqa: B008
) -> TraceArtifactListResponse:
    engine = _get_engine(request)
    affected = await find_affected_artifacts(
        engine, artifact_type=artifact_type, external_id=external_id
    )
    return TraceArtifactListResponse(items=affected)


@router.get("/traceability/coverage", response_model=TraceArtifactListResponse)
async def get_coverage(
    request: Request,
    _security_context: SecurityContext = Depends(require_permission(EVALUATION_READ)),  # noqa: B008
) -> TraceArtifactListResponse:
    engine = _get_engine(request)
    uncovered = await find_uncovered_requirements(engine)
    return TraceArtifactListResponse(items=uncovered)
