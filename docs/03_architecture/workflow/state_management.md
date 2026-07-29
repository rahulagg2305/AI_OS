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

## Implementation Status (2026-07-28)

**Partially built.** The storage technology and schema this document's own §9 once deferred are **not open questions** — they were decided by [ADR-0011](../../18_decision_log/adr/ADR-0011-persistence-and-workflow-state.md) and are real: PostgreSQL, an append-only `workflow.workflow_events` log plus a materialized `workflow_instances` snapshot updated in the same transaction, with per-step state additionally materialized in `workflow.workflow_steps` (§4.2's "Status of individual steps").

**What §4.1's "current status" concretely is, verified against `kernel/src/ai_os_kernel/workflow_engine/instance.py`:** the canonical list is 9 states, but **only 3 are ever written** — `created`, `running`, `completed`. `waiting_for_human`, `waiting_for_retry`, `quality_gate_failed`, and `compensating` are declared in the enum with no code path that transitions an instance into any of them; `failed` and `cancelled` are likewise declared and unused today (a failing step currently propagates as a raised exception, not a persisted terminal state). §5's "Idempotency of steps is strongly preferred" is real and enforced — `(workflow_id, step_name, attempt)` is a unique constraint on `workflow_steps`.

**Durability and recovery (§6) are real**: lease-based crash recovery (`SELECT ... FOR UPDATE SKIP LOCKED`, heartbeat renewal, an expiry reaper) lets another worker resume an instance after a crash, tested directly. **Not built**: the Context Manager relationship in §7 is only partly true — it reads a workflow's declared inputs and a named prior step's output, but has no first-class Filter/Ranker; the Evaluation Engine and Dashboard relationships are entirely unbuilt (both subsystems are 0%).

Authoritative, always-current status: `../../19_roadmap/feature_inventory.md` (module 5, Workflow Engine) and `../../19_roadmap/implementation_status.md`. Build history: `../../19_roadmap/history/003_workflow_engine_core.md`.

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

This document establishes the baseline rules for state management in workflows. **Storage technology, schema, and recovery procedures are no longer open** — see the Implementation Status section near the top of this document for exactly what is decided (PostgreSQL, event log + snapshot, lease-based recovery, per [ADR-0011](../../18_decision_log/adr/ADR-0011-persistence-and-workflow-state.md)) and what remains genuinely unbuilt (6 of 9 canonical states are declared but never reached).

---

## 10. Final Authority

Order of precedence:

1. Project Constitution  
2. Workflow Architecture  
3. Workflow Engine Architecture  
4. State Management in Workflows  
5. Source Code

---

## 11. Related Documents

- [`workflow_architecture.md`](workflow_architecture.md) · [`../kernel/workflow_engine.md`](../kernel/workflow_engine.md) — the architecture and Kernel component this document specializes
- [`error_handling_retry.md`](error_handling_retry.md) — how retry counters and error history (§4.1) are meant to be populated
- [ADR-0011](../../18_decision_log/adr/ADR-0011-persistence-and-workflow-state.md) — the persistence/workflow-state decision this document's §9 now cites as settled
- [`../../08_database/data_model.md`](../../08_database/data_model.md) §4 — the real `workflow.*` schema (`workflow_instances`, `workflow_events`, `workflow_steps`, `workflow_leases`)
- [`../../19_roadmap/feature_inventory.md`](../../19_roadmap/feature_inventory.md) · [`../../19_roadmap/implementation_status.md`](../../19_roadmap/implementation_status.md) — live build status
