"""HTTP route for the Software Engineering pack's own real
``se.delivery_pipeline`` workflow (``POST /api/v1/workflows/se.delivery_pipeline``)
— the first pack-specific workflow trigger route in this codebase,
mirroring :mod:`ai_os_kernel.routes.workflows`'s own ``start_workflow``
shape exactly: the same ``Depends(require_permission(WORKFLOW_START))``
gate, the same synchronous run-to-completion + ``200`` response (this
codebase has no multi-instance worker loop yet — see that module's own
docstring for why ``200``, not the documented ``202``, is the honest
choice today), and the same ``app.state``-lookup-then-``503``-if-absent
pattern for a not-yet-available trigger.

**Why a dedicated route, not a ``definition_id`` field on the existing
``POST /api/v1/workflows``.** That route is hardcoded to one single
trigger (``app.state.trigger_prompted_agent_workflow``) with no
selector mechanism at all — adding one would be new, generic
multi-definition dispatch infrastructure, not "wire this one pipeline,"
and no second real workflow existed yet to justify building it before
this step. A second, sibling route — its own request/response DTOs,
its own ``app.state`` trigger attribute — is the smaller, honest step,
mirroring exactly how ``_build_workflow_trigger``/
``app.state.trigger_prompted_agent_workflow`` and
``build_pipeline_trigger``/``app.state.trigger_se_delivery_pipeline``
are already two separate, independent trigger closures in
``bootstrap.py``.

**The response includes the real ``documentationPath`` this pipeline
actually produces, unlike ``StartWorkflowResponse``'s own deliberately
generic shape.** ``se.delivery_pipeline`` has one real, known output
field (``documentationPath`` —
``ai_os_pack_software_engineering.workflows.models:PipelineOutput``) —
reading it back from the completed ``documentation`` step's own real,
persisted output and returning it directly is a real seam this
pipeline-specific route can justify (ADR-0004) that the
platform-generic ``/workflows`` route cannot, since it has no single
known workflow to specialize a response for.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ai_os_kernel.observability.logging import get_logger
from ai_os_kernel.security_manager import WORKFLOW_START, SecurityContext, require_permission
from ai_os_kernel.traceability_engine.errors import TraceabilityError
from ai_os_kernel.traceability_engine.link_writer import TraceLinkWriter
from ai_os_kernel.workflow_engine.advance_runner import WorkflowRunOutcome
from ai_os_kernel.workflow_engine.delivery_pipeline import record_documentation_traceability_link
from ai_os_kernel.workflow_engine.instance import WorkflowInstance
from ai_os_kernel.workflow_engine.repository import WorkflowInstanceRepository

router = APIRouter(prefix="/api/v1", tags=["delivery-pipeline"])

_logger = get_logger(__name__)

_DOCUMENTATION_STEP_ID = "documentation"

# The two outcomes in which the `documentation` step has genuinely run
# and persisted its output: a fully-completed run, and a run paused at
# the definition's own `approve-git-push` human-approval step (which
# sits *after* `documentation`). Reading `documentation_path` — and
# recording the produced-documentation trace link — in the paused case
# too is deliberate (product-owner decision, `P04-S02-M16-T04`): the
# documentation artifact really exists the moment that step completes,
# independent of the separate git-push approval still pending.
_DOCUMENTATION_PRODUCED_OUTCOMES = frozenset(
    {WorkflowRunOutcome.COMPLETED, WorkflowRunOutcome.WAITING_FOR_HUMAN}
)


class TriggerDeliveryPipelineRequest(BaseModel):
    """Mirrors ``capability_packs/software-engineering/workflows/delivery_pipeline.yaml``'s
    own declared ``inputs`` schema exactly
    (``ai_os_pack_software_engineering.workflows.models:PipelineInput``)."""

    requirement: str = Field(
        ...,
        description=(
            "The raw software requirement or ask to design, build, test, and document — "
            "analyzed and refined by Requirements Analyst before Architecture ever sees it."
        ),
    )
    specification: str | None = Field(
        default=None,
        description=(
            "An optional, additional structured Markdown specification (FR-030, "
            "`P03-S03-M30-T02`) — parsed into validated requirement items by "
            "Requirements Analyst. `requirement` stays required and unaffected; omitting "
            "this field changes nothing for any existing caller."
        ),
    )


class TriggerDeliveryPipelineResponse(BaseModel):
    """A reduced, JSON-safe projection of
    :class:`~ai_os_kernel.workflow_engine.advance_runner.WorkflowRunResult`
    — the identical shape :class:`~ai_os_kernel.routes.workflows.StartWorkflowResponse`
    already establishes — extended with ``documentation_path``, this
    pipeline's own real, known output field (``None`` unless the run
    genuinely completed and a real documentation artifact path was
    persisted)."""

    workflow_id: str
    outcome: WorkflowRunOutcome
    iterations: int
    error: str | None
    documentation_path: str | None
    """The real documentation file this run produced, or ``None``. Now
    populated for a ``waiting_for_human`` outcome too, not only
    ``completed`` (`P04-S02-M16-T04`): the definition's own
    ``approve-git-push`` human-approval step sits *after* ``documentation``,
    so a run paused there has genuinely produced the file already —
    reporting it is more honest than withholding it until the separate
    git-push approval lands. ``None`` for a run that never reached the
    ``documentation`` step (an early ``failed``)."""


async def _read_documentation_path(
    repository: WorkflowInstanceRepository, workflow_id: str
) -> str | None:
    steps = await repository.list_steps(workflow_id)
    documentation_outputs: dict[str, Any] | None = next(
        (s.outputs for s in steps if s.step_name == _DOCUMENTATION_STEP_ID and s.outputs), None
    )
    if documentation_outputs is None:
        return None
    path = documentation_outputs.get("documentationPath")
    return path if isinstance(path, str) else None


async def _record_documentation_link_best_effort(
    request: Request,
    workflow_id: str,
    last_instance: WorkflowInstance,
    documentation_path: str,
) -> None:
    """Record the real ``workflow_run --produced--> documentation`` link
    for this run — the Traceability Engine's first production write call
    site (``P04-S02-M16-T04``, risk register R-018).

    **Best-effort, and deliberately so.** By the time this runs, the
    pipeline has genuinely produced a real documentation file and the
    caller is about to return a real, successful response describing it.
    A traceability side-record is an observability artifact, not the
    run's primary deliverable — failing an already-successful pipeline
    response because a secondary link write hit a transient database
    error would be a real regression, so a :class:`TraceabilityError` is
    logged at ``warning`` and swallowed here rather than propagated. The
    catch is narrow on purpose: only the writer's own declared error
    type, never a bare ``Exception`` that could hide an unrelated bug.
    The happy path is proven by a real test, so a change that silently
    stops writing the link fails that test rather than passing quietly.

    A no-op when no ``trace_link_writer`` is wired (a degraded, no-engine
    composition) — the identical "unconfigured means the real feature
    does not run" shape every other optional ``app.state`` collaborator
    already uses.
    """
    writer: TraceLinkWriter | None = getattr(request.app.state, "trace_link_writer", None)
    if writer is None:
        return
    try:
        await record_documentation_traceability_link(
            writer,
            workflow_id=workflow_id,
            definition_id=last_instance.definition_id,
            definition_version=last_instance.definition_version,
            documentation_path=documentation_path,
        )
    except TraceabilityError:
        _logger.warning(
            "traceability.link_write_failed",
            workflow_id=workflow_id,
            documentation_path=documentation_path,
        )


@router.post("/workflows/se.delivery_pipeline", response_model=TriggerDeliveryPipelineResponse)
async def trigger_delivery_pipeline(
    request: Request,
    body: TriggerDeliveryPipelineRequest,
    # FastAPI's own documented Depends(...) idiom, not the
    # mutable-default-argument bug B008 otherwise correctly flags — see
    # ai_os_kernel.routes.workflows's identical pattern.
    security_context: SecurityContext = Depends(require_permission(WORKFLOW_START)),  # noqa: B008
) -> TriggerDeliveryPipelineResponse:
    trigger = getattr(request.app.state, "trigger_se_delivery_pipeline", None)
    if trigger is None:
        raise HTTPException(status_code=503, detail="se.delivery_pipeline is not available")

    trigger_inputs: dict[str, Any] = {"requirement": body.requirement}
    if body.specification is not None:
        trigger_inputs["specification"] = body.specification

    result = await trigger(trigger_inputs, security_context.principal.principal_id)

    documentation_path: str | None = None
    repository: WorkflowInstanceRepository | None = getattr(
        request.app.state, "workflow_instance_repository", None
    )
    if result.outcome in _DOCUMENTATION_PRODUCED_OUTCOMES and repository is not None:
        documentation_path = await _read_documentation_path(repository, result.workflow_id)

    if documentation_path is not None and result.last_instance is not None:
        await _record_documentation_link_best_effort(
            request, result.workflow_id, result.last_instance, documentation_path
        )

    return TriggerDeliveryPipelineResponse(
        workflow_id=result.workflow_id,
        outcome=result.outcome,
        iterations=result.iterations,
        error=str(result.error) if result.error is not None else None,
        documentation_path=documentation_path,
    )
