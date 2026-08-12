# Agent Communication & Coordination Rules – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Agent Communication & Coordination Rules  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## 1. Purpose

This document defines the mandatory rules for how Agents communicate and how their work is coordinated inside AI_OS.

The primary goal is to prevent chaotic, uncontrolled agent-to-agent interaction and to ensure that all coordination is explicit, observable, and owned by the Workflow Engine.

This document is subordinate to:

1. Project Constitution  
2. AI Governance Framework  
3. Agent Architecture & Agent Contract  
4. Workflow Architecture  
5. Kernel Architecture  

---

## Implementation Status (2026-07-28)

**The fundamental rule (§2) is genuinely upheld — structurally, not just by convention.** No agent-to-agent call path exists anywhere in the codebase; every real agent (`requirements-analyst`, `architecture`, `build`, `qa-test`, `documentation`) is invoked only through `AgentStepExecutor`, and `se.delivery_pipeline`'s own step hand-offs go through a real Context Manager resolver (`WorkflowStepOutputResolver`), never a direct call. This is the one document in this audit's remaining-20 list whose central claim is fully real.

**Of the 5 Allowed Communication Paths (§3):** paths 1 and 2 (Workflow Engine input/output) are real and exercised by every agent. Path 4 (LLM Gateway) is real for the four `PromptedAgent`-backed agents. **Path 3 (Tool Invocation via "the Tool Invoker") does not exist as described** — there is no `ToolInvoker` class or Protocol anywhere; the real, narrower mechanism is `ToolStepExecutor` + `SandboxedCommandTool`, and it is composed *internally* by three agents rather than called by an agent through a documented invoker interface. **Path 5 (Event Publication) is entirely unbuilt** — the Event Bus is a docstring-only stub, so no agent publishes any event.

**§6 Data Passing Rules are real**: inter-agent data travels through Workflow State (`workflow_steps.outputs`) and is made visible via the Context Manager, exactly as specified — this is the same real mechanism cited above. **§7 Error and Retry Coordination is not built**: see `../workflow/error_handling_retry.md`'s own Implementation Status — the Workflow Engine does not yet act on a step failure per any policy; there is no retry, compensate, or escalate decision made anywhere today, only an unhandled exception.

Authoritative, always-current status: `../../19_roadmap/feature_inventory.md`. Build history: `../../19_roadmap/history/019_delivery_pipeline.md`.

---

## 2. Fundamental Rule

**Agents never communicate directly with each other.**

All coordination, sequencing, data passing, and decision-making between agents is performed exclusively by the **Workflow Engine**.

---

## 3. Allowed Communication Paths

An Agent may only interact with the rest of the system through the following controlled paths:

1. **Input from the Workflow Engine**  
   The agent receives a structured work item + context prepared by the Context Manager.

2. **Output back to the Workflow Engine**  
   The agent returns a structured result (success, failure, or partial result).

3. **Tool Invocation**  
   The agent may call approved Tools through the Tool Invoker. Tools are the only way an agent may cause side effects (file changes, git operations, external calls, etc.).

4. **LLM Access**  
   The agent may call the LLM Gateway (never a provider directly).

5. **Event Publication (limited)**  
   Agents may publish approved events to the Event Bus if explicitly allowed by their contract and permissions.

---

## 4. Forbidden Communication

The following are strictly prohibited:

- Agent A calling Agent B directly
- Agent A writing into Agent B’s memory or private state
- Shared mutable state between agents without going through the Workflow Engine
- Hidden back-channels or side channels between agents
- Agents polling or watching each other

---

## 5. Coordination Model

Coordination is achieved through workflows:

- The Workflow definition declares which agents participate and in what order (or graph).
- The Workflow Engine invokes agents according to the definition.
- Data produced by one agent is stored in Workflow State and selectively passed as input to later agents via the Context Manager.
- Quality Gates and Human Approval Points are inserted between agents as needed.

---

## 6. Data Passing Rules

- Agents must not assume the existence of global shared memory.
- Any information that must be passed from one agent to another must travel through Workflow State.
- The Context Manager decides what previous outputs are visible to the next agent.
- Large artifacts (code, documents) are referenced by identity/path rather than passed by value when practical.

---

## 7. Error and Retry Coordination

- When an agent fails, the Workflow Engine decides the next action (retry, compensate, skip, escalate to human, or fail the workflow).
- Agents themselves do not decide to call other agents as a recovery strategy.

---

## 8. Observability Requirements

Every interaction must be visible:

- Which agent was invoked
- What input it received
- What output it produced
- Which tools it called
- Which LLM calls it made
- How long it took
- Whether it succeeded or failed

This information is essential for debugging and for multi-LLM comparison.

---

## 9. Relationship with Capability Packs

- Capability Packs may define agents and the workflows that coordinate them.
- Capability Packs may not introduce direct agent-to-agent communication mechanisms that bypass the Workflow Engine.

---

## 10. Current Status

This document establishes the mandatory communication and coordination rules for all agents.

Future documents may define standard interaction patterns (e.g., request-review-revise loops) that are still implemented on top of the Workflow Engine.

---

## 11. Final Authority

Order of precedence:

1. Project Constitution  
2. AI Governance Framework  
3. Agent Architecture & Agent Contract  
4. Workflow Architecture  
5. Agent Communication & Coordination Rules  
6. Source Code
