"""Workflow Engine — the sole orchestrator.

Owns workflow definitions, instance state, step scheduling, retries,
Quality Gate invocation, and Human Approval Points. Agents never
communicate directly with each other or with other workflows; all
coordination passes through here (ADR-0005).

See docs/03_architecture/kernel/workflow_engine.md, ADR-0011, ADR-0021.

Implemented so far (Stage B):

- Definition loading and validation — a workflow definition file becomes
  an in-memory, validated :class:`WorkflowDefinition`
  (:mod:`ai_os_kernel.workflow_engine.loader`,
  :mod:`ai_os_kernel.workflow_engine.models`).
- Instance creation — given a definition, inputs, and the id of the
  pack it belongs to, :class:`WorkflowInstanceService` validates the
  inputs, registers the definition into ``catalog.workflow_definitions``
  via :class:`~ai_os_kernel.workflow_engine.definition_catalog.
  WorkflowDefinitionCatalog` (an idempotent upsert — see that module),
  and then writes exactly one ``workflow_instances`` row
  (``status = created``) and its first ``workflow_events`` row
  (``workflow.started``) in one transaction.
  ``workflow_instances.definition_id``/``definition_version`` carry a
  real composite foreign key to ``catalog.workflow_definitions``
  (data_model.md §4.1) — registration happening first is what makes
  that foreign key satisfiable on every call.
- One state transition — `created` → `running`, appending a
  ``state.transitioned`` event and updating the snapshot's
  ``status``/``last_event_seq`` in the same transaction
  (:meth:`WorkflowInstanceService.start`).
- Step-by-step progression — :meth:`WorkflowInstanceService.advance`
  resolves the definition's next declared step from the instance's
  current one (or the first step, or "none left"), executes it, and
  either appends ``step.started``/``step.completed`` and advances
  ``current_step_id``, or — when no next step remains — appends
  ``workflow.completed`` and sets ``status = completed``. One call
  advances by exactly one step; repeated calls drive a multi-step
  workflow to completion. Each executed step also writes one
  materialised ``workflow_steps`` row (data_model.md §4.3) in the same
  transaction, queryable via
  :meth:`~ai_os_kernel.workflow_engine.repository.WorkflowInstanceRepository.list_steps`
  as :class:`~ai_os_kernel.workflow_engine.step_record.WorkflowStepRecord`.
  The append-only event log itself is queryable the same way via
  :meth:`~ai_os_kernel.workflow_engine.repository.WorkflowInstanceRepository.list_events`
  as :class:`~ai_os_kernel.workflow_engine.event_record.WorkflowEventRecord`.
  Both are plain, unguarded reads, mirroring
  :meth:`~ai_os_kernel.workflow_engine.repository.WorkflowInstanceRepository.get_instance`.
  The full collection of instances is listable the same way via
  :meth:`~ai_os_kernel.workflow_engine.repository.WorkflowInstanceRepository.list_instances`,
  keyset-paginated (newest first) by a
  :class:`~ai_os_kernel.workflow_engine.repository.WorkflowListCursor`
  rather than an offset, per api_architecture.md §9.
- Real dispatch by declared id — :class:`~ai_os_kernel.workflow_engine.
  registry.AgentRegistry`/:class:`~ai_os_kernel.workflow_engine.registry.
  ToolRegistry` resolve a step's declared ``agentId``/``toolId``
  (workflow_architecture.md's Step Contract) to a real, already-
  constructed :class:`~ai_os_kernel.workflow_engine.agent.Agent`/
  :class:`~ai_os_kernel.workflow_engine.tool.Tool` instance;
  :class:`~ai_os_kernel.workflow_engine.registry.InMemoryAgentRegistry`/
  :class:`~ai_os_kernel.workflow_engine.registry.InMemoryToolRegistry`
  are the simplest implementation — a plain mapping the composition
  root supplies directly. :class:`~ai_os_kernel.workflow_engine.
  registry.SqlAgentRegistry`/:class:`~ai_os_kernel.workflow_engine.
  registry.SqlToolRegistry` are a second, ``catalog.agents``/
  ``catalog.tools``-backed implementation: they confirm a declared id
  is a real, registered catalog row, then use
  :class:`~ai_os_kernel.workflow_engine.entrypoint_loader.
  EntrypointLoader` to load and construct the row's own declared
  ``entrypoint`` — a real implementation now, validated against the
  ``Agent``/``Tool`` Protocol before being returned. For tools, the
  loaded object's own declared ``trust_tier`` must agree with what
  ``catalog.tools`` records for it, so a catalog-declared
  ``tier1_sandboxed`` tool is still refused by ``ToolStepExecutor``
  regardless of what its own code claims. Before either loads anything,
  both also confirm the declared id's owning ``pack_id`` names a real
  ``catalog.packs`` row whose ``state``
  (:class:`~ai_os_kernel.workflow_engine.pack_state.PackState`) is
  ``activated`` — a missing or non-``activated`` pack raises
  :class:`~ai_os_kernel.workflow_engine.errors.PackNotActivatedError`
  before any entrypoint is imported. This is real dispatch *by id* to a
  real, dynamically-loaded implementation, now gated by the one fact
  that actually matters about its owning pack — still not real
  capability discovery: no pack install/upgrade lifecycle, no health
  monitoring, no permissions system, no sandboxing, no network or code
  download; see :mod:`ai_os_kernel.workflow_engine.registry` and
  :mod:`ai_os_kernel.workflow_engine.entrypoint_loader` for the exact
  boundary.
- Real (trivial) Agent invocation for Agent-type steps —
  :class:`AgentStepExecutor` resolves the step's declared ``agentId``
  through its injected ``AgentRegistry`` and calls the result,
  validating its output against that agent's declared ``output_schema``.
  It now also forwards the step's declared ``promptId``/
  ``promptVersion``/``modelAlias`` into the agent's ``inputs`` (the only
  three fields workflow_architecture.md's Step Contract documents for an
  agent step) — a step declaring none of them still executes with an
  empty ``inputs`` dict, unchanged from before.
- :class:`~ai_os_kernel.workflow_engine.prompted_agent.PromptedAgent` is
  the first real, non-``Echo*`` ``Agent``: it reads those three fields
  from ``inputs`` and delegates to an injected
  :class:`~ai_os_kernel.prompted_completion.PromptedCompletionService`,
  returning the completion's text as ``{"content": ...}``. Constructor-
  injected (a real database engine, secret, and model config are
  genuine dependencies), so it is used through
  :class:`InMemoryAgentRegistry`, not
  :class:`~ai_os_kernel.workflow_engine.registry.SqlAgentRegistry`'s
  zero-argument entrypoint loading — see that module's own docstring
  for why. :class:`EchoAgent` is unchanged and remains the deterministic
  implementation tests and local development use.
- Real (trivial) Tool invocation for Tool-type steps —
  :class:`ToolStepExecutor` resolves the step's declared ``toolId``
  through its injected ``ToolRegistry`` and calls the result, refuses
  anything but a ``tier2_trusted`` tool (no sandbox exists yet —
  ADR-0016), and validates its output.
- :class:`DispatchingStepExecutor` routes Agent-type steps to the agent
  path, Tool-type steps to the tool path, and every other step type to
  :class:`NoOpStepExecutor`. Still no real external tool execution, no
  sandboxing, no Context Manager, and no general per-step input-mapping
  mechanism beyond the three Step Contract invocation fields — tools are
  still always invoked with no inputs.
- :class:`QualityGateStepExecutor` (added 2026-07-30) is the first real,
  blocking implementation for a Quality-Gate step — the smallest real
  slice of the still-0%-built Quality Gate Engine
  (`quality_gate_engine.md`): it reads a configured source step's own
  real, persisted output and raises :class:`QualityGateFailedError`
  (halting :class:`WorkflowAdvanceRunner.run_to_completion`, the
  existing failure boundary) unless that output's ``passed`` field is
  literally ``True``. `se.delivery_pipeline` (below) is its first real
  caller, gating Documentation on Test's own real outcome. Still not the
  full engine: no Gate Registry, no pack-declared gate definitions, no
  ``evaluation.gate_results`` writer, and only one, named, overridable
  success-field convention (``success_field``, default ``"passed"``) is
  checked — no ``evaluationMethod``/``successCriteria`` expression
  language.
- Lease acquisition, renewal, and release — :class:`WorkflowLeaseService`
  claims a `running` instance's row in ``workflow_leases`` with
  ``SELECT ... FOR UPDATE SKIP LOCKED`` (reclaiming only if expired),
  lets the holding worker extend ``expires_at``/``heartbeat_at`` via
  :meth:`~ai_os_kernel.workflow_engine.lease.WorkflowLeaseService.renew`
  (a guarded ``UPDATE`` — the row is already known, so ``SKIP LOCKED``'s
  "scan past a locked row" semantics do not apply), and releases it
  afterward, so a worker can safely claim an instance before calling
  :meth:`WorkflowInstanceService.advance`. See
  :mod:`ai_os_kernel.workflow_engine.lease`.
- :class:`~ai_os_kernel.workflow_engine.lease_reaper.WorkflowLeaseReaper`
  proactively reclaims leases past ``expires_at`` in one bounded,
  structured-logging pass, closing the one gap left in the lease
  cycle: reclaiming no longer depends on another worker's ``acquire``
  call happening to trigger it. See
  :mod:`ai_os_kernel.workflow_engine.lease_reaper`.
- :class:`~ai_os_kernel.workflow_engine.advance_runner.WorkflowAdvanceRunner`
  composes the two. ``run_once`` acquires a lease, runs exactly one
  ``advance()``, and releases the lease in a ``finally`` block — release
  always runs, whether ``advance()`` succeeds or raises.
  ``run_to_completion`` calls ``run_once`` repeatedly for **one**
  instance until it completes, a bounded ``max_iterations`` is reached,
  or a call fails — returning a structured
  :class:`~ai_os_kernel.workflow_engine.advance_runner.WorkflowRunResult`
  rather than raising for a workflow-level failure. Both are
  single-instance and synchronous: a future multi-instance worker loop,
  its scheduling/polling, any decision to renew mid-step, and a
  background expiry reaper are not yet implemented.

Every transition and advance guard is the ``UPDATE ... WHERE`` clause
itself — one atomic statement comparing against the instance's expected
current state, no separate read-then-write race window.

A real Agent (`PromptedAgent`) can now call the real LLM Gateway/Prompt
Engine, but only when the composition root constructs and registers it
directly (`InMemoryAgentRegistry`) — nothing in this package does that
wiring itself. Not yet implemented: the Context Manager, real per-step
input mapping beyond the three Step Contract invocation fields, real
external tool execution, sandboxing, a multi-instance worker process
framework, statuses beyond `created`/`running`/`completed`,
retry/compensation, and parallel/sub-workflow support.
"""

from ai_os_kernel.workflow_engine.advance_runner import (
    WorkflowAdvanceRunner,
    WorkflowRunOutcome,
    WorkflowRunResult,
)
from ai_os_kernel.workflow_engine.agent import Agent, EchoAgent
from ai_os_kernel.workflow_engine.definition_catalog import (
    SqlWorkflowDefinitionCatalog,
    WorkflowDefinitionCatalog,
)
from ai_os_kernel.workflow_engine.entrypoint_loader import EntrypointLoader
from ai_os_kernel.workflow_engine.errors import (
    AgentNotRegisteredError,
    AgentOutputValidationError,
    AgentRegistryError,
    EntrypointLoadError,
    PackNotActivatedError,
    PromptedAgentInputError,
    QualityGateFailedError,
    ToolNotRegisteredError,
    ToolOutputValidationError,
    ToolRegistryError,
    ToolSandboxRequiredError,
    WorkflowDefinitionError,
    WorkflowDefinitionRegistrationError,
    WorkflowInputValidationError,
    WorkflowInstanceCreationError,
    WorkflowInvalidTransitionError,
    WorkflowLeaseUnavailableError,
)
from ai_os_kernel.workflow_engine.event_record import WorkflowEventRecord
from ai_os_kernel.workflow_engine.instance import WorkflowInstance, WorkflowInstanceStatus
from ai_os_kernel.workflow_engine.lease import (
    SqlWorkflowLeaseRepository,
    WorkflowLease,
    WorkflowLeaseRepository,
    WorkflowLeaseService,
)
from ai_os_kernel.workflow_engine.lease_reaper import LeaseReapResult, WorkflowLeaseReaper
from ai_os_kernel.workflow_engine.loader import WorkflowDefinitionLoader
from ai_os_kernel.workflow_engine.models import (
    HumanApprovalPoint,
    JoinPolicy,
    RetryPolicy,
    StepType,
    WorkflowDefinition,
    WorkflowStep,
)
from ai_os_kernel.workflow_engine.pack_state import PackState
from ai_os_kernel.workflow_engine.prompted_agent import PromptedAgent
from ai_os_kernel.workflow_engine.quality_gate import QualityGateStepExecutor
from ai_os_kernel.workflow_engine.registry import (
    AgentRegistry,
    InMemoryAgentRegistry,
    InMemoryToolRegistry,
    SqlAgentRegistry,
    SqlToolRegistry,
    ToolRegistry,
)
from ai_os_kernel.workflow_engine.repository import (
    SqlWorkflowInstanceRepository,
    WorkflowInstanceRepository,
    WorkflowListCursor,
)
from ai_os_kernel.workflow_engine.service import WorkflowInstanceService
from ai_os_kernel.workflow_engine.step_executor import (
    AgentStepExecutor,
    DispatchingStepExecutor,
    NoOpStepExecutor,
    StepExecutor,
    ToolStepExecutor,
)
from ai_os_kernel.workflow_engine.step_record import WorkflowStepRecord
from ai_os_kernel.workflow_engine.tool import EchoTool, Tool, TrustTier

__all__ = [
    "Agent",
    "AgentNotRegisteredError",
    "AgentOutputValidationError",
    "AgentRegistry",
    "AgentRegistryError",
    "AgentStepExecutor",
    "DispatchingStepExecutor",
    "EchoAgent",
    "EchoTool",
    "EntrypointLoadError",
    "EntrypointLoader",
    "HumanApprovalPoint",
    "InMemoryAgentRegistry",
    "InMemoryToolRegistry",
    "JoinPolicy",
    "LeaseReapResult",
    "NoOpStepExecutor",
    "PackNotActivatedError",
    "PackState",
    "PromptedAgent",
    "PromptedAgentInputError",
    "QualityGateFailedError",
    "QualityGateStepExecutor",
    "RetryPolicy",
    "SqlAgentRegistry",
    "SqlToolRegistry",
    "SqlWorkflowDefinitionCatalog",
    "SqlWorkflowInstanceRepository",
    "SqlWorkflowLeaseRepository",
    "StepExecutor",
    "StepType",
    "Tool",
    "ToolNotRegisteredError",
    "ToolOutputValidationError",
    "ToolRegistry",
    "ToolRegistryError",
    "ToolSandboxRequiredError",
    "ToolStepExecutor",
    "TrustTier",
    "WorkflowAdvanceRunner",
    "WorkflowDefinition",
    "WorkflowDefinitionCatalog",
    "WorkflowDefinitionError",
    "WorkflowDefinitionLoader",
    "WorkflowDefinitionRegistrationError",
    "WorkflowEventRecord",
    "WorkflowInputValidationError",
    "WorkflowInstance",
    "WorkflowInstanceCreationError",
    "WorkflowInstanceRepository",
    "WorkflowInstanceService",
    "WorkflowInstanceStatus",
    "WorkflowInvalidTransitionError",
    "WorkflowLease",
    "WorkflowLeaseReaper",
    "WorkflowLeaseRepository",
    "WorkflowLeaseService",
    "WorkflowLeaseUnavailableError",
    "WorkflowListCursor",
    "WorkflowRunOutcome",
    "WorkflowRunResult",
    "WorkflowStep",
    "WorkflowStepRecord",
]
