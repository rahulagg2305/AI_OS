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
4. **Other step types declare none of these fields.** `decision`, `parallel`, `sub_workflow`, `quality_gate`, and `human_approval` steps each already have their own documented contract (`joinPolicy` for `parallel` — `workflow_engine.md` §7.1; the Human Approval Point Contract for `human_approval`; gate-id references for `quality_gate`) and are unaffected by this section.
5. **These fields identify *what* to invoke, not *how*.** No templating, branching, or per-step scripting is introduced. Runtime selection of a prompt/model beyond this static declaration (config-driven defaults, experiment-forced overrides) remains the Prompt Engine's and LLM Gateway's own responsibility (`prompt_engine.md` §9, `llm_gateway.md`), not a workflow-level concern.

This section defines the **declared** contract only. Resolving `agentId`/`toolId` to a runtime `Agent`/`Tool` implementation, and passing `promptId`/`promptVersion`/`modelAlias` through to an agent's own Prompt Engine/LLM Gateway calls, is implementation — deliberately not specified further here (see `19_roadmap/implementation_status.md` for what is actually built).

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
