# State Management in Workflows – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** State Management in Workflows  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## 1. Purpose

This document defines how state is managed for workflows in AI_OS.

Correct state management is essential for long-running workflows, recovery after failures, human-in-the-loop pauses, observability, and multi-LLM experiment reproducibility.

This document is subordinate to:

1. Project Constitution  
2. Workflow Architecture  
3. Workflow Engine Architecture  
4. Error Handling & Retry Strategies  

---

## 2. Design Goals

State management must:

- Be durable (survive process restarts)
- Be auditable
- Support resumption after failure or human approval
- Keep Agents as stateless as practical
- Provide a clear source of truth for the current status of every workflow instance
- Support historical analysis and replay

---

## 3. Ownership of State

- The **Workflow Engine** is the sole owner of workflow instance state.
- Agents must not maintain hidden long-lived state about a workflow.
- Tools may have their own transient state but must not become the source of truth for workflow progress.
- Capability Packs must not bypass the Workflow Engine to store workflow state.

---

## 4. Types of State

### 4.1 Workflow Instance State
- Current status — the **canonical nine-state list** is defined in `../kernel/workflow_engine.md` §7 and is not restated here: `created`, `running`, `waiting_for_human`, `waiting_for_retry`, `quality_gate_failed`, `compensating`, `completed`, `failed`, `cancelled`
- Current step
- Inputs and outputs of completed steps
- Accumulated context / artifacts references
- Retry counters
- Error history
- Timestamps

### 4.2 Step State
- Status of individual steps
- Attempts and outcomes

### 4.3 Execution History
- Immutable (or append-only) log of significant events that allows reconstruction of what happened

---

## 5. Key Design Rules

- State transitions must be explicit and logged.
- State must be consistent with the actual progress of the workflow.
- Large artifacts (code, documents, binaries) should be stored by reference, not embedded directly in state, when practical.
- State must contain enough information to resume a workflow safely.
- Experiment runs must be able to isolate their state from other runs.

---

## 6. Durability & Recovery

- Workflow state must be persisted so that a crash or restart does not lose progress.
- On recovery, the Workflow Engine must be able to determine the last consistent state and resume or fail cleanly.
- Idempotency of steps is strongly preferred to make recovery safer.

---

## 7. Relationship with Other Components

- **Workflow Engine** reads and writes state.
- **Context Manager** uses workflow state when assembling context for the next agent.
- **Human Approval Points** rely on state being set to a waiting status and later resumed.
- **Error Handling & Retry** strategies update retry counters and error history in state.
- **Observability** records state transitions.
- **Evaluation Engine** uses final and intermediate state for metrics and comparisons.
- **Dashboard** displays state to users.

---

## 8. Observability Requirements

Every significant state transition must be recorded with:

- Workflow ID / Trace ID
- Previous state → New state
- Reason / triggering event
- Timestamp

---

## 9. Current Status

This document establishes the baseline rules for state management in workflows.

Concrete storage technology, schema, and recovery procedures will be refined during implementation of the Workflow Engine.

---

## 10. Final Authority

Order of precedence:

1. Project Constitution  
2. Workflow Architecture  
3. Workflow Engine Architecture  
4. State Management in Workflows  
5. Source Code
