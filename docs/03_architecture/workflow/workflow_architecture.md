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
- **3.5 of the 7 Supported Step Types genuinely execute (updated 2026-08-01, `P02-S01-M05-T09`).** `agent` and `tool` steps dispatch to real executors; `decision` now does too — `DecisionStepExecutor` genuinely evaluates a real, closed-vocabulary condition (see the new "Decision Step Contract" this update adds below) against a named prior step's own persisted output and branches execution to one of two declared targets, not a positional walk. `parallel`, `sub_workflow`, and `human_approval` still route to `NoOpStepExecutor` and complete having done nothing. `quality_gate` is real for exactly one, narrow, composition-configured case — see `../kernel/quality_gate_engine.md`'s own Implementation Status — not a general mechanism; a caller that doesn't configure one still routes to `NoOpStepExecutor` unchanged. Like `quality_gate`, no real composition wires `decision_executor` in yet — the mechanism is real and proven, unused by any running pipeline today.
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
4. **Other step types declare none of these fields.** `decision`, `parallel`, `sub_workflow`, `quality_gate`, and `human_approval` steps each already have their own documented contract (the Decision Step Contract below for `decision`; `joinPolicy` for `parallel` — `workflow_engine.md` §7.1; the Human Approval Point Contract for `human_approval`; gate-id references for `quality_gate`) and are unaffected by this section.
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
