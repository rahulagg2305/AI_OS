"""Real composition for ``se.implement_task`` (``P08-S02-M30-T02``) — the
real, buildable version of workflows.md §4's own documented graph; see
``capability_packs/software-engineering/workflows/implement_task.yaml``'s
own header comment for the full, disclosed reasoning behind its three
departures from that document (no ``backend-developer`` agent, no
``fs.apply_patch``/``test.run`` tool steps, no per-loop attempt counter).

Unlike :mod:`ai_os_kernel.workflow_engine.product_creation`, this
workflow has no ``human_approval`` steps (so no
``HumanApprovalStepExecutor``/``resume_*_after_approval`` needed) but
does have two real, genuinely-looping ``decision`` steps — this
module's own first real use of :class:`DecisionStepExecutor` outside
:mod:`ai_os_kernel.workflow_engine.delivery_pipeline`. ``quality-gate-
tests-pass`` is a real, *configured* gate (unlike ``product_creation``'s
own two disclosed no-ops): it reads ``qa-test``'s own real ``passed``
field, genuinely meaningful since both decision steps already only let
a run reach it once ``qa-test``/``code-review`` both reported real
success.
"""

from __future__ import annotations

from collections.abc import Callable
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
from ai_os_kernel.sandbox.default_executor import default_python_command
from ai_os_kernel.workflow_engine.advance_runner import (
    WorkflowAdvanceRunner,
    WorkflowRunResult,
    WorkflowTrigger,
)
from ai_os_kernel.workflow_engine.definition_catalog import SqlWorkflowDefinitionCatalog
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
    DecisionStepExecutor,
    DispatchingStepExecutor,
    NoOpStepExecutor,
)

PACK_ID = "software-engineering"

_DEFINITION_PATH = (
    Path("capability_packs") / "software-engineering" / "workflows" / "implement_task.yaml"
)

_WORKER_ID = "software-engineering-implement-task-trigger"
_LEASE_DURATION_SECONDS = 30

# A real, whole-run safety net, not a per-loop counter (the YAML's own
# header explains why no finer-grained one exists yet). Sized generously
# above the worst real cycle this graph can take — up to three steps per
# `tests-passed` retry, up to five per `no-blocking-findings` retry
# (which itself re-enters the `tests-passed` loop) — rather than tuned
# to any single scenario.
_MAX_ITERATIONS = 30

_STEP_SOURCES: dict[str, str | list[str]] = {"qa-test": "implement", "code-review": "implement"}
_IMPLEMENT_STEP_ID = "implement"
_GATE_SOURCES = {"quality-gate-tests-pass": "qa-test"}


def _make_run_command_from_file_path(
    python_command: tuple[str, ...],
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Identical shape to
    :func:`~ai_os_kernel.workflow_engine.delivery_pipeline._make_run_generated_file_with_python`
    — derives ``runCommand``, a field the Test Agent's own contract
    requires that the Build Agent's own output has no reason to
    produce, from Build's own real, now-known ``filePath``."""

    def _run_command(output: dict[str, Any]) -> dict[str, Any]:
        run_command = [*python_command, output["filePath"]]
        return {**output, "runCommand": run_command}

    return _run_command


class _StepScopedResolver:
    """Identical to :mod:`ai_os_kernel.workflow_engine.product_creation`'s
    own private helper of the same name — restricts ``inner``'s
    contribution to one step (``implement``, which has no prior step to
    read from and needs the workflow instance's own real ``task`` input
    instead)."""

    def __init__(self, inner: ContextSourceResolver, step_ids: frozenset[str]) -> None:
        self.source_type: SourceType = inner.source_type
        self._inner = inner
        self._step_ids = step_ids

    async def resolve(self, request: ContextRequest) -> list[ContextItem]:
        if request.step_id not in self._step_ids:
            return []
        return await self._inner.resolve(request)


def load_implement_task_definition() -> WorkflowDefinition:
    """Loads and validates ``workflows/implement_task.yaml`` through the
    real :class:`WorkflowDefinitionLoader` — the identical canonical-load
    shape
    :func:`~ai_os_kernel.workflow_engine.product_creation.load_product_creation_definition`
    already establishes."""
    return WorkflowDefinitionLoader().load(_DEFINITION_PATH)


def build_implement_task_context_manager(
    repository: WorkflowInstanceRepository,
    *,
    python_command: tuple[str, ...] | None = None,
) -> ContextManager:
    """The real step-output-to-next-step-input seam for this workflow —
    see this module's own docstring for the ``_STEP_SOURCES``/transform
    reasoning. ``python_command``, when omitted, defaults to
    :func:`~ai_os_kernel.sandbox.default_executor.default_python_command`
    — correct for the real production path; a caller constructing its
    own agents with an explicit ``sandbox=`` override must pass the
    matching ``python_command`` here too (the identical contract
    ``build_pipeline_context_manager`` already documents)."""
    resolved_python_command = python_command or default_python_command()
    resolvers: list[ContextSourceResolver] = [
        _StepScopedResolver(WorkflowStateResolver(repository), frozenset({_IMPLEMENT_STEP_ID})),
        WorkflowStepOutputResolver(
            repository,
            step_sources=_STEP_SOURCES,
            output_transforms={
                "qa-test": _make_run_command_from_file_path(resolved_python_command)
            },
        ),
    ]
    return DefaultContextManager(resolvers)


def build_implement_task_trigger(
    engine: AsyncEngine,
    agent_registry: AgentRegistry,
    *,
    python_command: tuple[str, ...] | None = None,
) -> WorkflowTrigger:
    """Mirrors
    :func:`~ai_os_kernel.workflow_engine.product_creation.build_product_creation_trigger`'s
    own shape — real, ``engine``-backed persistence driving one
    ``WorkflowDefinition`` through create -> start -> run-to-completion.
    No ``human_approval_executor`` is supplied (this workflow declares
    none); ``decision_executor``/``quality_gate_executor`` are, this
    module's own first real use of a genuinely-looping ``decision`` step
    outside :mod:`ai_os_kernel.workflow_engine.delivery_pipeline`."""
    repository = SqlWorkflowInstanceRepository(engine)
    context_manager = build_implement_task_context_manager(
        repository, python_command=python_command
    )
    definition_catalog = SqlWorkflowDefinitionCatalog(engine)
    instance_service = WorkflowInstanceService(
        repository=repository,
        step_executor=DispatchingStepExecutor(
            agent_executor=AgentStepExecutor(agent_registry, context_manager=context_manager),
            tool_executor=NoOpStepExecutor(),
            default_executor=NoOpStepExecutor(),
            quality_gate_executor=QualityGateStepExecutor(repository, gate_sources=_GATE_SOURCES),
            decision_executor=DecisionStepExecutor(repository),
        ),
        definition_catalog=definition_catalog,
        run_manifest_recorder=SqlRunManifestRecorder(engine),
    )
    advance_runner = WorkflowAdvanceRunner(
        instance_service=instance_service,
        lease_service=WorkflowLeaseService(SqlWorkflowLeaseRepository(engine)),
    )
    definition = load_implement_task_definition()

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
            workflow_id=instance.workflow_id, reason="se.implement_task trigger"
        )
        return await advance_runner.run_to_completion(
            workflow_id=instance.workflow_id,
            definition=definition,
            worker_id=_WORKER_ID,
            lease_duration_seconds=_LEASE_DURATION_SECONDS,
            max_iterations=_MAX_ITERATIONS,
        )

    return trigger
