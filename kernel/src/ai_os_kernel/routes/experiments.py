"""api_architecture.md §6.3's own Experiments endpoints:
``POST /api/v1/experiments`` (define, ``P04-S01-M12-T12``),
``GET /api/v1/experiments`` (list), ``GET /api/v1/experiments/{id}``
(detail), and ``POST /api/v1/experiments/{id}/run`` (run,
``P04-S01-M12-T13``). The comparison endpoints
(``GET /experiments/{id}/comparison``, ``.../runs``) remain a real,
disclosed later slice.

**Kernel-owned, pack-agnostic.** These routes are backed by the Kernel's
own :class:`~ai_os_kernel.evaluation_engine.experiment_repository.
SqlExperimentRepository` — see that module's own docstring for why
experiment validation lives in the platform, not the Benchmarking pack
(the Kernel hard-codes no pack knowledge). The create path was built
first, deliberately: read routes over the never-written
``evaluation.experiments`` table would have been the same "proven but
idle" hollowness the Traceability/Project-Intelligence steps closed
(risk register R-018). ``POST /experiments/{id}/run`` now closes the same
gap for ``evaluation.experiment_runs``: it is the first production caller
of the already-tested run writer, via the synchronous
:class:`~ai_os_kernel.evaluation_engine.experiment_run_orchestrator.
ExperimentRunOrchestrator` — see that module for the execution model and
its disclosed limitations.

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

from ai_os_kernel.context_manager.manager import ContextManager
from ai_os_kernel.evaluation_engine.experiment_repository import (
    ExperimentDefinitionInput,
    ExperimentDefinitionNotFoundError,
    ExperimentRecord,
    ExperimentValidationError,
    SqlExperimentRepository,
)
from ai_os_kernel.evaluation_engine.experiment_run_orchestrator import (
    ExperimentNotFoundError,
    ExperimentNotRunnableError,
    ExperimentRunOrchestrator,
    ExperimentRunSummary,
)
from ai_os_kernel.llm_gateway.errors import LLMProviderError
from ai_os_kernel.llm_gateway.router import Router
from ai_os_kernel.sdk_adapters.experiment_run_recorder_adapter import SqlExperimentRunRecorder
from ai_os_kernel.security_manager import (
    EVALUATION_READ,
    EXPERIMENT_RUN,
    SecurityContext,
    require_permission,
)
from ai_os_kernel.workflow_engine.advance_runner import WorkflowAdvanceRunner
from ai_os_kernel.workflow_engine.definition_catalog import SqlWorkflowDefinitionCatalog
from ai_os_kernel.workflow_engine.lease import SqlWorkflowLeaseRepository, WorkflowLeaseService
from ai_os_kernel.workflow_engine.registry import AgentRegistry, InMemoryToolRegistry
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from ai_os_kernel.workflow_engine.service import WorkflowInstanceService
from ai_os_kernel.workflow_engine.step_executor import (
    AgentStepExecutor,
    DispatchingStepExecutor,
    NoOpStepExecutor,
    ToolStepExecutor,
)

router = APIRouter(prefix="/api/v1", tags=["experiments"])


def _get_repository(request: Request) -> SqlExperimentRepository:
    # The identical `app.state.database_engine` accessor
    # `routes/gates.py`/`routes/traceability.py` already establish.
    engine: AsyncEngine | None = getattr(request.app.state, "database_engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="evaluation engine is not available")
    return SqlExperimentRepository(engine, definition_catalog=SqlWorkflowDefinitionCatalog(engine))


def _get_run_orchestrator(request: Request) -> ExperimentRunOrchestrator:
    """Compose the synchronous experiment-run orchestrator from the real,
    ``_lifespan``-built collaborators on ``app.state``. Mirrors
    ``bootstrap._build_workflow_trigger``'s own composition shape (the
    same ``AgentStepExecutor`` over ``app.state.agent_registry`` +
    ``app.state.context_manager``), plus the model router the run needs to
    resolve each variant's alias. Any missing collaborator degrades to a
    clear 503, the identical "a real dependency is genuinely absent"
    handling ``_get_repository`` already uses for the engine."""
    engine: AsyncEngine | None = getattr(request.app.state, "database_engine", None)
    agent_registry: AgentRegistry | None = getattr(request.app.state, "agent_registry", None)
    context_manager: ContextManager | None = getattr(request.app.state, "context_manager", None)
    model_router: Router | None = getattr(request.app.state, "model_router", None)
    if engine is None or agent_registry is None or context_manager is None or model_router is None:
        raise HTTPException(status_code=503, detail="experiment-run engine is not available")

    instance_repository = SqlWorkflowInstanceRepository(engine)
    definition_catalog = SqlWorkflowDefinitionCatalog(engine)
    instance_service = WorkflowInstanceService(
        repository=instance_repository,
        step_executor=DispatchingStepExecutor(
            agent_executor=AgentStepExecutor(agent_registry, context_manager=context_manager),
            tool_executor=ToolStepExecutor(InMemoryToolRegistry({})),
            default_executor=NoOpStepExecutor(),
        ),
        definition_catalog=definition_catalog,
    )
    advance_runner = WorkflowAdvanceRunner(
        instance_service=instance_service,
        lease_service=WorkflowLeaseService(SqlWorkflowLeaseRepository(engine)),
    )
    return ExperimentRunOrchestrator(
        experiment_repository=SqlExperimentRepository(
            engine, definition_catalog=definition_catalog
        ),
        definition_catalog=definition_catalog,
        instance_repository=instance_repository,
        advance_runner=advance_runner,
        router=model_router,
        run_recorder=SqlExperimentRunRecorder(engine),
    )


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


@router.post("/experiments/{experiment_id}/run", response_model=ExperimentRunSummary)
async def run_experiment(
    request: Request,
    experiment_id: str,
    security_context: SecurityContext = Depends(require_permission(EXPERIMENT_RUN)),  # noqa: B008
) -> ExperimentRunSummary:
    """Synchronously run a defined experiment: one real workflow per
    variant x replicate, each recorded to ``evaluation.experiment_runs``
    (``P04-S01-M12-T13``). ``EXPERIMENT_RUN`` is §5's own write capability
    — the same permission ``POST /experiments`` uses. A missing experiment
    is 404; an experiment this synchronous slice cannot run (its
    ``variables`` do not vary exactly the ``model`` dimension, or an alias
    has no configured route) is 422 — a caller-fixable definition problem,
    not a server fault."""
    orchestrator = _get_run_orchestrator(request)
    try:
        return await orchestrator.run(
            experiment_id, principal_id=security_context.principal.principal_id
        )
    except ExperimentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ExperimentNotRunnableError, LLMProviderError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
