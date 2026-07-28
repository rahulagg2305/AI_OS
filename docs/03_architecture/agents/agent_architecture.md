# Agent Architecture & Agent Contract – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Agent Architecture & Agent Contract  
**Version:** 1.1  
**Status:** Approved  
**Last Updated:** 2026-07-28 (added Implementation Status and Related Documents; marked the components in the High-Level Architecture diagram that have no implementation; resolved the stale "future documents will define the Agent Catalog" note — it exists)

**Previously:** 2026-07-26 (cross-referenced `workflow_architecture.md`'s Step Contract: `promptId`/`promptVersion`/`modelAlias` inform `AgentRequest` construction at invocation step 2)

---

## Purpose

This document defines the official architecture, execution model, lifecycle and mandatory contract for every Agent in AI_OS.

Agents are specialized, narrow-responsibility execution units that perform domain tasks under the control of the Workflow Engine. They are owned by Capability Packs and operate exclusively through Platform Kernel services.

This document is subordinate to:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Capability Pack Contract  
5. Kernel Architecture  

---

## Implementation Status (2026-07-28)

**Built:** the Invocation Lifecycle below is real end to end for `agent`-type workflow steps. `ai_os_kernel/workflow_engine/step_executor.py`'s `AgentStepExecutor` resolves a step's declared `agentId` through an `AgentRegistry` (in-memory or SQL-backed against real `catalog.agents` rows, gated on pack activation), assembles context via the Context Manager, invokes the agent, and validates its output against the agent's declared `output_schema` — a real Output Validator. `ai_os_kernel/workflow_engine/prompted_agent.py` is a real Prompt Requester + LLM Gateway Client: it renders a versioned prompt through the Prompt Engine and calls the LLM Gateway, never a provider. The `promptId`/`promptVersion`/`modelAlias` pass-through described under Lifecycles is implemented exactly as described. **Five real agents exist**, in `../../../capability_packs/software-engineering/src/ai_os_pack_software_engineering/agents/`: `requirements-analyst`, `architecture`, `build`, `qa-test` (`verification.py`), and `documentation`. Four of the five are genuinely chained through one declared workflow (`se.delivery_pipeline`); `requirements-analyst` is proven independently but not yet chained in. Agents are genuinely stateless between invocations. Observability emits real OpenTelemetry spans.

**Not built:**

- **The Agent Contract table below is the *manifest* contract, not a Python `Agent` Protocol.** Its fields are declared in and validated by the manifest JSON Schema; there is **no SDK `Agent` Protocol, no `AgentRequest`, and no `AgentResult`** (`../platform/platform_sdk.md` §4.2 — specification only). The real interface an agent implements today is a Kernel-internal `ai_os_kernel.workflow_engine.agent.Agent` with a much narrower shape.
- **`supportedWorkflows`, `qualityGates`, `retryPolicy`, and `timeout`** are declarable but nothing reads them. There is no agent-level retry, no agent-level timeout enforcement, and no Quality Gate Engine to run agent-level gates.
- **The Reasoning / Tool Loop does not exist.** No agent invokes a tool: there is **no `ToolInvoker`** at any layer (`../platform/platform_sdk.md` §5.6). The only real tool path is a workflow-level `tool` step (`ToolStepExecutor` + `SandboxedCommandTool`), which is not an in-agent loop.
- **The Error Handler returns no `StructuredError`** — that type and the whole `AiOsError` hierarchy do not exist anywhere in the codebase (`../workflow/error_handling_retry.md` §8).
- **Input Validator:** output is validated against the declared schema; **inputs are not**. `AgentStepExecutor` constructs an `inputs` dict and passes it through without validating it against an `input_model`.
- **Of the sixteen Agent Categories below, five exist.** Eleven do not: Technical Planning, Backend Development, Frontend Development, Database, API Design, DevOps, Security, Code Review, Release, Refactoring, Existing Project Analysis, Performance. (`Requirements Analyst`, `Architecture`, `QA / Test`, and `Documentation` are the four that map to real agents, plus a `build` agent that covers part of Backend Development.)
- **Context Management:** of the five sources listed, only Workflow State is implemented (1 of 6 Context Manager sources) — no Knowledge Manager, Memory Manager, or Runtime Configuration resolver exists.
- **Permissions are declared but not enforced** for agents; no monotonic-narrowing check runs at load or at runtime.

Authoritative, always-current status: `../../19_roadmap/feature_inventory.md` (per-module completion table — rows 5, 8, 18, 29) and `../../19_roadmap/implementation_status.md`. Build history: `../../19_roadmap/history/INDEX.md`.

---

## Objectives

The Agent Architecture ensures agents are:

- Modular
- Reusable
- Stateless where practical
- Interface-driven
- Configuration-driven
- LLM-agnostic
- Secure
- Observable
- Independently testable
- Governed through the Workflow Engine

---

## Core Principles

- Single Responsibility
- Narrow, well-defined purpose
- Contract-First Design
- No direct agent-to-agent communication
- Workflow Engine owns orchestration and state
- LLM Gateway is the only LLM access point
- Respect Quality Gates and Human Approval Points
- Deterministic, auditable execution

---

## Agent Contract (Mandatory)

| Field                | Required | Description                          |
|----------------------|----------|--------------------------------------|
| id                   | Yes      | Fully qualified `<pack_id>/<slug>`, globally unique |
| name                 | Yes      | Human-readable name                  |
| description          | Yes      | Short description                    |
| purpose              | Yes      | Clear responsibility                 |
| inputs               | Yes      | Input schema                         |
| outputs              | Yes      | Output schema                        |
| permissions          | Yes      | Required permissions                 |
| supportedWorkflows   | Yes      | Supported workflows                  |
| requiredTools        | No       | Tool dependencies                    |
| qualityGates         | No       | Agent-level validations              |
| timeout              | No       | Maximum execution time               |
| retryPolicy          | No       | Retry behaviour                      |
| entrypoint           | Yes      | Implementation path                  |
| version              | Yes      | Semantic version                     |

---

## High-Level Architecture

```text
User / API
      │
Workflow Engine   ── assembles context via the Context Manager, then invokes
      │
Agent
├── Input Validator          validates AgentRequest against input_model      [NOT BUILT]
├── Context Consumer         READS the supplied AssembledContext             [built]
├── Prompt Requester         requests a versioned prompt from the Prompt Registry  [built]
├── Reasoning / Tool Loop    bounded; tool calls via the Tool Invoker        [NOT BUILT — no Tool Invoker exists]
├── LLM Gateway Client       the only model access path                      [built]
├── Output Validator         validates against output_model before returning [built]
├── Error Handler            returns StructuredError; no own retry policy    [NOT BUILT — StructuredError does not exist]
└── Telemetry                                                               [built — spans; console exporters only]
```

The bracketed markers reflect the state of the code on 2026-07-28 (see Implementation Status above), not a change to the design.

**Two corrections from v1.0.** The agent had a "Context Builder", which contradicted the rule that agents must not assemble context — an agent **consumes** the `AssembledContext` supplied by the Context Manager and never performs its own retrieval. And "Prompt Selector" is a **Prompt Requester**: the agent requests a prompt by ID and version from the Prompt Registry rather than choosing or composing prompt text itself.

---

## Agent Categories (Initial Target)

An **initial target list**, not an inventory. Five of the sixteen exist in code as of 2026-07-28 — marked below. The authoritative per-agent catalogue is `../../05_agents/agent_catalog.md`.

1. Requirements Analyst — **built** (`requirements-analyst`; proven independently, not yet chained into `se.delivery_pipeline`)
2. Architecture — **built** (`architecture`)
3. Technical Planning  
4. Backend Development — partially covered by the **built** `build` agent
5. Frontend Development  
6. Database  
7. API Design  
8. DevOps  
9. Security  
10. QA / Test — **built** (`qa-test`)
11. Code Review  
12. Documentation — **built** (`documentation`)
13. Release  
14. Refactoring  
15. Existing Project Analysis  
16. Performance  

Additional agents shall be delivered through Capability Packs.

---

## Communication Rules

- Agents never communicate directly.
- Workflow Engine is the only orchestrator.
- Context is supplied by the Context Manager.
- Results are returned as structured outputs.
- Side effects occur only through approved Tools.

---

## Lifecycles

Two distinct lifecycles, conflated in v1.0:

**Registration lifecycle** (once per pack activation): declared in manifest → validated → registered → available to workflows → withdrawn on pack deactivation.

**Invocation lifecycle** (once per step):

1. Workflow Engine assembles context via the Context Manager
2. `AgentRequest` constructed with context, security context, budget, and deadline
3. Input validated against `input_model`
4. Agent executes: requests prompts, calls the LLM Gateway, invokes Tools
5. Output validated against `output_model`
6. `AgentResult` returned to the Workflow Engine
7. Result and usage persisted as workflow events; telemetry emitted

The agent retains **no state** between invocations.

When the invoking workflow step declares `promptId`/`promptVersion`/`modelAlias` (`workflow_architecture.md`'s Step Contract), those are the values the agent uses at step 4 — which prompt it requests from the Prompt Engine, and which model alias it passes to the LLM Gateway. They are inputs to the agent's own invocation, constructed into its `AgentRequest` at step 2; the Workflow Engine passes them through without acting on them itself, consistent with the agent — not the Workflow Engine — being the caller of both the Prompt Engine and the LLM Gateway (`system_architecture.md`'s "LLM Abstraction Path").

---

## Context Management

Agents receive context from:

- Workflow State
- Knowledge Manager
- Memory Manager
- Runtime Configuration
- User Inputs

Agents shall not assemble global context independently.

---

## Tool & LLM Usage

- Only registered tools may be invoked.
- All tool execution is auditable.
- All LLM interactions occur exclusively through the LLM Gateway.
- Provider abstraction, retries, fallbacks, token accounting and cost tracking are handled by the Kernel.

---

## Error Handling

- Return structured errors.
- Prefer idempotent execution.
- Retry policy is controlled by the Workflow Engine.

---

## Security

Agents shall:

- Apply least privilege
- Validate inputs
- Protect secrets
- Respect authorization
- Produce audit records

---

## Observability

Every invocation shall emit:

- Structured logs
- Metrics
- Trace ID
- Workflow ID
- Execution duration
- Token usage (when applicable)
- Success / Failure status
- Error details

---

## Testing Requirements

- Unit Tests
- Contract Tests
- Integration Tests
- Workflow Tests
- Regression Tests

---

## Documentation Requirements

Each agent shall include:

- Overview
- Responsibilities
- Inputs & Outputs
- Tool Dependencies
- Workflow Participation
- Configuration
- Limitations
- Change Log

---

## Relationship with Capability Packs

- Agents are owned by Capability Packs.
- Capability Packs declare agents in `manifest.yaml`.
- Plugin / Manifest Loader discovers and registers them.
- Agents from different packs shall never depend on each other’s internal implementation.

---

## Current Status

This document establishes the baseline Agent Architecture and Agent Contract. See Implementation Status above for what of it exists in code.

The "future documents" v1.0 anticipated now exist and are the authorities on their own subjects: the **Agent Catalog** is `../../05_agents/agent_catalog.md` (with per-agent detail in `../../05_agents/agent_specifications.md`), and **communication patterns** are `agent_communication.md` and `../workflow/workflow_patterns.md`. Individual implementations live in their owning pack — today, `../../../capability_packs/software-engineering/src/ai_os_pack_software_engineering/agents/`, documented in `../../06_capability_packs/software_engineering/agents.md`.

---

## Final Authority

Order of precedence:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Capability Pack Contract  
5. Kernel Architecture  
6. Agent Architecture & Agent Contract  
7. Source Code

---

## Related Documents

**Governing ADRs**

- [ADR-0005 — Agents never communicate directly](../../18_decision_log/adr/ADR-0005-agents-never-communicate-directly.md) — the Communication Rules
- [ADR-0021 — Declarative workflows, no dynamic task planner](../../18_decision_log/adr/ADR-0021-declarative-workflows-no-dynamic-task-planner.md) — why no agent selects another agent or the next step
- [ADR-0002 — LLM Gateway single entry point](../../18_decision_log/adr/ADR-0002-llm-gateway-single-entry-point.md) — the LLM Gateway Client is the only model access path
- [ADR-0004 — Interface-driven and configuration-over-code](../../18_decision_log/adr/ADR-0004-interface-driven-and-configuration-over-code.md) — contract-first agent design
- [ADR-0022 — Reproducibility over determinism](../../18_decision_log/adr/ADR-0022-reproducibility-over-determinism.md) — why prompt id + version are recorded per invocation
- [ADR-0016 — Tool execution sandboxing](../../18_decision_log/adr/ADR-0016-tool-execution-sandboxing.md) — side effects only through approved Tools
- [ADR-0023 — Identity, roles, and permissions](../../18_decision_log/adr/ADR-0023-identity-roles-and-permissions.md) — least privilege
- Full index: `../../18_decision_log/README.md`

**Architecture**

- `../platform/system_architecture.md` — the "LLM Abstraction Path" this document's Lifecycles section depends on
- `../platform/platform_sdk.md` §4.2 — the specified `Agent` Protocol, `AgentRequest`, `AgentResult` (**specification only; no implementing package**)
- `agent_communication.md` — the mandatory coordination rules
- `../workflow/workflow_architecture.md` — the Step Contract that supplies `agentId`/`promptId`/`promptVersion`/`modelAlias`
- `../workflow/error_handling_retry.md` — the error taxonomy an agent returns into, and why the Workflow Engine (not the agent) owns retry
- `../kernel/workflow_engine.md` · `../kernel/context_manager.md` · `../kernel/prompt_engine.md` · `../kernel/llm_gateway.md` — the Kernel services an agent consumes
- `../capability_framework/capability_pack_contract.md` · `../capability_framework/manifest_schema.md` — how an agent is declared and registered
- `../../05_agents/agent_catalog.md` · `../../05_agents/agent_specifications.md` — the per-agent catalogue and specifications
- `../../06_capability_packs/software_engineering/agents.md` — the five real agents

**Requirements traced to this document**

- `../../02_requirements/functional/functional_requirements.md` — FR-004 (agents coordinated by a declared workflow graph), FR-007 (all model calls via the Gateway), FR-010 (context assembled per step), FR-011 (versioned prompts with validated variables), FR-022 (per-step budgets); the agent categories map to FR-031 – FR-045

**Terminology**

- `../../20_glossary/glossary.md`

**Current state of the build**

- `../../19_roadmap/feature_inventory.md` (rows 5, 8, 18, 29), `../../19_roadmap/implementation_status.md`, `../../19_roadmap/history/INDEX.md`
