"""Chains the Software Engineering pack's own five independently-proven
agents — Requirements Analyst, Architecture, Build, Test, Documentation
— into one real, declared Workflow Engine pipeline:
``capability_packs/software-engineering/workflows/delivery_pipeline.yaml``,
loaded through :class:`~ai_os_kernel.workflow_engine.loader.WorkflowDefinitionLoader`.
Not a new orchestration mechanism, no new Workflow Engine capability —
composition only, the identical shape
:func:`~ai_os_kernel.bootstrap._build_workflow_trigger` already
establishes for the Kernel's own demo workflow, reused here for a real
pack-owned one.

**Promoted from ``tests/integration/_delivery_pipeline.py`` into real
Kernel code (this feature step, 2026-07-30) — not a second
implementation, the same one, relocated.** That module's own prior
home was itself a relocation (from the pack's own source tree,
``platform_sdk_v1_scope.md`` step 7): pack code must never import
``ai_os_kernel``, so this composition — which genuinely needs
``ai_os_kernel`` internals throughout — could never live there. Living
under ``tests/`` was correct only as long as the only real callers
*were* tests. Now a real HTTP route (:mod:`ai_os_kernel.routes.delivery_pipeline`)
needs the identical composition to trigger a real, production run —
and production code importing from ``tests/`` would be backwards, the
same class of layering mistake the step-7 relocation existed to avoid
in the other direction. This module is the one real, canonical home;
``bootstrap.py`` and both Delivery Pipeline integration tests
(``tests/integration/workflow_engine/test_delivery_pipeline.py``,
``tests/integration/sandbox/test_delivery_pipeline_docker.py``) all
import the same functions from here now, rather than each holding
its own copy.

**Still genuinely pack-specific, hardcoded knowledge, exactly like
``bootstrap.py``'s own demo composition already is.** This module
knows the real, fully-qualified agent ids
(``software-engineering/architecture``, etc.), the real workflow id
(``se.delivery_pipeline``), and the real step ids this one pack's one
workflow declares — the identical "no generic Capability-Manager-driven
pack/workflow discovery exists yet, so a real route needs real,
named knowledge instead of speculative generic infrastructure" shape
``bootstrap.py``'s own ``_build_demo_workflow_definition``/
``_DEMO_WORKFLOW_*`` constants already establish for the platform's
own demo agent. This is a documented, temporary compromise, not the
long-term shape — see ``capability_pack_contract.md``'s own note on
pack discovery being Capability Manager territory, not yet built.

**The one genuinely missing piece the original relocation-into-tests
step built: a real step-output-to-next-step-input hand-off.** Each of
this pack's five agents was, until then, proven only independently —
nothing in this codebase had ever taken one step's real, persisted
output and turned it into the next step's real input. That piece is
:class:`~ai_os_kernel.context_manager.resolvers.WorkflowStepOutputResolver`
(a Kernel-level, reusable Context Manager resolver — see its own
docstring for the full design and why it lives there, not as a new
field on :class:`~ai_os_kernel.workflow_engine.models.WorkflowStep`).
This module owns only the *pipeline-specific* configuration of that
generic mechanism: which step reads which prior step's output, and the
one narrow, reviewed exception neither agent's own already-shipped
contract can satisfy on its own.

**The real data flow, and the one deliberate exception.**

- ``architecture`` reads ``requirements-analyst``'s own output,
  field-selected to ``analysis`` — Requirements Analyst's sole output
  field, fed into Architecture's own ``{{context}}`` prompt variable as
  free text, exactly the same variable this pipeline's own raw
  ``requirement`` top-level input used to feed Architecture directly
  before this hand-off existed. Architecture's own prompt
  (``architecture_proposal.md``) needed no change at all: it already
  reads whatever real text arrives in ``{{context}}``, regardless of
  which real upstream step supplied it — the identical "forwards
  whatever arrives, unchanged" contract every ``PromptedAgent``-descended
  agent in this pack already has.
- ``build`` reads ``architecture``'s own output, field-selected to
  ``content`` — Architecture's sole output field, fed into Build's own
  ``{{context}}`` prompt variable as free text (Build's own contract
  never parses structured JSON out of its context — it forwards
  whatever `PromptedAgent` flattens into that one prompt variable,
  unchanged).
- ``test`` reads ``build``'s own output, whole (JSON — matching
  ``verification.py``'s own already-shipped ``_extract_payload()``
  convention). **The one deliberate exception**: the Test Agent's own
  contract requires ``runCommand``, a field the Build Agent's own
  output has no reason to produce (it never decides how its own file
  should be run — "the caller decides," per ``verification.py``'s own
  docstring). :func:`_make_run_generated_file_with_python` builds a
  real, tiny, reviewed Python callable — not a workflow-author-facing
  expression language — supplied as this one step's ``output_transforms``
  entry, deriving ``runCommand = [*python_command, filePath]`` from the
  now-known, real ``filePath`` Build actually produced. This pipeline's
  own Architecture step is the one that ultimately decides Build
  produces a Python file — this transform is the one place that
  assumption is recorded, not silently relied upon.

  **``python_command`` is threaded through explicitly
  (``build_pipeline_trigger``/``build_pipeline_context_manager``'s own
  ``python_command`` parameter), not independently re-derived.** A
  caller that constructs its own agents with an explicit ``sandbox=``
  override (any test wanting a specific, non-default backend) must
  pass the matching ``python_command`` here too, or the transform would
  derive an interpreter command that does not match the sandbox the
  agents were actually given.
- ``documentation`` reads **both** ``build``'s and ``test``'s own
  outputs, merged (``build`` first, ``test`` second — ``test``'s own
  ``exitCode`` therefore wins over ``build``'s own same-named field,
  the write operation's exit code; a deliberate, declared merge order,
  never a computed value). The merged dict already contains every field
  the Documentation Agent's own contract needs
  (``workingDirectory``/``filePath``/``instruction`` from ``build``,
  ``passed``/``exitCode``/``output`` from ``test``) — no transform
  needed here at all.

**A real, blocking quality_gate step now sits between ``test`` and
``documentation`` (added 2026-07-30) — the smallest real slice of the
still-0%-built Quality Gate Engine.** ``quality-gate-tests-pass``
(:class:`~ai_os_kernel.workflow_engine.quality_gate.QualityGateStepExecutor`,
configured via ``_GATE_SOURCES`` below) reads ``test``'s own real,
persisted ``passed`` field and raises
:class:`~ai_os_kernel.workflow_engine.errors.QualityGateFailedError`
when it is not ``True`` — halting the pipeline via the existing
``WorkflowAdvanceRunner.run_to_completion`` failure boundary, the same
one :class:`~ai_os_kernel.workflow_engine.errors.AgentOutputValidationError`
already uses, so a genuinely failing test run now stops the pipeline
before Documentation ever runs, rather than Documentation blindly
recording a failure it never actually blocked.

**Why a real pack-owned YAML file, not a Python-constructed
``WorkflowDefinition`` (``kernel/bootstrap.py``'s own demo's own
choice).** That demo's own comment is explicit about why it chose
Python: "there is no real pack directory for such a file to live in
yet." One now does — :class:`WorkflowDefinitionLoader` is the real,
existing mechanism for loading it, not a second, parallel way to build
a definition.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
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
from ai_os_kernel.workflow_engine.advance_runner import WorkflowAdvanceRunner, WorkflowRunResult
from ai_os_kernel.workflow_engine.definition_catalog import SqlWorkflowDefinitionCatalog
from ai_os_kernel.workflow_engine.lease import SqlWorkflowLeaseRepository, WorkflowLeaseService
from ai_os_kernel.workflow_engine.loader import WorkflowDefinitionLoader
from ai_os_kernel.workflow_engine.models import WorkflowDefinition
from ai_os_kernel.workflow_engine.quality_gate import QualityGateStepExecutor
from ai_os_kernel.workflow_engine.registry import AgentRegistry, InMemoryToolRegistry
from ai_os_kernel.workflow_engine.repository import (
    SqlWorkflowInstanceRepository,
    WorkflowInstanceRepository,
)
from ai_os_kernel.workflow_engine.service import WorkflowInstanceService
from ai_os_kernel.workflow_engine.step_executor import (
    AgentStepExecutor,
    DispatchingStepExecutor,
    NoOpStepExecutor,
    ToolStepExecutor,
)

PACK_ID = "software-engineering"

# Paths are resolved relative to the current working directory, matching
# every other path bootstrap.py resolves (see its own module docstring:
# "every documented way of running the Kernel ... starts the process
# from the repository root") — not `Path(__file__)`-relative, since this
# module now runs as real production code, not a relocatable test file.
_DEFINITION_PATH = (
    Path("capability_packs") / "software-engineering" / "workflows" / "delivery_pipeline.yaml"
)

# Deliberately generous, not tuned — six real steps (five agent steps
# plus the real quality_gate step, added 2026-07-30) plus one final
# completion transition need seven `advance()` calls; the identical
# "bound exists, not sized precisely" reasoning
# kernel/bootstrap.py's own demo trigger already uses for its own
# one-step workflow.
_WORKER_ID = "software-engineering-pipeline-trigger"
_LEASE_DURATION_SECONDS = 30
_MAX_ITERATIONS = 10

# The real quality_gate step's own source-step config (added
# 2026-07-30) — composition-level, per ai_os_kernel.workflow_engine.
# quality_gate.QualityGateStepExecutor's own docstring: which prior
# step's real output the gate reads is pipeline-specific knowledge, the
# same shape _STEP_SOURCES below already establishes for
# WorkflowStepOutputResolver, not a field on the step declaration
# itself. `quality-gate-tests-pass` reads `test`'s own real `passed`
# field — see delivery_pipeline.yaml's own comment on this step id.
_GATE_SOURCES: dict[str, str] = {"quality-gate-tests-pass": "test"}


def _make_run_generated_file_with_python(
    python_command: tuple[str, ...],
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Builds the one deliberate, narrow exception this module's own
    docstring names: a transform that derives a ``runCommand`` the Test
    Agent's own contract requires from the Build Agent's own real,
    now-known ``filePath`` — real Python code supplied to
    `WorkflowStepOutputResolver`'s own ``output_transforms`` seam, never
    a workflow-author-facing expression language declared in the YAML
    definition itself. ``python_command`` is bound once, by the caller
    that actually knows which sandbox backend this run's agents were
    given — see this module's own docstring for why that must not be
    re-derived independently."""

    def _run_generated_file_with_python(output: dict[str, Any]) -> dict[str, Any]:
        return {**output, "runCommand": [*python_command, output["filePath"]]}

    return _run_generated_file_with_python


_STEP_SOURCES: dict[str, str | list[str]] = {
    "architecture": "requirements-analyst",
    "build": "architecture",
    "test": "build",
    "documentation": ["build", "test"],
}
_FIELD_SELECTORS = {"architecture": "analysis", "build": "content"}

# WorkflowStateResolver has no per-step concept of its own — it always
# contributes the workflow instance's own top-level `inputs`,
# unconditionally, for every step (this is correct, existing, unchanged
# Kernel behaviour; every other real caller of it has only ever had one
# agent step, so the question of scoping it never arose before this
# pipeline had multiple). Only the `requirements-analyst` step needs
# that contribution (the real `requirement` a caller supplied) — every
# other step needs exactly one clean payload from
# WorkflowStepOutputResolver alone; concatenating WorkflowStateResolver's
# own item alongside it would corrupt that payload (two JSON objects, or
# two texts, joined by DefaultContextManager/PromptedAgent's own "\n\n"
# flatten). _StepScopedResolver is the fix: a tiny, pipeline-owned
# wrapper restricting WorkflowStateResolver's own contribution to the
# one step that needs it, without changing WorkflowStateResolver itself
# at all.
_REQUIREMENTS_ANALYST_STEP_ID = "requirements-analyst"


class _StepScopedResolver:
    """Delegates to ``inner`` only when ``request.step_id`` is one of
    ``step_ids``; returns no items for every other step. See this
    module's own ``_STEP_SOURCES`` comment above for why this pipeline
    needs it."""

    def __init__(self, inner: ContextSourceResolver, step_ids: frozenset[str]) -> None:
        self.source_type: SourceType = inner.source_type
        self._inner = inner
        self._step_ids = step_ids

    async def resolve(self, request: ContextRequest) -> list[ContextItem]:
        if request.step_id not in self._step_ids:
            return []
        return await self._inner.resolve(request)


def load_pipeline_definition() -> WorkflowDefinition:
    """Loads and validates ``workflows/delivery_pipeline.yaml`` through
    the real :class:`WorkflowDefinitionLoader` — the one canonical
    definition every real caller drives, production route and tests
    alike; only the agent registry each supplies differs."""
    return WorkflowDefinitionLoader().load(_DEFINITION_PATH)


def build_pipeline_context_manager(
    repository: WorkflowInstanceRepository, *, python_command: tuple[str, ...] | None = None
) -> ContextManager:
    """The real step-output-to-next-step-input seam, configured for
    this pipeline specifically — see this module's own docstring for
    the full reasoning behind each entry. ``WorkflowStateResolver`` is
    included too, but scoped via ``_StepScopedResolver`` to the
    ``requirements-analyst`` step alone (which has no prior step to read
    from, and needs the workflow instance's own real ``requirement``
    input instead) — see the ``_STEP_SOURCES`` comment above for why
    every other step must not also receive it.

    ``python_command``, when omitted, defaults to
    :func:`~ai_os_kernel.sandbox.default_executor.default_python_command`
    — correct for the real production path, where every agent this
    pipeline dispatches to resolves its own sandbox from that identical
    default. A caller that constructs its own agents with an explicit
    ``sandbox=`` override (any test wanting a specific, non-default
    backend) must pass the matching ``python_command`` here too.
    """
    resolved_python_command = python_command or default_python_command()
    return DefaultContextManager(
        [
            _StepScopedResolver(
                WorkflowStateResolver(repository), frozenset({_REQUIREMENTS_ANALYST_STEP_ID})
            ),
            WorkflowStepOutputResolver(
                repository,
                step_sources=_STEP_SOURCES,
                field_selectors=_FIELD_SELECTORS,
                output_transforms={
                    "test": _make_run_generated_file_with_python(resolved_python_command)
                },
            ),
        ]
    )


def build_pipeline_trigger(
    engine: AsyncEngine,
    agent_registry: AgentRegistry,
    *,
    python_command: tuple[str, ...] | None = None,
) -> Callable[[dict[str, Any], str], Awaitable[WorkflowRunResult]]:
    """Mirrors ``kernel/bootstrap.py``'s own ``_build_workflow_trigger``
    shape exactly — real, ``engine``-backed persistence driving one
    ``WorkflowDefinition`` through create -> start -> run-to-completion.
    ``agent_registry`` is the one thing a caller must choose: a real
    ``SqlAgentRegistry`` (production, via ``bootstrap.py``, and the
    opt-in live integration tests) or a deterministic, Echo-backed
    ``InMemoryAgentRegistry`` keyed by this same pack-qualified id
    convention (the deterministic integration tests) — this function
    does not care which.

    ``python_command`` is forwarded to :func:`build_pipeline_context_manager`
    unchanged — see that function's own docstring.
    """
    repository = SqlWorkflowInstanceRepository(engine)
    context_manager = build_pipeline_context_manager(repository, python_command=python_command)
    instance_service = WorkflowInstanceService(
        repository=repository,
        step_executor=DispatchingStepExecutor(
            agent_executor=AgentStepExecutor(agent_registry, context_manager=context_manager),
            tool_executor=ToolStepExecutor(InMemoryToolRegistry({})),
            default_executor=NoOpStepExecutor(),
            quality_gate_executor=QualityGateStepExecutor(repository, gate_sources=_GATE_SOURCES),
        ),
        definition_catalog=SqlWorkflowDefinitionCatalog(engine),
    )
    advance_runner = WorkflowAdvanceRunner(
        instance_service=instance_service,
        lease_service=WorkflowLeaseService(SqlWorkflowLeaseRepository(engine)),
    )
    definition = load_pipeline_definition()

    async def trigger(inputs: dict[str, Any], principal_id: str) -> WorkflowRunResult:
        instance = await instance_service.create_instance(
            definition=definition,
            inputs=inputs,
            principal_id=principal_id,
            pack_id=PACK_ID,
        )
        await instance_service.start(
            workflow_id=instance.workflow_id,
            reason="se.delivery_pipeline trigger",
        )
        return await advance_runner.run_to_completion(
            workflow_id=instance.workflow_id,
            definition=definition,
            worker_id=_WORKER_ID,
            lease_duration_seconds=_LEASE_DURATION_SECONDS,
            max_iterations=_MAX_ITERATIONS,
        )

    return trigger
