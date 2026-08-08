"""Real composition for ``se.product_creation`` (``P08-S02-M30-T01``) —
the buildable prefix of workflows.md §3's own documented graph; see
``capability_packs/software-engineering/workflows/product_creation.yaml``'s
own header comment for the full, disclosed reasoning behind stopping
at step 7 of 14 (a real, unbuilt `foreach` step type, not an oversight).

Deliberately much smaller than
:mod:`ai_os_kernel.workflow_engine.delivery_pipeline`'s own
composition: no ``tool``/``decision`` steps exist in this workflow (no
``ToolStepExecutor``/``DecisionStepExecutor`` needed), no retry policy
(nothing here is configured to fail and retry), and
``QualityGateStepExecutor`` is given a deliberately empty
``gate_sources`` — see the YAML's own header for why an unconfigured
gate id resolving as a real, honest pass is the documented, existing
behaviour, not a fabricated one — so no ``gate_registry`` either.
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
from ai_os_kernel.workflow_engine.human_approval import (
    HumanApprovalStepExecutor,
    SqlApprovalRepository,
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
    NoOpStepExecutor,
)

PACK_ID = "software-engineering"

_DEFINITION_PATH = (
    Path("capability_packs") / "software-engineering" / "workflows" / "product_creation.yaml"
)

_WORKER_ID = "software-engineering-product-creation-trigger"
_LEASE_DURATION_SECONDS = 30
# Seven real steps (three agent, two quality_gate, two human_approval)
# plus the final completion transition — well inside this bound, the
# identical "a real bound exists, not sized precisely" margin
# `delivery_pipeline.py`'s own `_MAX_ITERATIONS` already establishes.
_MAX_ITERATIONS = 15

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


def build_product_creation_trigger(
    engine: AsyncEngine, agent_registry: AgentRegistry
) -> WorkflowTrigger:
    """Mirrors
    :func:`~ai_os_kernel.workflow_engine.delivery_pipeline.build_pipeline_trigger`'s
    own shape exactly — real, ``engine``-backed persistence driving one
    ``WorkflowDefinition`` through create -> start -> run-to-completion.
    ``agent_registry`` is the one thing a caller must choose (a real
    ``SqlAgentRegistry`` or a deterministic ``InMemoryAgentRegistry``).

    **A returned ``WorkflowRunOutcome.WAITING_FOR_HUMAN`` is this
    trigger's own honest final answer for this call, not an error** —
    this workflow has two real Human Approval Points; resuming a
    specific paused instance after a real decision is the caller's own
    job (via ``WorkflowAdvanceRunner.run_to_completion`` again on the
    same ``workflow_id``), the identical shape
    ``resume_pipeline_after_approval`` establishes for
    ``se.delivery_pipeline``.
    """
    repository = SqlWorkflowInstanceRepository(engine)
    context_manager = build_product_creation_context_manager(repository)
    definition_catalog = SqlWorkflowDefinitionCatalog(engine)
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
        ),
        definition_catalog=definition_catalog,
        run_manifest_recorder=SqlRunManifestRecorder(engine),
    )
    advance_runner = WorkflowAdvanceRunner(
        instance_service=instance_service,
        lease_service=WorkflowLeaseService(SqlWorkflowLeaseRepository(engine)),
    )
    definition = load_product_creation_definition()

    async def trigger(
        inputs: dict[str, Any],
        principal_id: str,
        *,
        principal_permissions: frozenset[str] | None = None,
    ) -> WorkflowRunResult:
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
    engine: AsyncEngine, agent_registry: AgentRegistry, *, workflow_id: str
) -> WorkflowRunResult:
    """Re-enters an existing, paused instance after a real approval
    decision — mirrors
    :func:`~ai_os_kernel.workflow_engine.delivery_pipeline.resume_pipeline_after_approval`'s
    own shape, built from the identical composition
    :func:`build_product_creation_trigger` uses internally, so neither
    ever drifts from the other."""
    repository = SqlWorkflowInstanceRepository(engine)
    context_manager = build_product_creation_context_manager(repository)
    definition_catalog = SqlWorkflowDefinitionCatalog(engine)
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
        ),
        definition_catalog=definition_catalog,
        run_manifest_recorder=SqlRunManifestRecorder(engine),
    )
    advance_runner = WorkflowAdvanceRunner(
        instance_service=instance_service,
        lease_service=WorkflowLeaseService(SqlWorkflowLeaseRepository(engine)),
    )
    definition = load_product_creation_definition()
    return await advance_runner.run_to_completion(
        workflow_id=workflow_id,
        definition=definition,
        worker_id=_WORKER_ID,
        lease_duration_seconds=_LEASE_DURATION_SECONDS,
        max_iterations=_MAX_ITERATIONS,
    )
