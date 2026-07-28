# Context Manager Design – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Context Manager Design  
**Version:** 1.1  
**Status:** Approved  
**Last Updated:** 2026-07-28 (§4: recorded the second real "Workflow State" resolver — no other content changed)

---

## 1. Purpose

This document defines the design of the **Context Manager**, a core component of the AI_OS Platform Kernel.

The Context Manager is responsible for assembling the precise, minimal, and relevant context that an Agent needs to perform its task. It prevents agents from independently pulling large amounts of information and ensures that context is consistent, traceable, and appropriate for the current workflow step.

This document is subordinate to:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Kernel Architecture  
5. Agent Architecture & Agent Contract  
6. Workflow Architecture  
7. Knowledge Manager & Memory Manager (related components)

---

## 2. Design Goals

The Context Manager must:

- Assemble context in a controlled and predictable way
- Supply only the information required for the current step
- Integrate data from multiple sources (Knowledge, Memory, Workflow State, Runtime Configuration, User Inputs)
- Remain domain-agnostic
- Support reproducibility for multi-LLM experiments
- Be fully observable (what context was given to which agent)
- Prevent agents from performing uncontrolled context retrieval

---

## 3. Core Responsibilities

- Accept a context request from the Workflow Engine (or Agent Invoker)
- Determine what information is required for the current agent and step
- Retrieve relevant data from:
  - Workflow State
  - Knowledge Manager
  - Memory Manager
  - AI Context Packs
  - Runtime Configuration
  - User-provided inputs
- Apply filtering, ranking, and size limits
- Return a structured context object
- Record exactly what context was supplied (for audit and replay)

---

## 4. High-Level Structure

```text
Context Manager
│
├── Context Request Handler
├── Source Resolvers
│     ├── Workflow State Resolver
│     ├── Knowledge Resolver
│     ├── Memory Resolver
│     ├── AI Context Pack Resolver
│     └── Configuration Resolver
├── Context Assembler
├── Context Filter / Ranker
├── Size & Token Budget Enforcer
└── Context Audit Logger
```

**Two real "Workflow State" resolvers now exist (2026-07-28), not one.** `ai_os_kernel.context_manager.resolvers.WorkflowStateResolver` reads a workflow instance's own top-level `inputs` (unchanged, matches "Workflow State Resolver" above exactly). A second, sibling resolver, `WorkflowStepOutputResolver`, reads a *named prior step's* own persisted output (`workflow_steps.outputs`) — §5's own `required_context_types` example already named this case (`previous_outputs`) without a resolver to back it; this is that resolver. Both share the same source category — this is not a new bullet in the diagram above, but a second real implementation behind the existing "Workflow State Resolver" one. See `ai_os_pack_software_engineering.pipeline` (the `software-engineering` capability pack) for its first real, production use, chaining a real four-step workflow.

---

## 5. Context Request

A typical context request contains:

- workflow_id
- step_id
- agent_id
- required_context_types (e.g., requirements, architecture, previous_outputs, coding_standards, etc.)
- token_budget or size limit
- experiment / run identifiers (for reproducibility)

---

## 6. Context Response

```text
AssembledContext
    items: ContextItem[]
    total_tokens: int
    sources_queried: SourceType[]
    items_excluded_count: int          # what did NOT fit, so truncation is visible
    assembly_id: str
    index_generation: str              # pinnable for reproducibility

ContextItem
    content: str
    provenance: SourceRef              # where it came from, and at what version
    relevance_score: float
    token_count: int
    trust: Literal["trusted", "untrusted"]
```

**`trust` is mandatory on every item and is load-bearing.** Repository content, ingested documents, tool output, and web content are always `untrusted`. The Prompt Engine wraps untrusted items in explicit data boundaries, and no untrusted content can confer authority — that structural rule, not prompt wording, is what contains prompt injection ([ADR-0016](../../18_decision_log/adr/ADR-0016-tool-execution-sandboxing.md)).

**Budget enforcement is hard, and truncation is recorded.** When the token budget is reached, assembly truncates by rank and reports `items_excluded_count`. Silent overflow — or silent dropping without a count — would make a degraded run indistinguishable from a healthy one.

---

## 7. Key Design Rules

- Agents must not bypass the Context Manager to pull arbitrary knowledge.
- Context must be minimal yet sufficient.
- The same context request under the same conditions should produce the same context (important for multi-LLM experiments).
- All context assembly decisions must be auditable.

---

## 8. Relationship with Other Components

- **Workflow Engine** asks the Context Manager to prepare context before invoking an Agent.
- **Knowledge Manager** provides long-term documentation, ADRs, specifications, and patterns.
- **Memory Manager** provides short-term and long-term engineering memory.
- **AI Context Packs** provide curated, high-signal context packages.
- **Prompt Engine** may receive parts of the assembled context when rendering prompts.
- **LLM Gateway** ultimately receives the final prompt that was built using this context.

---

## 9. Observability Requirements

Every context assembly must record:

- Workflow ID / Trace ID / Agent ID
- What sources were queried
- What items were included or excluded
- Final context size / token estimate
- Timestamp

This supports debugging and exact replay of experiments.

---

## 10. Current Status

This document defines the design baseline for the Context Manager.

Detailed interfaces, data models, and ranking/filtering strategies will be refined during implementation.

---

## 11. Final Authority

Order of precedence:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Kernel Architecture  
5. Context Manager Design  
6. Source Code
