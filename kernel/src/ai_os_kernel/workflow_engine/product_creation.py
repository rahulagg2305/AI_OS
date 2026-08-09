"""Real composition for ``se.product_creation`` (``P08-S02-M30-T01``) —
the buildable prefix of workflows.md §3's own documented graph; see
``capability_packs/software-engineering/workflows/product_creation.yaml``'s
own header comment for the full, disclosed reasoning behind stopping
at step 7 of 14 (a real, unbuilt `foreach` step type, not an oversight).

**Step 8 (`foreach implementation_plan.tasks -> sub_workflow
se.implement_task`) is real now too (2026-08-09), closing that gap.**
``StepType.FOREACH``/``ForeachStepExecutor`` exist as of this same step
(`P08-S02-M30-T01`); this module wires one real child composition —
:func:`~ai_os_kernel.workflow_engine.implement_task.
build_implement_task_instance_service`, the identical composition
:func:`~ai_os_kernel.workflow_engine.implement_task.
build_implement_task_trigger` itself uses — reused, not duplicated.
Steps 9-14 (nine parallel quality gates, documentation, release, the
final PR) remain genuinely unbuilt; this step's own scope is exactly
"give the plan artifact its first real consumer," not the full
documented graph.

**Composition is built fresh per real call, not once at module-import
time — a real, previously-latent gap this step found and fixed.**
:class:`~ai_os_kernel.workflow_engine.step_executor.
ForeachStepExecutor`/:class:`~ai_os_kernel.workflow_engine.
step_executor.SubWorkflowStepExecutor` both fix ``principal_id`` at
*construction* time, but no real production caller had ever wired
either one before this step — every existing use was a test building a
fixed, single-principal fixture. A real trigger built once at startup
and reused across many real calls (this module's own established
shape, mirroring ``delivery_pipeline.py``'s ``build_pipeline_trigger``)
cannot know the real, per-call ``principal_id`` in advance. Rather than
widen the ``StepExecutor`` Protocol (a bigger, cross-cutting change no
other step type needs), :func:`build_product_creation_trigger` now
builds the whole per-request stack — parent ``instance_service``/
``advance_runner`` *and* the child ``foreach_executor`` composition —
fresh inside its own ``trigger()`` closure, using that call's real
``principal_id``, so every child ``se.implement_task`` instance
``ForeachStepExecutor`` creates is genuinely attributed to the same
principal who triggered the parent run, never a placeholder.
:func:`resume_product_creation_after_approval` discovers that same real
``principal_id`` from the parent instance's own already-persisted
record (it never took one as a parameter) rather than inventing a
second identity for the same logical run.

Deliberately much smaller than
:mod:`ai_os_kernel.workflow_engine.delivery_pipeline`'s own
composition: no ``tool``/``decision`` steps exist directly in *this*
workflow's own 8 real steps (no ``ToolStepExecutor``/
``DecisionStepExecutor`` needed at this level — ``se.implement_task``
has its own, separate composition for those), no retry policy (nothing
here is configured to fail and retry), and this workflow's own two
``quality_gate`` steps are given a deliberately empty ``gate_sources``
— see the YAML's own header for why an unconfigured gate id resolving
as a real, honest pass is the documented, existing behaviour, not a
fabricated one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.context_manager.manager import ContextManager, DefaultContextManager
from ai_os_kernel.context_manager.models import ContextItem, ContextRequest, SourceType
from ai_os_kernel.context_manager.resolvers import (
    ContextSourceResolver,
    WorkflowStateResolver,
    WorkflowStepOutputResolver,
)
from ai_os_kernel.workflow_engine.advance_runner import (
    WorkflowAdvanceRunner,
    WorkflowRunResult,
    WorkflowTrigger,
)
from ai_os_kernel.workflow_engine.definition_catalog import SqlWorkflowDefinitionCatalog
from ai_os_kernel.workflow_engine.errors import WorkflowInvalidTransitionError
from ai_os_kernel.workflow_engine.human_approval import (
    HumanApprovalStepExecutor,
    SqlApprovalRepository,
)
from ai_os_kernel.workflow_engine.implement_task import (
    IMPLEMENT_TASK_MAX_ITERATIONS,
    build_implement_task_instance_service,
    load_implement_task_definition,
)
from ai_os_kernel.workflow_engine.lease import SqlWorkflowLeaseRepository, WorkflowLeaseService
from ai_os_kernel.workflow_engine.loader import WorkflowDefinitionLoader
from ai_os_kernel.workflow_engine.models import WorkflowDefinition
from ai_os_kernel.workflow_engine.quality_gate import QualityGateStepExecutor
from ai_os_kernel.workflow_engine.registry import AgentRegistry
from ai_os_kernel.workflow_engine.repository import (
    SqlWorkflowInstanceRepository,
    WorkflowInstanceRepository,
)
from ai_os_kernel.workflow_engine.run_manifest_recorder import SqlRunManifestRecorder
from ai_os_kernel.workflow_engine.service import WorkflowInstanceService
from ai_os_kernel.workflow_engine.step_executor import (
    AgentStepExecutor,
    DispatchingStepExecutor,
    ForeachStepExecutor,
    NoOpStepExecutor,
)

PACK_ID = "software-engineering"

_DEFINITION_PATH = (
    Path("capability_packs") / "software-engineering" / "workflows" / "product_creation.yaml"
)
_IMPLEMENT_TASK_DEFINITION_ID = "se.implement_task"

_WORKER_ID = "software-engineering-product-creation-trigger"
_LEASE_DURATION_SECONDS = 30
# Eight real steps (three agent, two quality_gate, two human_approval,
# one foreach) plus the final completion transition — well inside this
# bound, the identical "a real bound exists, not sized precisely"
# margin `delivery_pipeline.py`'s own `_MAX_ITERATIONS` already
# establishes. The foreach step's own child fan-out has its own,
# separate iteration budget (`IMPLEMENT_TASK_MAX_ITERATIONS`, imported
# from `implement_task.py` below) — running every child to completion
# does not consume this parent workflow's own iteration count at all.
_MAX_ITERATIONS = 15
# `implement-tasks`'s own real `maxFanOut` bound (ADR-0021: "foreach
# declares a maximum fan-out") lives in `product_creation.yaml` itself,
# not here — it is a `WorkflowStep`'s own declared field, read by
# `ForeachStepExecutor` from the loaded `WorkflowDefinition`, never a
# Python-side value this composition module could duplicate without
# the two silently drifting apart. See that YAML's own inline comment
# for the real, disclosed reasoning behind the number chosen.

# The real Context Manager wiring: `architecture` reads
# `requirements-analyst`'s own real `analysis` field;
# `technical-planner` reads `architecture`'s own real `content` field
# — the identical `_STEP_SOURCES`/`_FIELD_SELECTORS` shape and even the
# identical field names `delivery_pipeline.py`'s own
# `architecture`/`build` entries already establish (this pack's
# `architecture`/`build` agents share the exact same output field
# names as this workflow's `requirements-analyst`/`architecture`).
_STEP_SOURCES: dict[str, str | list[str]] = {
    "architecture": "requirements-analyst",
    "technical-planner": "architecture",
}
_FIELD_SELECTORS = {"architecture": "analysis", "technical-planner": "content"}
_REQUIREMENTS_ANALYST_STEP_ID = "requirements-analyst"


class _StepScopedResolver:
    """Identical to :mod:`ai_os_kernel.workflow_engine.delivery_pipeline`'s
    own private helper of the same name — restricts ``inner``'s
    contribution to one step (``requirements-analyst``, which has no
    prior step to read from and needs the workflow instance's own real
    ``specification`` input instead)."""

    def __init__(self, inner: ContextSourceResolver, step_ids: frozenset[str]) -> None:
        self.source_type: SourceType = inner.source_type
        self._inner = inner
        self._step_ids = step_ids

    async def resolve(self, request: ContextRequest) -> list[ContextItem]:
        if request.step_id not in self._step_ids:
            return []
        return await self._inner.resolve(request)


def load_product_creation_definition() -> WorkflowDefinition:
    """Loads and validates ``workflows/product_creation.yaml`` through
    the real :class:`WorkflowDefinitionLoader` — the identical
    canonical-load shape
    :func:`~ai_os_kernel.workflow_engine.delivery_pipeline.load_pipeline_definition`
    already establishes."""
    return WorkflowDefinitionLoader().load(_DEFINITION_PATH)


def build_product_creation_context_manager(
    repository: WorkflowInstanceRepository,
) -> ContextManager:
    """The real step-output-to-next-step-input seam for this workflow —
    see this module's own docstring for the ``_STEP_SOURCES``/
    ``_FIELD_SELECTORS`` reasoning."""
    resolvers: list[ContextSourceResolver] = [
        _StepScopedResolver(
            WorkflowStateResolver(repository), frozenset({_REQUIREMENTS_ANALYST_STEP_ID})
        ),
        WorkflowStepOutputResolver(
            repository, step_sources=_STEP_SOURCES, field_selectors=_FIELD_SELECTORS
        ),
    ]
    return DefaultContextManager(resolvers)


def _build_product_creation_composition(
    engine: AsyncEngine,
    agent_registry: AgentRegistry,
    *,
    principal_id: str,
    python_command: tuple[str, ...] | None,
) -> tuple[WorkflowInstanceService, WorkflowAdvanceRunner]:
    """The full real composition for one specific ``principal_id`` —
    parent ``instance_service`` *and* the child ``se.implement_task``
    fan-out ``ForeachStepExecutor`` needs at construction time. Built
    fresh per real call (see this module's own docstring for why
    ``principal_id`` cannot be fixed once at startup like every other
    piece of this composition) — mirrors
    :func:`~ai_os_kernel.workflow_engine.delivery_pipeline._build_pipeline_composition`'s
    own ``(instance_service, advance_runner)`` return shape, shared by
    both real callers below."""
    repository = SqlWorkflowInstanceRepository(engine)
    context_manager = build_product_creation_context_manager(repository)
    definition_catalog = SqlWorkflowDefinitionCatalog(engine)
    # A genuinely separate `WorkflowInstanceService`/`WorkflowAdvanceRunner`
    # pair drives each real child `se.implement_task` instance — the
    # identical `_make_child_service`/`child_runner` shape
    # `test_sub_workflow_step_execution.py` already establishes; both
    # wrap the *same* `implement_task_instance_service`, never two
    # different ones.
    implement_task_instance_service = build_implement_task_instance_service(
        engine, agent_registry, python_command=python_command
    )
    foreach_executor = ForeachStepExecutor(
        definitions={_IMPLEMENT_TASK_DEFINITION_ID: load_implement_task_definition()},
        instance_service=implement_task_instance_service,
        advance_runner=WorkflowAdvanceRunner(
            instance_service=implement_task_instance_service,
            lease_service=WorkflowLeaseService(SqlWorkflowLeaseRepository(engine)),
        ),
        repository=repository,
        pack_id=PACK_ID,
        principal_id=principal_id,
        lease_duration_seconds=_LEASE_DURATION_SECONDS,
        max_iterations=IMPLEMENT_TASK_MAX_ITERATIONS,
    )
    instance_service = WorkflowInstanceService(
        repository=repository,
        step_executor=DispatchingStepExecutor(
            agent_executor=AgentStepExecutor(agent_registry, context_manager=context_manager),
            tool_executor=NoOpStepExecutor(),
            default_executor=NoOpStepExecutor(),
            quality_gate_executor=QualityGateStepExecutor(repository, gate_sources={}),
            human_approval_executor=HumanApprovalStepExecutor(
                approval_repository=SqlApprovalRepository(engine),
                instance_repository=repository,
                definition_catalog=definition_catalog,
            ),
            foreach_executor=foreach_executor,
        ),
        definition_catalog=definition_catalog,
        run_manifest_recorder=SqlRunManifestRecorder(engine),
    )
    advance_runner = WorkflowAdvanceRunner(
        instance_service=instance_service,
        lease_service=WorkflowLeaseService(SqlWorkflowLeaseRepository(engine)),
    )
    return instance_service, advance_runner


def build_product_creation_trigger(
    engine: AsyncEngine,
    agent_registry: AgentRegistry,
    *,
    python_command: tuple[str, ...] | None = None,
) -> WorkflowTrigger:
    """Mirrors
    :func:`~ai_os_kernel.workflow_engine.delivery_pipeline.build_pipeline_trigger`'s
    own shape — real, ``engine``-backed persistence driving one
    ``WorkflowDefinition`` through create -> start -> run-to-completion.
    ``agent_registry`` is the one thing a caller must choose (a real
    ``SqlAgentRegistry`` or a deterministic ``InMemoryAgentRegistry``);
    ``python_command`` is forwarded to ``se.implement_task``'s own child
    composition (defaults to the real production sandbox's own command
    when omitted — see ``implement_task.py``'s own
    ``build_implement_task_context_manager``).

    **A returned ``WorkflowRunOutcome.WAITING_FOR_HUMAN`` is this
    trigger's own honest final answer for this call, not an error** —
    this workflow has two real Human Approval Points; resuming a
    specific paused instance after a real decision is the caller's own
    job (via :func:`resume_product_creation_after_approval`), the
    identical shape ``resume_pipeline_after_approval`` establishes for
    ``se.delivery_pipeline``.

    **The whole composition is built fresh inside this closure, per
    call — see this module's own docstring.** ``definition`` alone is
    loaded once, outside, since it carries no per-principal state.
    """
    definition = load_product_creation_definition()

    async def trigger(
        inputs: dict[str, Any],
        principal_id: str,
        *,
        principal_permissions: frozenset[str] | None = None,
    ) -> WorkflowRunResult:
        instance_service, advance_runner = _build_product_creation_composition(
            engine, agent_registry, principal_id=principal_id, python_command=python_command
        )
        instance = await instance_service.create_instance(
            definition=definition,
            inputs=inputs,
            principal_id=principal_id,
            pack_id=PACK_ID,
            principal_permissions=principal_permissions,
        )
        await instance_service.start(
            workflow_id=instance.workflow_id, reason="se.product_creation trigger"
        )
        return await advance_runner.run_to_completion(
            workflow_id=instance.workflow_id,
            definition=definition,
            worker_id=_WORKER_ID,
            lease_duration_seconds=_LEASE_DURATION_SECONDS,
            max_iterations=_MAX_ITERATIONS,
        )

    return trigger


async def resume_product_creation_after_approval(
    engine: AsyncEngine,
    agent_registry: AgentRegistry,
    *,
    workflow_id: str,
    python_command: tuple[str, ...] | None = None,
) -> WorkflowRunResult:
    """Re-enters an existing, paused instance after a real approval
    decision — mirrors
    :func:`~ai_os_kernel.workflow_engine.delivery_pipeline.resume_pipeline_after_approval`'s
    own shape, built from the identical composition
    :func:`build_product_creation_trigger` uses internally, so neither
    ever drifts from the other.

    **Discovers the real, already-persisted ``principal_id`` from the
    paused instance itself** — this function never took one as a
    parameter, and the child ``se.implement_task`` fan-out this resume
    may reach must be attributed to the same principal who originally
    triggered the parent run, never a second, invented identity for the
    same logical run.
    """
    probe_repository = SqlWorkflowInstanceRepository(engine)
    existing = await probe_repository.get_instance(workflow_id)
    if existing is None:
        raise WorkflowInvalidTransitionError(
            f"cannot resume se.product_creation workflow '{workflow_id}': no such instance"
        )

    _, advance_runner = _build_product_creation_composition(
        engine,
        agent_registry,
        principal_id=existing.principal_id,
        python_command=python_command,
    )
    definition = load_product_creation_definition()
    return await advance_runner.run_to_completion(
        workflow_id=workflow_id,
        definition=definition,
        worker_id=_WORKER_ID,
        lease_duration_seconds=_LEASE_DURATION_SECONDS,
        max_iterations=_MAX_ITERATIONS,
    )
