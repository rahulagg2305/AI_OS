# Workflow Architecture – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Workflow Architecture  
**Version:** 1.1  
**Status:** Approved  
**Last Updated:** 2026-07-28 (Context Management: one-line pointer recording that "Previous workflow state" is now genuinely implemented)

**Previously:** 2026-07-26 (added: Step Contract — minimum invocation fields `agentId`/`toolId`/`promptId`/`promptVersion`/`modelAlias`)

---

## Purpose

This document defines the official architecture, execution model, governance, lifecycle and mandatory contract for Workflows in AI_OS.

Workflows are the primary orchestration mechanism of AI_OS. They coordinate Agents, Tools and Platform Services, manage execution state, enforce Quality Gates, handle failures and Human Approval Points, and deliver deterministic end-to-end execution.

The Workflow Engine, part of the Platform Kernel, is the sole owner of workflow execution.

This document is subordinate to:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Capability Pack Contract  
5. Kernel Architecture  
6. Agent Architecture & Agent Contract  

---

## Implementation Status (2026-07-28)

**Partially built — the core loop is real; most of the declared surface is not.**

**Built:** definition loading/validation (`WorkflowDefinitionLoader`), instance creation and lease acquisition, per-step context preparation → agent/tool execution → output validation → state append (one transaction), completion, and the Step Contract's five invocation fields exactly as specified. `se.delivery_pipeline` is a real, running instance of this lifecycle.

**Not built, and in two cases structurally blocked rather than merely unwritten:**
- **5.5 of the 7 Supported Step Types genuinely execute (updated 2026-08-02, `P02-S01-M05-T11`).** `agent` and `tool` steps dispatch to real executors; `decision`, `parallel`, and now `sub_workflow` do too. `DecisionStepExecutor` genuinely evaluates a real, closed-vocabulary condition (see the "Decision Step Contract" below) against a named prior step's own persisted output and branches execution to one of two declared targets, not a positional walk. `ParallelStepExecutor` genuinely runs its declared branches concurrently (real `asyncio` tasks, proven by real wall-clock timing, not a sequential loop) and joins per the real, closed-vocabulary "Parallel Step Contract" below — `all`/`any`/`collect`, exactly as `workflow_engine.md` §7.1 already documented the *policy* semantics, though the *membership* contract (which steps are a parallel step's branches) was, like decision-step branching, undocumented anywhere until this step. `SubWorkflowStepExecutor` genuinely creates a real, separate child `WorkflowInstance` via its own, independent `WorkflowInstanceService`/`WorkflowAdvanceRunner`, runs it to completion, and joins on that child's own real, persisted last-step output — see the "Sub-workflow Step Contract" below for the `subWorkflowId` field and why definition resolution is composition-level, not a catalog read. `human_approval` still routes to `NoOpStepExecutor` and completes having done nothing. `quality_gate` is real for exactly one, narrow, composition-configured case — see `../kernel/quality_gate_engine.md`'s own Implementation Status — not a general mechanism; a caller that doesn't configure one still routes to `NoOpStepExecutor` unchanged. Like `quality_gate`/`decision`/`parallel`, no real composition wires `sub_workflow_executor` in yet — the mechanism is real and proven, unused by any running pipeline today.
- **Only 3 of `state_management.md`'s 9 canonical instance states are ever written**: `created`, `running`, `completed`. `waiting_for_human`, `waiting_for_retry`, `quality_gate_failed`, and `compensating` are declared in the `WorkflowInstanceStatus` enum but no code path transitions an instance into any of them — verified by searching every reference to each in `kernel/src/ai_os_kernel/workflow_engine/`. `failed` and `cancelled` are likewise declared but unused; a failing step currently propagates as a raised exception rather than a persisted terminal state.
- **Quality Gates** (Quality Gate Engine still 0% built as its own subsystem) are enforced for exactly one real, narrow case as of 2026-07-30 — see the Step Types bullet above — otherwise still unenforced; **Human-in-the-Loop** (`approvals` table has no writer) remains fully unenforced. The sections below describing the general Gate Contract are still specification only.
- **Failure Handling (updated 2026-07-30):** `RetryPolicy` is declared on `WorkflowDefinition` (not `WorkflowStep` — a factual correction to this line's own prior claim) and validated at load time (bounded attempts + duration). It is now genuinely read for exactly one, narrow case: `WorkflowAdvanceRunner.run_to_completion` retries a failed, blocking `quality_gate` step, bounded by both `max_attempts` and `max_duration_seconds`, when a caller has configured a retry target for it (`se.delivery_pipeline` does; every other caller doesn't and keeps the prior "fails immediately" behavior). Every other kind of step failure (`AgentOutputValidationError`, etc.) is still not automatically retried. No rollback/compensation and no human escalation path exist.
- **Observability**: Quality Gate results, human decisions, and token/cost metrics are not emitted (their producing subsystems don't exist); the rest of the documented telemetry is real.

Authoritative, always-current status: `../../19_roadmap/feature_inventory.md` (module 5, Workflow Engine) and `../../19_roadmap/implementation_status.md`. Build history: `../../19_roadmap/history/003_workflow_engine_core.md` and `history/INDEX.md`.

---

## Objectives

Workflows shall be:

- Reproducible (pinned conditions, deterministic platform behaviour, recorded non-determinism — [ADR-0022](../../18_decision_log/adr/ADR-0022-reproducibility-over-determinism.md))
- Modular
- Reusable
- Recoverable
- Auditable
- Observable
- Configuration-driven
- Versioned
- Long-running capable
- LLM-agnostic
- Independently testable

---

## Core Concepts

- **Workflow** — Multi-step orchestration definition.
- **Step** — Individual execution unit.
- **Workflow State** — Durable execution state owned by the Workflow Engine.
- **Quality Gate** — Mandatory validation checkpoint.
- **Human Approval Point** — Explicit human decision checkpoint.

---

## High-Level Architecture

```text
User / API
      │
Workflow Engine  ── loads + validates the DECLARED workflow definition
      │
      ├─ per declared step:
      │       Context Manager  → assembled context
      │       Agent or Tool    → structured result
      │       LLM Gateway      (via the agent, if the step needs a model)
      │       State append     (event + snapshot, one transaction)
      │
      ├─ Quality Gates         at declared points
      ├─ Human Approval        at declared points (workflow persists and waits)
      │
      └─ Knowledge & Metrics update → run manifest recorded
              │
          Response
```

**There is no task-planning or agent-selection phase.** v1.0 of this document showed "Task Planning & Agent Selection" and listed "Task Decomposition" and "Agent Assignment" in the lifecycle, implying runtime planning — which contradicted the fact that steps and agents are statically declared in the pack manifest and validated at load. The resolution ([ADR-0021](../../18_decision_log/adr/ADR-0021-declarative-workflows-no-dynamic-task-planner.md)):

- Workflows are **declared graphs**, validated at pack load; every agent, tool, and gate reference must resolve or the pack does not activate.
- Where work must be decomposed at runtime, a **planning agent** emits a schema-conforming **plan artifact**, and a declared `foreach` step executes a declared sub-workflow per item. The content of the work is dynamic; the shape of the control flow is declared.
- No agent chooses the next step, and no agent selects another agent.

This is what preserves replay, fair cross-model comparison, static validation, and bounded cost.

---

## Workflow Contract (Mandatory)

| Field                 | Required | Description                          |
|-----------------------|----------|--------------------------------------|
| id                    | Yes      | Globally unique identifier           |
| name                  | Yes      | Human-readable name                  |
| description           | Yes      | Workflow purpose                     |
| version               | Yes      | Semantic version                     |
| trigger               | No       | Invocation trigger                   |
| inputs                | Yes      | Input schema                         |
| outputs               | Yes      | Output schema                        |
| steps                 | Yes      | Ordered or graph-based steps         |
| agents                | Yes      | Participating agents                 |
| requiredTools         | No       | Tool dependencies                    |
| qualityGates          | Yes      | Validation checkpoints               |
| humanApprovalPoints   | No       | Human decisions                      |
| failureHandling       | Yes      | Retry / rollback / escalation        |
| timeout               | No       | Execution timeout                    |
| retryPolicy           | No       | Retry configuration                  |
| entrypoint            | Yes      | Workflow definition location         |

---

## Supported Step Types

- Agent Step
- Tool Step
- Decision Step
- Parallel Step
- Sub-workflow Step
- Quality Gate Step
- Human Approval Step

---

## Step Contract (Minimum Invocation Fields)

`type` is a step's primary discriminator (Supported Step Types, above); it decides which executor a step runs through and does not change. Beyond `id`/`type`, an `agent` or `tool` step may declare the following fields — the minimum the Workflow Engine needs to later invoke the correct Agent or Tool, and, for an agent, the Prompt Engine render and LLM Gateway call that agent makes. This is deliberately not a general orchestration language: every field below is a flat, statically-declared identifier or version string, resolved once at pack load — never a computed value, a cross-step reference, a template, or conditional logic.

| Field           | Required                          | Description                                                                                          |
|-----------------|------------------------------------|--------------------------------------------------------------------------------------------------------|
| `agentId`       | Yes, when `type` is `agent`        | The agent to invoke — the fully qualified `<pack_id>/<slug>` id from the Agent Contract                |
| `toolId`        | Yes, when `type` is `tool`         | The tool to invoke — a dot-namespaced id (Coding Standards' `Tool, workflow, gate IDs` convention)      |
| `promptId`      | No — optional, `agent` steps only  | The prompt the agent should render before calling the LLM Gateway (`prompt_engine.md` §7 Resolution Flow) |
| `promptVersion` | No — optional, `agent` steps only  | Pins `promptId` to a specific version. The Prompt Engine's render contract requires both together (`prompt_engine.md` §6/§7); declaring one without the other is invalid |
| `modelAlias`    | No — optional, `agent` steps only  | The model alias (never a literal model id — [ADR-0002](../../18_decision_log/adr/ADR-0002-llm-gateway-single-entry-point.md)) the agent's LLM Gateway call should use |

Rules:

1. **`type` remains the sole primary discriminator** for how a step executes. These fields refine an `agent`/`tool` step's invocation; they do not add a new step type and do not change how `type` is interpreted.
2. **An `agent` step must declare `agentId`.** `promptId`, `promptVersion`, and `modelAlias` are optional — inputs to that agent's own invocation, not consumed directly by the Workflow Engine. This mirrors `system_architecture.md`'s "LLM Abstraction Path": the agent, not the Workflow Engine, is the caller of the Prompt Engine and the LLM Gateway.
3. **A `tool` step must declare `toolId`.** `promptId`/`promptVersion`/`modelAlias` have no meaning for a `tool` step and shall not be declared on one — a Tool is a trivial in-process unit of work (Tool Contract) with no prompt or LLM involvement.
4. **Other step types declare none of these fields.** `decision`, `parallel`, `sub_workflow`, `quality_gate`, and `human_approval` steps each already have their own documented contract (the Decision Step Contract below for `decision`; `joinPolicy` for `parallel` — `workflow_engine.md` §7.1; the Sub-workflow Step Contract below for `sub_workflow`; the Human Approval Point Contract for `human_approval`; gate-id references for `quality_gate`) and are unaffected by this section.
5. **These fields identify *what* to invoke, not *how*.** No templating, branching, or per-step scripting is introduced. Runtime selection of a prompt/model beyond this static declaration (config-driven defaults, experiment-forced overrides) remains the Prompt Engine's and LLM Gateway's own responsibility (`prompt_engine.md` §9, `llm_gateway.md`), not a workflow-level concern.

This section defines the **declared** contract only. Resolving `agentId`/`toolId` to a runtime `Agent`/`Tool` implementation, and passing `promptId`/`promptVersion`/`modelAlias` through to an agent's own Prompt Engine/LLM Gateway calls, is implementation — deliberately not specified further here (see `19_roadmap/implementation_status.md` for what is actually built).

---

## Decision Step Contract

**Added 2026-08-01 (`P02-S01-M05-T09`).** This section did not exist before this step — no prior document defined a field-level contract for decision-step branching, and inventing one without a document to follow was recorded as "architecture this module does not own" ([`models.py`](../../../kernel/src/ai_os_kernel/workflow_engine/models.py)'s own docstring, before this step). The product owner explicitly approved this minimal contract as part of the step itself, a disclosed decision rather than a document written after the fact to justify code already built.

A `decision` step declares exactly two fields, both required together:

| Field       | Description                                                                                  |
|-------------|------------------------------------------------------------------------------------------------|
| `condition` | `sourceStepId` (a step declared *earlier* in the sequence), `field` (a key in that step's own recorded output), `equals` (a literal value — string, number, boolean, or null) |
| `branches`  | Exactly the two keys `"true"`/`"false"`, each naming a real, declared step id                  |

Deliberately **not an expression language** — the same "not a general orchestration language" principle the Step Contract above states for `agent`/`tool` steps applies here too: one named source step, one field of its output, one literal equality comparison, two named targets. No boolean combinators, no nested conditions, no arithmetic.

**Evaluated genuinely, against real state, not a template.** At runtime, the resolved outcome is `sourceStep.outputs[field] == equals`; the branch taken is `branches["true"]` or `branches["false"]` accordingly — see `workflow_engine.md` §5.5 for exactly how this is computed and read back to drive real execution.

**Validated at load time, not discovered at runtime.** `sourceStepId` must name a real, already-declared step earlier in the sequence (a forward reference could never resolve — that step cannot have executed yet); both `branches` targets must name real, declared steps. A definition failing either check is rejected before any instance ever runs.

---

## Parallel Step Contract

**Added 2026-08-01 (`P02-S01-M05-T10`).** `workflow_engine.md` §7.1 already documented the real *policy* semantics (`all`/`any`/`collect`) in prose, but no document — and no field on `WorkflowStep` — ever declared *which* steps are a parallel step's branches. The same "architecture this module does not own" situation `decision` was in; the product owner again explicitly approved a minimal contract as part of this step.

A `parallel` step declares, alongside its already-real `joinPolicy`:

| Field           | Description                                                                                     |
|-----------------|---------------------------------------------------------------------------------------------------|
| `parallelSteps` | At least two nested, inline steps, each a full `agent` or `tool` step declaration (the identical Step Contract fields above) — no nested `parallel`/`decision`/`quality_gate`/etc. |

**Branches are declared inline, not by reference.** Unlike `decision`'s `sourceStepId` (a reference to another top-level step), a parallel step's branches are nested *inside* it — they are not separate entries in the outer `steps` sequence, and the outer sequencer (`WorkflowInstanceService._resolve_next_step`) never sees them individually; it only ever advances past the one `parallel` step as a whole, exactly as it already does for `agent`/`tool`. This is a deliberate scope limit, not an oversight: it lets genuine concurrent execution exist without changing `WorkflowInstance`'s own single `current_step_id` model at all, a substantially larger, riskier change (tracking multiple simultaneously in-flight steps at the instance-state level) this step does not make.

**No nested branch may itself be `parallel`, `decision`, or any other cross-referencing step type.** Each of those carries its own reference semantics (a join policy of its own, a `sourceStepId` elsewhere in the *outer* sequence) that cannot resolve inside an isolated concurrent branch — rejected at load time, not discovered as a confusing runtime failure.

**Real join policy semantics, exactly as `workflow_engine.md` §7.1 already documented them, now genuinely enforced:**
- `all` — every branch must succeed; the step fails if any does, decided only after every branch has genuinely run to completion.
- `any` — the first branch to succeed wins; every branch still running is genuinely cancelled the moment a success is observed.
- `collect` — every branch runs to completion; failures are reported as real, structured partial results, never raised.

---

## Sub-workflow Step Contract

**Added 2026-08-02 (`P02-S01-M05-T11`).** Investigation confirmed a genuinely bigger question than `decision`/`parallel` faced: invoking a `sub_workflow` step requires creating and tracking a real, separate `WorkflowInstance`, not just a new field. `WorkflowDefinitionCatalog` — the component that would seem to resolve a workflow id to its `WorkflowDefinition` — is, by its own docstring, write-only ("No reader, no update, no delete — registration is the only operation this step approves"), so no real path exists to *look up* a definition by id at runtime. The product owner was presented three options (build a real catalog reader; resolve the reference at the composition level; stop and defer to a dedicated architecture step) and approved composition-level injection.

A `sub_workflow` step declares exactly one field:

| Field           | Description                                                                                     |
|-----------------|---------------------------------------------------------------------------------------------------|
| `subWorkflowId` | The id of the child `WorkflowDefinition` to invoke — a plain reference string, the identical shape `DecisionCondition`'s own `sourceStepId` already uses |

**Resolved via composition-level injection, not a catalog read.** `SubWorkflowStepExecutor` is constructed with a plain `{workflow_definition_id: WorkflowDefinition}` mapping — the identical shape `QualityGateStepExecutor`'s own `gate_sources` and `WorkflowAdvanceRunner.run_to_completion`'s own `step_retry_targets` already establish for "a cross-step/cross-workflow reference belongs in the composition layer, not as new, workflow-file-facing architecture." A step whose declared `subWorkflowId` is absent from this mapping fails clearly (`SubWorkflowFailedError`), never silently skipped.

**Genuine child execution, through the same classes any top-level workflow already uses.** `SubWorkflowStepExecutor` creates the child instance (`WorkflowInstanceService.create_instance`), starts it, and runs it to completion (`WorkflowAdvanceRunner.run_to_completion`) via its own, independently-injected `WorkflowInstanceService`/`WorkflowAdvanceRunner` pair — not a second, parallel execution mechanism, and not a simulation. A child that does not reach `WorkflowRunOutcome.COMPLETED` fails the parent's `sub_workflow` step (`SubWorkflowFailedError`).

**Child outputs, read from the child's own last-executed step — never from `WorkflowInstance.outputs`.** That field exists on the model but is never actually written by `SqlWorkflowInstanceRepository.advance_workflow`'s completion branch (verified by reading it directly). "Child outputs in the parent" is instead the completed child's own `current_step_id` (never touched by the completion branch, so it still names the last step that genuinely ran) read back through the same `_latest_completed_output` helper `DecisionStepExecutor` already reuses for the identical "read a named step's real, persisted output" need.

---

## Execution Lifecycle

1. Registration (at pack load)
2. Validation (references resolved; graph checked)
3. Instance creation and lease acquisition
4. Per declared step: context preparation → agent/tool execution → output validation → state append
5. Quality Gate evaluation at declared points
6. Human Approval at declared points
7. Completion
8. Knowledge & Metrics update; run manifest recorded
9. Audit

*(v1.0 listed "Task Decomposition" and "Agent Assignment" as steps 5 and 6. Both are removed — see the note under High-Level Architecture above.)*

---

## State Management

- Workflow Engine owns all state.
- Agents remain stateless where practical.
- State is durable and resumable.
- State transitions are fully auditable.

---

## Communication Model

Workflows coordinate:

- Agents via Workflow Engine
- Tools via approved interfaces
- Platform Services through published contracts
- Events through the Event Bus

Direct orchestration outside the Workflow Engine is prohibited.

---

## Context Management

Workflow context may include:

- User inputs
- Runtime configuration
- Knowledge Manager
- Memory Manager
- Previous workflow state — genuinely implemented (2026-07-28) via `ai_os_kernel.context_manager.resolvers.WorkflowStepOutputResolver`, a Context Manager resolver reading a named prior step's own persisted output; see `context_manager.md` §4 for the full design

---

## Failure Handling

Workflows shall support:

- Structured errors
- Retries
- Rollback / compensation
- Timeout handling
- Human escalation

Retry policy is enforced by the Workflow Engine.

---

## Quality Gates

Quality Gates are mandatory checkpoints.

Examples include:

- Build success
- Test execution
- Security scan
- Architecture compliance
- Linting
- Coverage thresholds

Workflow progression stops when mandatory gates fail.

---

## Human-in-the-Loop

Critical activities requiring approval include:

- Requirements approval
- Architecture approval
- Production deployment
- Major design changes

---

## Security

Every workflow shall:

- Enforce least privilege
- Validate inputs
- Respect authorization
- Produce audit records

---

## Observability

Every execution shall emit:

- Structured logs
- Trace ID
- Workflow ID
- Agent invocations
- Tool calls
- LLM Gateway usage
- Quality Gate results
- Human decisions
- Execution duration
- Token and cost metrics
- Final outcome

Execution traces should support replay.

---

## Testing Requirements

- Unit Tests
- Workflow Tests
- Integration Tests
- Contract Tests
- Regression Tests

---

## Documentation Requirements

Each workflow shall include:

- Overview
- Trigger
- Inputs & Outputs
- Step Sequence
- Agent Responsibilities
- Tool Dependencies
- Quality Gates
- Failure Scenarios
- Change Log

---

## Relationship with Capability Packs

- Workflows are owned by Capability Packs.
- Capability Packs declare workflows in `manifest.yaml`.
- Plugin / Manifest Loader discovers and registers workflows.

---

## Current Status

This document establishes the baseline Workflow Architecture. Detailed workflow patterns and Workflow Engine implementation are defined in subsystem documents.

---

## Final Authority

Order of precedence:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Capability Pack Contract  
5. Kernel Architecture  
6. Agent Architecture & Agent Contract  
7. Workflow Architecture  
8. Source Code

---

## Related Documents

- [`../kernel/workflow_engine.md`](../kernel/workflow_engine.md) — the Kernel component implementing this architecture; owns the canonical state list and lease mechanics
- [`workflow_patterns.md`](workflow_patterns.md) — the 8 reusable orchestration patterns built on this architecture (1 of 8 real)
- [`state_management.md`](state_management.md) — the state-ownership rules this document's own "State Management" section summarizes
- [`error_handling_retry.md`](error_handling_retry.md) — the failure-handling model referenced above
- [`../governance/human_approval_points.md`](../governance/human_approval_points.md) — the Human-in-the-Loop contract (0% built)
- [`../quality/quality_gates_framework.md`](../quality/quality_gates_framework.md) — the Quality Gates contract (0% built)
- [`../agents/agent_architecture.md`](../agents/agent_architecture.md) · [`../agents/agent_communication.md`](../agents/agent_communication.md) — the Agent side of every agent-step invocation
- [ADR-0021](../../18_decision_log/adr/ADR-0021-declarative-workflows-no-dynamic-task-planner.md) — declarative workflows, no runtime task planner
- [ADR-0022](../../18_decision_log/adr/ADR-0022-reproducibility-over-determinism.md) — the Objectives' reproducibility requirement
- [ADR-0002](../../18_decision_log/adr/ADR-0002-llm-gateway-single-entry-point.md) — governs the Step Contract's `modelAlias` field
- [`../../06_capability_packs/software_engineering/workflows.md`](../../06_capability_packs/software_engineering/workflows.md) — the one pack currently declaring real workflows against this contract
- [`../../19_roadmap/feature_inventory.md`](../../19_roadmap/feature_inventory.md) · [`../../19_roadmap/implementation_status.md`](../../19_roadmap/implementation_status.md) — live build status
