"""Chains this pack's own four independently-proven agents —
Architecture, Build, Test, Documentation — into one real, declared
Workflow Engine pipeline: ``workflows/delivery_pipeline.yaml``, loaded
through the already-real, previously-unused
:class:`~ai_os_kernel.workflow_engine.loader.WorkflowDefinitionLoader`.
Not a new orchestration mechanism, no new Workflow Engine capability —
composition only, the identical shape
:func:`~ai_os_kernel.bootstrap._build_workflow_trigger` already
establishes for the Kernel's own demo workflow, reused here for a real
pack-owned one.

**The one genuinely missing piece this step builds: a real
step-output-to-next-step-input hand-off.** Each of this pack's four
agents was, until now, proven only independently — nothing in this
codebase had ever taken one step's real, persisted output and turned
it into the next step's real input. That piece is
:class:`~ai_os_kernel.context_manager.resolvers.WorkflowStepOutputResolver`
(a Kernel-level, reusable Context Manager resolver — see its own
docstring for the full design and why it lives there, not as a new
field on :class:`~ai_os_kernel.workflow_engine.models.WorkflowStep`).
This module owns only the *pipeline-specific* configuration of that
generic mechanism: which step reads which prior step's output, and the
one narrow, reviewed exception neither agent's own already-shipped
contract can satisfy on its own.

**The real data flow, and the one deliberate exception.**

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
  produces a Python file (see ``delivery_pipeline.yaml``'s own
  ``inputs``/this pack's own live-test instruction) — this transform is
  the one place that assumption is recorded, not silently relied upon.

  **``python_command`` is threaded through explicitly
  (``build_pipeline_trigger``/``build_pipeline_context_manager``'s own
  ``python_command`` parameter), not independently re-derived — a real,
  discovered bug this fixes, not a style preference.** An earlier
  version of this function called
  :func:`~ai_os_kernel.sandbox.default_executor.default_python_command`
  directly, on the (false, in general) assumption that "whichever
  backend the Build/Test agents themselves default to" always matches
  "whichever backend `AIOS_SANDBOX_BACKEND` currently names" — true only
  when *every* agent in the run is left to its own bare default. A
  caller that explicitly injects a specific ``sandbox=`` into Build/Test
  (any test wanting a fast, Docker-independent run, most concretely)
  breaks that assumption: the transform would derive ``python3``
  (matching the ambient env var) while the agent it hands the command to
  was actually constructed with ``LocalSubprocessSandbox`` (needing
  ``sys.executable``) — a real failure, caught by
  ``test_delivery_pipeline.py``'s own deterministic tier the first time
  it ran against a real daemon. The fix makes the *caller* — the one
  party that genuinely knows which backend every agent in this run was
  actually given — supply ``python_command`` once, consistently, rather
  than leaving two independent resolutions to coincidentally agree.
- ``documentation`` reads **both** ``build``'s and ``test``'s own
  outputs, merged (``build`` first, ``test`` second — ``test``'s own
  ``exitCode`` therefore wins over ``build``'s own same-named field,
  the write operation's exit code; a deliberate, declared merge order,
  never a computed value). The merged dict already contains every field
  the Documentation Agent's own contract needs
  (``workingDirectory``/``filePath``/``instruction`` from ``build``,
  ``passed``/``exitCode``/``output`` from ``test``) — no transform
  needed here at all.

**Why a real pack-owned YAML file, not a Python-constructed
``WorkflowDefinition`` (kernel/bootstrap.py's own demo's own choice).**
That demo's own comment is explicit about why it chose Python: "there
is no real pack directory for such a file to live in yet." One now
does — this is the first genuine consumer of
:class:`WorkflowDefinitionLoader` in this codebase's own history, not a
second, parallel way to build a definition.

**Why this composition lives in the pack, not in
``kernel/bootstrap.py``.** Every step this pipeline declares names a
pack-qualified agent id (``software-engineering/architecture``, etc.) —
real, working dispatch for these needs the pack's own
``SqlAgentRegistry``-resolvable agents, not the Kernel's own unrelated
demo agent. Kernel code importing pack-specific pipeline logic would
also invert this pack's own already-documented, one-way "pack imports
Kernel internals" compromise (``architecture.py``'s own docstring) —
this module imports Kernel internals, exactly like every other module
in this pack, never the reverse.
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

_PACK_ID = "software-engineering"
_DEFINITION_PATH = Path(__file__).resolve().parents[2] / "workflows" / "delivery_pipeline.yaml"

# Deliberately generous, not tuned — four real steps plus one final
# completion transition need five `advance()` calls; the identical
# "bound exists, not sized precisely" reasoning
# kernel/bootstrap.py's own demo trigger already uses for its own
# one-step workflow.
_WORKER_ID = "software-engineering-pipeline-trigger"
_LEASE_DURATION_SECONDS = 30
_MAX_ITERATIONS = 10


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
    "build": "architecture",
    "test": "build",
    "documentation": ["build", "test"],
}
_FIELD_SELECTORS = {"build": "content"}

# WorkflowStateResolver has no per-step concept of its own — it always
# contributes the workflow instance's own top-level `inputs`,
# unconditionally, for every step (this is correct, existing, unchanged
# Kernel behaviour; every other real caller of it has only ever had one
# agent step, so the question of scoping it never arose before this
# pipeline had four). Only the `architecture` step needs that
# contribution (the real `requirement` a caller supplied) — build/test/
# documentation each need exactly one clean payload from
# WorkflowStepOutputResolver alone; concatenating WorkflowStateResolver's
# own item alongside it would corrupt that payload (two JSON objects, or
# two texts, joined by DefaultContextManager/PromptedAgent's own "\n\n"
# flatten — genuinely discovered by this step's own manual end-to-end
# trace, not by inspection). _StepScopedResolver is the fix: a tiny,
# pipeline-owned wrapper restricting WorkflowStateResolver's own
# contribution to the one step that needs it, without changing
# WorkflowStateResolver itself at all.
_ARCHITECTURE_STEP_ID = "architecture"


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
    definition both the deterministic and the opt-in live full-chain
    tests drive; only the agent registry each supplies differs."""
    return WorkflowDefinitionLoader().load(_DEFINITION_PATH)


def build_pipeline_context_manager(
    repository: WorkflowInstanceRepository, *, python_command: tuple[str, ...] | None = None
) -> ContextManager:
    """The real step-output-to-next-step-input seam, configured for
    this pipeline specifically — see this module's own docstring for
    the full reasoning behind each entry. ``WorkflowStateResolver`` is
    included too, but scoped via ``_StepScopedResolver`` to the
    ``architecture`` step alone (which has no prior step to read from,
    and needs the workflow instance's own real ``requirement`` input
    instead) — see the ``_STEP_SOURCES`` comment above for why every
    other step must not also receive it.

    ``python_command``, when omitted, defaults to
    :func:`~ai_os_kernel.sandbox.default_executor.default_python_command`
    — correct for the real production path, where every agent this
    pipeline dispatches to resolves its own sandbox from that identical
    default. A caller that constructs its own agents with an explicit
    ``sandbox=`` override (any test wanting a specific, non-default
    backend) must pass the matching ``python_command`` here too — see
    this module's own docstring for the bug this closes.
    """
    resolved_python_command = python_command or default_python_command()
    return DefaultContextManager(
        [
            _StepScopedResolver(
                WorkflowStateResolver(repository), frozenset({_ARCHITECTURE_STEP_ID})
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
    ``SqlAgentRegistry`` (production, and this step's own opt-in live
    proof) or a deterministic, Echo-backed ``InMemoryAgentRegistry``
    keyed by this same pack-qualified id convention (this step's own
    deterministic full-chain test) — this function does not care which.

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
            pack_id=_PACK_ID,
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
