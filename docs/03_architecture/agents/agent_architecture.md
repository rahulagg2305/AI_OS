# Agent Architecture & Agent Contract – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Agent Architecture & Agent Contract  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-26 (cross-referenced `workflow_architecture.md`'s Step Contract: `promptId`/`promptVersion`/`modelAlias` inform `AgentRequest` construction at invocation step 2)

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
├── Input Validator          validates AgentRequest against input_model
├── Context Consumer         READS the supplied AssembledContext
├── Prompt Requester         requests a versioned prompt from the Prompt Registry
├── Reasoning / Tool Loop    bounded; tool calls via the Tool Invoker
├── LLM Gateway Client       the only model access path
├── Output Validator         validates against output_model before returning
├── Error Handler            returns StructuredError; no own retry policy
└── Telemetry
```

**Two corrections from v1.0.** The agent had a "Context Builder", which contradicted the rule that agents must not assemble context — an agent **consumes** the `AssembledContext` supplied by the Context Manager and never performs its own retrieval. And "Prompt Selector" is a **Prompt Requester**: the agent requests a prompt by ID and version from the Prompt Registry rather than choosing or composing prompt text itself.

---

## Agent Categories (Initial Target)

1. Requirements Analyst  
2. Architecture  
3. Technical Planning  
4. Backend Development  
5. Frontend Development  
6. Database  
7. API Design  
8. DevOps  
9. Security  
10. QA / Test  
11. Code Review  
12. Documentation  
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

This document establishes the baseline Agent Architecture and Agent Contract.

Future documents will define the detailed Agent Catalog, communication patterns and individual implementations.

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
