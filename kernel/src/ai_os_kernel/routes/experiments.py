"""api_architecture.md §6.3's own Experiments endpoints — the create+read
foundation (``P04-S01-M12-T12``): ``POST /api/v1/experiments`` (define),
``GET /api/v1/experiments`` (list), ``GET /api/v1/experiments/{id}``
(detail). The run/comparison endpoints (``POST /experiments/{id}/run``,
``GET /experiments/{id}/comparison``, ``.../runs``) remain a real,
disclosed later slice.

**Kernel-owned, pack-agnostic.** These routes are backed by the Kernel's
own :class:`~ai_os_kernel.evaluation_engine.experiment_repository.
SqlExperimentRepository` — see that module's own docstring for why
experiment validation lives in the platform, not the Benchmarking pack
(the Kernel hard-codes no pack knowledge). Building the *create* path
first is deliberate: read routes over the never-written
``evaluation.experiments`` table would have been the same "proven but
idle" hollowness the Traceability/Project-Intelligence steps just closed
(risk register R-018) — an experiment must be genuinely createable
before listing/reading it is worth anything.

**Permissions.** Reads use ``evaluation:read`` — ``permissions.py``'s own
comment already names "experiments" as one of that permission's grants
(every real role), the identical family ``GET /gates/results`` uses.
Create uses a new ``experiment:run`` permission: api_architecture.md §5's
own table documents ``experiment:read``/``experiment:run`` but the code
had neither as a constant (only the broader ``evaluation:read`` for the
read side); §5 names no separate "define" permission, so defining and
(the future) launching an experiment both fall under the one
``experiment:run`` write capability §5 provides, granted to the same
``operator``/``maintainer``/``admin`` roles §5's own row documents as
able to "run experiments" — reusing §5's documented vocabulary rather
than inventing a third string.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.evaluation_engine.experiment_repository import (
    ExperimentDefinitionInput,
    ExperimentDefinitionNotFoundError,
    ExperimentRecord,
    ExperimentValidationError,
    SqlExperimentRepository,
)
from ai_os_kernel.security_manager import (
    EVALUATION_READ,
    EXPERIMENT_RUN,
    SecurityContext,
    require_permission,
)
from ai_os_kernel.workflow_engine.definition_catalog import SqlWorkflowDefinitionCatalog

router = APIRouter(prefix="/api/v1", tags=["experiments"])


def _get_repository(request: Request) -> SqlExperimentRepository:
    # The identical `app.state.database_engine` accessor
    # `routes/gates.py`/`routes/traceability.py` already establish.
    engine: AsyncEngine | None = getattr(request.app.state, "database_engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="evaluation engine is not available")
    return SqlExperimentRepository(engine, definition_catalog=SqlWorkflowDefinitionCatalog(engine))


class ExperimentListResponse(BaseModel):
    """The documented collection envelope (``{"items": [...]}``), the same
    shape ``GET /gates/results`` uses. Unpaginated — experiments are a
    genuinely small, human-defined set (see the repository's own note)."""

    items: list[ExperimentRecord]


@router.post("/experiments", response_model=ExperimentRecord, status_code=201)
async def create_experiment(
    request: Request,
    body: ExperimentDefinitionInput,
    security_context: SecurityContext = Depends(require_permission(EXPERIMENT_RUN)),  # noqa: B008
) -> ExperimentRecord:
    repository = _get_repository(request)
    try:
        return await repository.create(body, created_by=security_context.principal.principal_id)
    except ExperimentValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ExperimentDefinitionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/experiments", response_model=ExperimentListResponse)
async def list_experiments(
    request: Request,
    _security_context: SecurityContext = Depends(require_permission(EVALUATION_READ)),  # noqa: B008
) -> ExperimentListResponse:
    repository = _get_repository(request)
    return ExperimentListResponse(items=await repository.list_all())


@router.get("/experiments/{experiment_id}", response_model=ExperimentRecord)
async def get_experiment(
    request: Request,
    experiment_id: str,
    _security_context: SecurityContext = Depends(require_permission(EVALUATION_READ)),  # noqa: B008
) -> ExperimentRecord:
    repository = _get_repository(request)
    record = await repository.get(experiment_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"no experiment with id '{experiment_id}'")
    return record
