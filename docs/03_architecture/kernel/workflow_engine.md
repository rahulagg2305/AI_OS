# Workflow Engine Architecture – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Workflow Engine Architecture  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## 1. Purpose

This document defines the detailed architecture of the **Workflow Engine**, the central orchestration component of the AI_OS Platform Kernel.

The Workflow Engine is responsible for executing workflows, coordinating agents, managing state, enforcing Quality Gates, handling failures, and supporting human-in-the-loop decisions.

This document is subordinate to:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Kernel Architecture  
5. Workflow Architecture  
6. Agent Architecture & Agent Contract  
7. Quality Gates Framework  

---

## 2. Responsibilities

The Workflow Engine shall:

- Load and validate workflow definitions
- Manage the full lifecycle of workflow instances
- Maintain durable workflow state
- Schedule and invoke Agents
- Invoke Tools through approved interfaces
- Enforce Quality Gates
- Handle Human Approval Points
- Manage retries, timeouts, and failure recovery
- Emit full observability data (logs, traces, metrics)
- Support long-running and resumable workflows
- Remain completely domain-agnostic

---

## 3. Design Goals

- Deterministic execution where practical
- High resilience and recoverability
- Full auditability and replay support
- Clear separation from domain logic
- Support for both sequential and parallel steps
- Extensible through Capability Packs (workflows are contributed by packs)

---

## 4. High-Level Internal Structure

```text
Workflow Engine
│
├── Workflow Definition Loader
├── Workflow Validator
├── Workflow Instance Manager
├── State Store              event log + snapshot, one transaction
├── Lease Manager            SKIP LOCKED claim, heartbeat, expiry reclaim
├── Step Executor            idempotency-keyed
├── Agent Invoker
├── Tool Invoker
├── Gate Coordinator         requests gates; owns the CONSEQUENCE of a result
├── Human Approval Manager
├── Failure & Retry Manager
├── Event Publisher          in-process bus + transactional outbox
├── Metrics & Tracing
└── Scheduler                delayed starts, concurrency limits
```

**Note on the Gate Coordinator (v2.0).** v1.0 listed a "Quality Gate Executor" here, duplicating the Quality Gate Engine. The split is now explicit: the **Quality Gate Engine** resolves and executes gates and returns structured results; the **Gate Coordinator** in this engine decides what a result *means* for the workflow (proceed, retry, corrective loop, compensate, escalate). Execution belongs to the Engine, consequence belongs to the Workflow Engine ([ADR-0006](../../18_decision_log/adr/ADR-0006-quality-gates-are-mandatory.md)).

---

## 5. Key Components

### 5.1 Workflow Definition Loader
- Loads workflow definitions declared by Capability Packs (via Manifest)
- Supports versioned workflow definitions

### 5.2 Workflow Validator
- Validates workflow structure against the Workflow Contract
- Checks agent and tool references
- Validates Quality Gate and Human Approval Point declarations

### 5.3 Workflow Instance Manager
- Creates, runs, pauses, resumes, and completes workflow instances
- Maintains the current status of every running workflow

### 5.4 State Store
- Durable storage of workflow state
- Must support resumption after process restarts
- State transitions must be append-only / auditable

### 5.5 Step Executor
- Executes individual steps (Agent, Tool, Decision, Parallel, Sub-workflow, Quality Gate, Human Approval)

### 5.6 Agent Invoker
- Prepares context for the agent
- Calls the agent through its published contract
- Collects structured output

### 5.7 Tool Invoker
- Invokes registered tools with proper permission checks
- Captures tool inputs, outputs, and errors

### 5.8 Gate Coordinator
- Requests gate execution from the **Quality Gate Engine** at declared points
- Interprets the returned result and applies the consequence: proceed, retry, enter a corrective loop, compensate, or escalate to a human
- Blocks progression on any blocking failure
- Persists gate results as workflow events

It does not evaluate gate logic itself; that is the Quality Gate Engine's responsibility.

### 5.9 Human Approval Manager
- Pauses the workflow
- Notifies the appropriate human channel (Dashboard / Voice / API)
- Resumes only after explicit approval or rejection

### 5.10 Failure & Retry Manager
- Applies the retry policy defined in the workflow
- Supports compensation / rollback actions
- Escalates to human when retries are exhausted

### 5.11 Event Publisher
- Publishes significant workflow events to the Event Bus
- Enables other components and the Dashboard to react

### 5.12 Metrics & Tracing
- Emits Trace ID, Workflow ID, step timings, token usage, cost, and outcomes
- Supports full execution replay

### 5.13 Scheduler
- Supports delayed and scheduled workflow starts
- Manages concurrent workflow execution limits

---

## 6. Execution Flow (Happy Path)

1. Workflow definition is loaded and validated
2. New workflow instance is created
3. Initial context is prepared
4. Steps are executed in order (or according to the graph)
5. For each Agent step:
   - Context is built
   - Agent is invoked
   - Output is validated
6. Quality Gates are evaluated at defined points
7. Human Approval Points pause execution when required
8. Final output is produced
9. Knowledge and metrics are updated
10. Workflow is marked Completed

---

## 7. State Model (Simplified)

**This is the canonical workflow state list.** It is the single authority; `../workflow/state_management.md` and the data model reference it rather than restating an abbreviated version.

| State | Meaning |
|---|---|
| `created` | Instance created, not yet leased |
| `running` | Leased by a worker and executing |
| `waiting_for_human` | Paused at a Human Approval Point; durable, may last days |
| `waiting_for_retry` | Backoff before a retry attempt |
| `quality_gate_failed` | A blocking gate failed; awaiting corrective action or escalation |
| `compensating` | Executing compensation steps after a failure |
| `completed` | Finished successfully |
| `failed` | Terminal failure |
| `cancelled` | Cancelled by an authorized principal |

Every transition is an appended event carrying the previous state, the new state, the reason, and the triggering event — written in the same transaction as the snapshot update, so state and log can never disagree ([ADR-0011](../../18_decision_log/adr/ADR-0011-persistence-and-workflow-state.md)).

### 7.1 Concurrency, leasing, and idempotency

The properties that make multiple workers safe:

- **Leasing.** A worker claims an instance with `SELECT … FOR UPDATE SKIP LOCKED`, then heartbeats. A lease that expires without a heartbeat is reclaimed by another worker.
- **Idempotency keys.** Every step execution carries a key derived from `(workflow_id, step_name, attempt)`. A reclaimed step re-executes safely; a completed step is not re-run.
- **Workspace isolation.** Each instance holds its own working copy — mandatory, not best-effort. This is what makes parallel and `foreach` steps safe against concurrent-write corruption.
- **Parallel join semantics.** A `parallel` step declares its join policy: `all` (any branch failure fails the step), `any` (first success wins, others cancelled), or `collect` (all branches complete; failures returned as partial results). A parallel step with no declared policy fails validation rather than defaulting silently.
- **Bounded fan-out.** `foreach` declares `max_fanout`; loops declare maximum iterations **and** a token/cost ceiling.

---

## 8. Error Handling Strategy

- Transient errors → Retry according to policy
- Permanent errors → Fail the step / workflow or escalate
- Quality Gate failures → Block and optionally allow corrective re-entry
- Human rejection → Follow the defined rejection path

---

## 9. Observability Requirements

Every workflow instance must produce:

- Unique Workflow ID
- Trace ID
- Full step-by-step execution log
- Agent and Tool invocation records
- Quality Gate results
- Human decisions
- Timing and cost metrics
- Final status

The system must support later replay of the execution.

---

## 10. Extensibility

- New workflows are contributed exclusively by Capability Packs
- The Workflow Engine itself should not contain domain-specific workflows
- New step types may be added only through controlled Kernel evolution

---

## 11. Current Status

This document defines the detailed architecture of the Workflow Engine.

Implementation-level design (interfaces, data models, storage technology choices, etc.) will be refined during actual development.

---

## 12. Final Authority

Order of precedence:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Kernel Architecture  
5. Workflow Architecture  
6. Workflow Engine Architecture  
7. Source Code
