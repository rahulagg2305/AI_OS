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

## Implementation Status (2026-07-30)

**Of the 13 components in §4's internal structure, 3 are real, 1 is real-but-narrower-than-named, and the other 9 do not exist as classes.** Verified directly against `kernel/src/ai_os_kernel/workflow_engine/`:

- **Real:** Workflow Definition Loader, Workflow Instance Manager, State Store (event log + snapshot, per [ADR-0011](../../18_decision_log/adr/ADR-0011-persistence-and-workflow-state.md)), Lease Manager (`SELECT … FOR UPDATE SKIP LOCKED`, heartbeat, expiry reclaim — tested). **The Lease Manager's own proactive reclaim (`WorkflowLeaseReaper.reap_once`) is now genuinely, continuously scheduled (2026-07-30)** — `run_reap_loop()` (`lease_reaper.py`), the identical background-task pattern `ai_os_kernel.capability_manager.health_poller.run_health_polling_loop` already proved for the Pack Health Collector, re-polls every `LEASE_REAP_INTERVAL_SECONDS` (15.0, half the 30-second lease duration every real caller in this codebase currently uses) for the life of the Kernel process, started in `_lifespan` and cleanly cancelled before shutdown. This module's own docstring used to name this as "a future worker process framework['s]" job — that framework's first two real instances (health polling, now lease reaping) both now exist. **This is narrower than §5.13's own "Scheduler" component** (delayed/scheduled workflow *starts* — a distinct, still-unbuilt capability), not a step toward it.
- **Real but narrower than documented:** §5.6/§5.7's "Agent Invoker"/"Tool Invoker" are not separate invoker classes — they are `AgentStepExecutor` and `ToolStepExecutor` in `step_executor.py`, composed directly by a `DispatchingStepExecutor`.
- **Not built at all** (no matching class anywhere in the Kernel): Gate Coordinator (§5.8, though see the `quality_gate` bullet above for one real, narrow exception now layered on top of the halt behavior), Human Approval Manager (§5.9), Event Publisher (§5.11), Scheduler (§5.13, delayed/scheduled workflow starts — distinct from the Lease Manager's own now-real reap scheduling above). **Failure & Retry Manager (§5.10) is no longer accurately "not built at all" (updated 2026-07-30)**: `WorkflowAdvanceRunner`'s own bounded gate-retry logic (see the `quality_gate` bullet above) is a real, if narrow, instance of exactly this component's job — no dedicated `FailureRetryManager` class exists, and every non-gate failure still raises with no retry/compensate/escalate decision at all, but "nothing decides retry" is no longer true unconditionally.

**§5.5 Step Executor / §7.1's step types (updated 2026-07-30):** `StepType` declares exactly the 7 values this document expects (`agent`, `tool`, `decision`, `parallel`, `sub_workflow`, `quality_gate`, `human_approval`). `DispatchingStepExecutor` routes `agent` and `tool` to a real executor, and now optionally routes `quality_gate` to `ai_os_kernel.workflow_engine.quality_gate.QualityGateStepExecutor` — a real, blocking implementation for exactly one, composition-configured case (reads a named source step's own real, persisted output; raises `QualityGateFailedError` unless it reports `passed: True`), the smallest real slice of the still-0%-built Quality Gate Engine (module 15). A caller that does not supply one — every caller except `se.delivery_pipeline`'s own trigger — still falls through to `NoOpStepExecutor` unchanged. `decision`, `parallel`, `sub_workflow`, and `human_approval` remain fully `NoOpStepExecutor`-handled, with no executed behavior today.

**A real, bounded retry now sits on top of that gate halt (added 2026-07-30).** `WorkflowAdvanceRunner.run_to_completion` catches `QualityGateFailedError` and, when the failing gate's own id has a configured retry target (`gate_retry_targets`, composition-level config — `se.delivery_pipeline` retries a failed `quality-gate-tests-pass` from `build`) **and** `WorkflowDefinition.retry_policy` is declared, calls `WorkflowInstanceService.retry_after_gate_failure` — resetting `current_step_id` backward (a new `WorkflowInstanceRepository.reset_current_step`, CAS-guarded identically to `advance_workflow`, appending a real `workflow.step_retry_scheduled` event) so the next iteration genuinely re-executes from the retry target. Genuinely bounded on both axes `error_handling_retry.md` §4 requires (attempt count **and** wall-clock duration, tracked per gate, in-process, for the life of one `run_to_completion` call) — exhausting either falls through to the identical `FAILED` result this method already returned before this feature existed. `advance_workflow`'s own previously-hardcoded `attempt = 1` is now a real, computed value (`MAX(attempt)+1` for that `(workflow_id, step_name)`) — required for a retried step to get a genuine second `workflow_steps` row at all, given the existing `uq_workflow_steps_workflow_id_step_name_attempt` constraint; zero behavior change for every step that still only ever runs once. Scoped narrowly to gate failures only — every other exception still fails the run immediately, unchanged.

**A genuinely failed attempt is now genuinely recorded, not silently discarded (added 2026-07-30).** Before this, a raised step exception meant `advance_workflow` — the only method that ever wrote a `workflow_steps` row — was never reached, so a failed attempt left no trace at all; only an eventual successful retry (or nothing, if a bound was exhausted) was ever persisted, defeating quality_gate_engine.md §9's own "every gate execution must record ... error details" requirement. `WorkflowInstanceService.advance` now wraps the executor call in its own `try`/`except`: on any exception, a new `WorkflowInstanceRepository.record_failed_attempt` writes a real `workflow_steps` row (`status="failed"`, real `error` detail, the identical `MAX(attempt)+1`-computed `attempt` number `advance_workflow` uses) and a real `step.failed` event, guarded by the identical CAS pattern, before the *original* exception is re-raised completely unchanged (a bare `raise`) — `WorkflowAdvanceRunner`'s own retry/failure logic sees the exact same exception it always has; only the new persisted row is added. This applies to every step-executor exception, not only `QualityGateFailedError` — an `AgentOutputValidationError`/`ToolOutputValidationError` now also leaves a real, honest trace.

**§7 State Model:** verified against `workflow_engine/instance.py` — the 9-state list is real as an enum, but only `created`, `running`, `completed` are ever written; see `../workflow/state_management.md`'s own Implementation Status for the full breakdown (`waiting_for_human`, `waiting_for_retry`, `quality_gate_failed`, `compensating`, `failed`, `cancelled` are all declared, unreached). **Still true after the real `quality_gate` step type landed (2026-07-30, see the bullet above)**: a blocking gate failure raises `QualityGateFailedError`, halting `WorkflowAdvanceRunner.run_to_completion` with a structured `WorkflowRunOutcome.FAILED` — it does not write `workflow_instances.status = quality_gate_failed`, the identical "raise, don't write a new status" shape every other step-level failure (`AgentOutputValidationError`, etc.) already has; `quality_gate_failed` remains declared, unreached.

**§7.1 Concurrency, leasing, and idempotency is real and tested**: the lease claim/heartbeat/reclaim cycle and the `(workflow_id, step_name, attempt)` uniqueness constraint both exist and are exercised by the test suite. Parallel join policies (`all`/`any`/`collect`) and `foreach`/`max_fanout` bounds are declared in the data model but have no executor to enforce them, since `parallel` and `foreach` are both currently `NoOpStepExecutor`-handled.

Authoritative, always-current status: `../../19_roadmap/feature_inventory.md` (module 5, Workflow Engine) and `../../19_roadmap/implementation_status.md`. Build history: `../../19_roadmap/history/003_workflow_engine_core.md`.

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

This document defines the detailed architecture of the Workflow Engine. Storage technology is no longer an open question (PostgreSQL, per [ADR-0011](../../18_decision_log/adr/ADR-0011-persistence-and-workflow-state.md)) — see the Implementation Status section near the top for exactly which of §4's 13 components exist, which of §7's 9 states are reachable, and which of §7's 7 step types execute real logic today.

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

---

## 13. Related Documents

- [`../workflow/workflow_architecture.md`](../workflow/workflow_architecture.md) · [`../workflow/state_management.md`](../workflow/state_management.md) — the architecture this document implements and the state-persistence detail underneath it
- [`../workflow/error_handling_retry.md`](../workflow/error_handling_retry.md) — the retry/compensation ownership this document's §5.10/§8 assign to the (unbuilt) Failure & Retry Manager
- [`../quality/quality_gates_framework.md`](../quality/quality_gates_framework.md) — the Quality Gate Engine the (unbuilt) Gate Coordinator is meant to call
- [`../agents/agent_communication.md`](../agents/agent_communication.md) — the Agent Invoker's real counterpart, `AgentStepExecutor`
- [ADR-0006](../../18_decision_log/adr/ADR-0006-quality-gates-are-mandatory.md) · [ADR-0011](../../18_decision_log/adr/ADR-0011-persistence-and-workflow-state.md) — the two decisions §4 and §7 cite directly
- [`../../19_roadmap/feature_inventory.md`](../../19_roadmap/feature_inventory.md) · [`../../19_roadmap/implementation_status.md`](../../19_roadmap/implementation_status.md) — live build status
