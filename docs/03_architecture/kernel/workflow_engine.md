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

## Implementation Status (2026-07-30, updated 2026-08-12)

**Of the 13 components in §4's internal structure, 3 are real, 1 is real-but-narrower-than-named, and the rest do not exist as classes — though three of those (Failure & Retry Manager, Scheduler, Event Publisher) have since had their actual *job* done without a dedicated class; see the "Not built at all" bullet for each.** Verified directly against `kernel/src/ai_os_kernel/workflow_engine/`:

- **Real:** Workflow Definition Loader, Workflow Instance Manager, State Store (event log + snapshot, per [ADR-0011](../../18_decision_log/adr/ADR-0011-persistence-and-workflow-state.md)), Lease Manager (`SELECT … FOR UPDATE SKIP LOCKED`, heartbeat, expiry reclaim — tested). **The Lease Manager's own proactive reclaim (`WorkflowLeaseReaper.reap_once`) is now genuinely, continuously scheduled (2026-07-30)** — `run_reap_loop()` (`lease_reaper.py`), the identical background-task pattern `ai_os_kernel.capability_manager.health_poller.run_health_polling_loop` already proved for the Pack Health Collector, re-polls every `LEASE_REAP_INTERVAL_SECONDS` (15.0, half the 30-second lease duration every real caller in this codebase currently uses) for the life of the Kernel process, started in `_lifespan` and cleanly cancelled before shutdown. This module's own docstring used to name this as "a future worker process framework['s]" job — that framework's first two real instances (health polling, now lease reaping) both now exist. **This is narrower than §5.13's own "Scheduler" component** (delayed/scheduled workflow *starts* — a distinct, still-unbuilt capability), not a step toward it.
- **A third real instance of that "future worker process framework" now exists (2026-08-02, `P02-S01-M05-T12`, wired into `_lifespan` as of `P02-S01-M05-T14`): a multi-instance worker loop.** Every real advance path before this step (`WorkflowInstanceService.advance`, `WorkflowAdvanceRunner.run_once`/`run_to_completion`) required a caller to already name one specific `workflow_id`. `WorkflowWorkerLoop`/`run_worker_loop` (`worker_loop.py`) is the first real mechanism that *discovers* which instances are runnable and drives many of them concurrently, via a new, purpose-built `WorkflowInstanceRepository.list_runnable_instances` query (`status = 'running'`, no active lease — genuinely different from `list_instances`'s own paginated, newest-first listing for api_architecture.md §9). Each tick calls `WorkflowAdvanceRunner.run_once` for every discovered instance via one real `asyncio.gather` — one step per instance per tick, not `run_to_completion` per instance, so no single long-running instance can starve the rest of a batch. **Definition resolution now reads the real catalog (`P02-S01-M05-T14`), not a composition-injected mapping** — `WorkflowDefinitionCatalog` gained a real `get(definition_id, version)` reader, a lossless reconstruction from exactly the columns `register` already writes; `_advance_one` calls it per discovered instance, keyed by the full `(definition_id, definition_version)` pair (unlike `SubWorkflowStepExecutor`'s narrower, single-version-in-scope mapping, since a worker loop can discover instances spanning more than one still-running version). **Real, proven, and now genuinely running**: `run_worker_loop` starts in `_lifespan` as a fourth background task (`app.state.workflow_worker_task`), reusing the demo path's own `agent_registry`/`context_manager` for its step executor — the first of the `P02-S01-M05-T09`–`T12` "proven, unused" capabilities to move to "proven, running," proven live via a real Postgres-backed `TestClient` test with no manual `tick_once()` call (`tests/integration/test_worker_loop_in_lifespan.py`).

**Updated (`P03-S03-M30-T06`): this fixed, demo-scoped composition is now a real, enforced *scope*, not merely an unremarked default.** Investigation (building the real Human Approval decide route) found this loop's own fixed `DispatchingStepExecutor` — the identical one from the paragraph above, unchanged — genuinely cannot correctly advance `se.delivery_pipeline` instances: it has no `quality_gate`/`decision`/`human_approval` executor at all, and its `agent_registry` is the platform demo's own, which does not know this pack's agents. This was real, previously-latent exposure (never triggered before `se.delivery_pipeline` could pause): the moment an instance is resumed to `running`, this already-polling loop could independently rediscover and mis-advance it with the wrong composition, racing whatever correct caller resumed it. `WorkflowWorkerLoop` gained a new, real `exclude_definition_ids` (threaded from a matching `WorkflowInstanceRepository.list_runnable_instances` parameter), and `bootstrap.py` now excludes `se.delivery_pipeline` from this loop's own discovery entirely — closing the race, and making explicit what was always true only implicitly: this loop's own real scope is the platform demo workflow, not every real workflow definition system-wide.
- **Real but narrower than documented:** §5.6/§5.7's "Agent Invoker"/"Tool Invoker" are not separate invoker classes — they are `AgentStepExecutor` and `ToolStepExecutor` in `step_executor.py`, composed directly by a `DispatchingStepExecutor`.
- **Not built at all** (no matching class anywhere in the Kernel): Gate Coordinator (§5.8, though see the `quality_gate` bullet above for one real, narrow exception now layered on top of the halt behavior), Human Approval Manager (§5.9, though see the `human_approval` bullet above for the real, running implementation that also exists). **Event Publisher (§5.11) is no longer accurately "not built at all" either (updated 2026-08-12, `P02-S07-M17-T04`)**: no dedicated `EventPublisher` class exists, but §5.11's actual job — "Publishes significant workflow events to the Event Bus" — is now genuinely done for one event. `SqlWorkflowInstanceRepository.advance_workflow`'s terminal completion branch writes `workflow.completed` to `platform.event_outbox` inside its own already-open transaction (via `ai_os_kernel.event_bus.outbox_writer.write_outbox_event`), which the now-running `OutboxRelay` republishes onto the real `InProcessEventBus` — so §4's "in-process bus + transactional outbox" line describes real behaviour for the first time. Deliberately one event only: every other lifecycle row still goes solely to `workflow.workflow_events`, this engine's own event-sourcing log, and there is no `workflow.failed` event because `WorkflowInstanceStatus.FAILED` is never written by any production code (the same standing finding R-016 records). See `event_bus.md`'s own Implementation Status for the full chain and its remaining gaps. **Failure & Retry Manager (§5.10) is no longer accurately "not built at all" (updated 2026-07-30, widened the same day beyond gate failures to any retriable step-executor exception)**: `WorkflowAdvanceRunner`'s own bounded step-retry logic (see the retry bullet below) is a real, if narrow, instance of exactly this component's job — no dedicated `FailureRetryManager` class exists, no compensation/escalation decision exists for any exception, but "nothing decides retry" is no longer true unconditionally, and the decision is no longer gate-specific. **Scheduler (§5.13) is real too (updated 2026-08-03, `P02-S01-M05-T13`)** — closing the "delayed/scheduled workflow starts... neither of which decides *when* a not-yet-started instance should begin" gap this line used to name. `ai_os_kernel.workflow_engine.scheduler.WorkflowScheduler`/`run_scheduler_loop` starts a `created` instance once its own real, persisted `scheduled_at` (`workflow_instances.scheduled_at`, migration `0032`, nullable — `NULL` means no scheduled start was requested, every caller before this step) is genuinely due, applying the identical proven pattern the Lease Reaper/multi-instance worker loop above already establish: a bounded per-tick pass plus a real, continuously-running loop, started in `_lifespan` and drained through the same `GracefulShutdownCoordinator`. Proven end to end, real Postgres: a `created` instance with a due `scheduled_at` is genuinely started with no manual call, one not yet due is genuinely left alone, and a race with another caller that already started the same instance first is a real, isolated skip via the existing `WorkflowInvalidTransitionError`, never a per-tick failure.

**§5.5 Step Executor / §7.1's step types (updated 2026-08-01, `P02-S01-M05-T09`):** `StepType` declares exactly the 7 values this document expects (`agent`, `tool`, `decision`, `parallel`, `sub_workflow`, `quality_gate`, `human_approval`). `DispatchingStepExecutor` routes `agent` and `tool` to a real executor, optionally routes `quality_gate` to `ai_os_kernel.workflow_engine.quality_gate.QualityGateStepExecutor` — a real, blocking implementation for exactly one, composition-configured case (reads a named source step's own real, persisted output; raises `QualityGateFailedError` unless it reports `passed: True`) — originally the smallest real slice of the then-0%-built Quality Gate Engine (module 15), now (`P02-S06-M15-T09`, 2026-08-05) optionally cross-wired to that module's own real Gate Registry too (`gate_registry`/`gate_ids`, both `None`-default and additive — the pass/fail decision itself is unchanged; see `quality_gate_engine.md`'s own Implementation Status for the full detail) — and now optionally routes `decision` to `ai_os_kernel.workflow_engine.step_executor.DecisionStepExecutor`: a real, genuinely branching implementation. `WorkflowStep` gained a new, minimal, closed-vocabulary field-level contract for this — `condition` (`sourceStepId`/`field`/`equals`, evaluated against a named prior step's own real, persisted output) and `branches` (`{"true": stepId, "false": stepId}`), both required together, validated at load time (a forward reference to a not-yet-run source step, or a reference to an undeclared step, is rejected before any instance runs). The decision step's own execution persists `{"outcome": bool, "branch": stepId}` as its real output; `WorkflowInstanceService._resolve_next_step` reads that output back on the *next* `advance()` call to resolve the genuine next step, not `steps[index + 1]`. **This contract did not exist in any document before this step** — `workflow_architecture.md`'s own Step Contract section explicitly left decision-step branching undocumented, and building one was recorded there as "architecture this module does not own"; the product owner explicitly approved this minimal contract as part of the step itself rather than leaving the ticket blocked on a separate architecture step, a disclosed decision, not an unreviewed invention. No caller wires `decision_executor` into a real composition yet (mirroring `quality_gate_executor`'s own precedent: unwired in `bootstrap.py`, wired only where a real pipeline needs it) — every existing caller still falls through to `NoOpStepExecutor` unchanged. **Updated 2026-08-01 (`P02-S01-M05-T10`): `parallel` is real too.** `DispatchingStepExecutor` now optionally routes `parallel` to `ai_os_kernel.workflow_engine.step_executor.ParallelStepExecutor`, which genuinely runs its declared branches concurrently (real `asyncio.gather`/`asyncio.wait` over the same `agent_executor`/`tool_executor` a top-level `agent`/`tool` step already uses) and joins per the real, already-documented `joinPolicy` semantics (§7.1 below) — `all` waits for every branch before failing on any failure, `any` genuinely cancels every branch still running the moment one succeeds, `collect` never raises, reporting every branch's own real outcome as a partial result. `WorkflowStep` gained the matching field-level contract this needed and never had — `parallelSteps` (at least two nested, inline `agent`/`tool` steps; no nested `parallel`/`decision`/etc., since those carry cross-step reference semantics that cannot resolve inside an isolated branch), required alongside `joinPolicy`. **This contract did not exist in any document before this step either** — the same "architecture this module does not own" situation `decision` was in; the product owner again explicitly approved a minimal contract as part of the step. `parallel_executor` is unwired into any real composition too, the identical `quality_gate_executor`/`decision_executor` precedent. **Updated 2026-08-02 (`P02-S01-M05-T11`): `sub_workflow` is real too.** Unlike `decision`/`parallel`, this genuinely requires creating and tracking a separate `WorkflowInstance` — investigation confirmed `WorkflowDefinitionCatalog` is write-only (its own docstring: "No reader, no update, no delete"), so no real path exists to look up a `WorkflowDefinition` by id at runtime. `DispatchingStepExecutor` now optionally routes `sub_workflow` to `ai_os_kernel.workflow_engine.step_executor.SubWorkflowStepExecutor`, constructed with a plain, composition-level `{workflow_definition_id: WorkflowDefinition}` mapping (the identical shape `gate_sources`/`step_retry_targets` already establish) rather than a new catalog reader — the product owner explicitly chose this over building one, or over stopping and deferring to a dedicated architecture step. It genuinely creates the child instance, starts it, and runs it to completion through its own, independently-injected `WorkflowInstanceService`/`WorkflowAdvanceRunner` pair — the same classes any top-level workflow already uses — then joins on the completed child's own real, persisted last-step output (read via `current_step_id` + `_latest_completed_output`, since `WorkflowInstance.outputs` is never actually written by `advance_workflow`'s completion branch). `WorkflowStep` gained the matching field-level contract — `subWorkflowId`, a plain reference string, the identical shape `DecisionCondition`'s own `sourceStepId` already uses. See `../workflow/workflow_architecture.md`'s new "Sub-workflow Step Contract" section for the full reasoning. `sub_workflow_executor` is unwired into any real composition too, the identical precedent. **`WorkflowDefinitionCatalog` gained a real `get` reader as of `P02-S01-M05-T14`** (see the worker-loop bullet above) — `SubWorkflowStepExecutor` itself was deliberately left unchanged, still resolving via its own composition-injected mapping; switching it to the new reader is real, disclosed, unclaimed follow-up work, not done as part of this step. **`decision_executor` is no longer unwired everywhere (updated 2026-08-02, `P02-S01-M05-T15`).** `se.delivery_pipeline` — the one real, running pipeline this codebase has (`ai_os_kernel.workflow_engine.delivery_pipeline`) — now declares a real `decision` step, `route-after-build`, and its own `build_pipeline_trigger` now supplies `decision_executor=DecisionStepExecutor(repository)`, the identical composition already established for `quality_gate_executor` there. Chosen over `parallel` (concurrently running `lint`/`test` would require each branch's own output independently persisted and re-plumbed through `_GATE_SOURCES`/`_STEP_SOURCES` — real, already-proven behavior declined to disturb) and over `sub_workflow` (nothing in this pipeline invokes another whole `WorkflowDefinition`). `route-after-build` reads `build`'s own real, previously-uninspected `written` field and routes to `lint` unchanged when `true`, or straight to `test` (skipping a wasted Lint invocation and its own gate) when `false` — the last of the four `P02-S01-M05-T09`–`T12` "proven, unused" capabilities to reach a real, running composition; only `parallel`/`sub_workflow` remain unwired now. **`human_approval` is real too, as of `P03-S05-M14-T04`/`T05` (2026-08-02) — the last of the 7 step types to genuinely execute at all.** `DispatchingStepExecutor` now optionally routes `human_approval` to `ai_os_kernel.workflow_engine.human_approval.HumanApprovalStepExecutor`, which genuinely, durably pauses the real instance (`waiting_for_human`, `mark_waiting_for_human` — a new `WorkflowInstanceRepository` method) at a declared approval point and resumes only on a real, attributable decision (`SqlApprovalRepository.decide`) — never a timeout, closing R-001's own permanent hard rule (`risk_register.md`). A real bug found and fixed along the way: a second, separate `run_to_completion` call against an already-waiting instance used to misreport `FAILED` (via the pre-existing "instance must be running" lease-acquire guard) — fixed with a genuine `WorkflowRunOutcome.WAITING_FOR_HUMAN` (`advance_runner.py`) and a new `WorkflowInstanceService.get_instance` passthrough so the runner can tell the two cases apart. See `../governance/human_approval_points.md`'s own Implementation Status for the full design, and `human_approval.py`'s own module docstring for the real, disclosed scope this deliberately stops short of (no HTTP route, no RBAC, no automatic timeout/escalation sweep). **Stale as of `P03-S03-M30-T05`/`T06` (2026-08-02/03): `human_approval_executor` is no longer unwired.** `se.delivery_pipeline` gained a real `approve-git-push` point (`T05`), and `build_pipeline_trigger`'s own composition (factored into a shared `_build_pipeline_composition` helper alongside the new `resume_pipeline_after_approval`, `T06`) now supplies a real `human_approval_executor` too — the last of the five optional executors to reach a real, running composition. `T06` also added a real HTTP route (`ai_os_kernel.routes.approvals`, see `human_approval_points.md`'s own Implementation Status) closing the "no HTTP route" half of this paragraph's own disclosed scope; RBAC was already closed by `T06`'s own predecessor (`P03-S05-M14-T06`). Only the automatic timeout/escalation sweep remains genuinely unbuilt.

**A real, bounded retry sits on top of that gate halt — and now generalizes to any step-executor exception, not only gate failures (added 2026-07-30, widened the same day).** `WorkflowAdvanceRunner.run_to_completion` catches *any* exception a step raises and retries it only when it declares itself `getattr(exc, "retriable", None) is True` — an explicit, per-instance self-declaration, the identical convention `ai_os_kernel.llm_gateway.errors.LLMProviderError` already carries for its own provider-retry logic — and its `step_id` (attached to every exception, uniformly, by `WorkflowInstanceService.advance`) has a configured retry target (`step_retry_targets`, composition-level config — `se.delivery_pipeline` retries a failed `build`, `quality-gate-lint-clean`, or `quality-gate-tests-pass` all from `build`) **and** `WorkflowDefinition.retry_policy` is declared. `QualityGateFailedError` self-declares `retriable = True` unconditionally (a gate retry is genuine corrective work — see that class's own docstring); most other Workflow Engine exceptions (`AgentOutputValidationError`, `ToolOutputValidationError`, `ToolSandboxRequiredError`, `AgentNotRegisteredError`, `ToolNotRegisteredError`, `EntrypointLoadError`, `PackNotActivatedError`, `PromptedAgentInputError`) declare nothing, so they retain the exact prior "fail immediately" behavior; `AgentRegistryError`/`ToolRegistryError` are deliberately left undecided (each conflates a transient and a permanent nature in one type — see `advance_runner.py`'s own module docstring). A retriable failure resets `current_step_id` backward via `WorkflowInstanceService.retry_after_step_failure` (a new `WorkflowInstanceRepository.reset_current_step`, CAS-guarded identically to `advance_workflow`, appending a real `workflow.step_retry_scheduled` event) so the next iteration genuinely re-executes from the retry target. Genuinely bounded on both axes `error_handling_retry.md` §4 requires (attempt count **and** wall-clock duration, tracked per step, in-process, for the life of one `run_to_completion` call) — exhausting either falls through to the identical `FAILED` result this method already returned before this feature existed. `advance_workflow`'s own previously-hardcoded `attempt = 1` is now a real, computed value (`MAX(attempt)+1` for that `(workflow_id, step_name)`) — required for a retried step to get a genuine second `workflow_steps` row at all, given the existing `uq_workflow_steps_workflow_id_step_name_attempt` constraint; zero behavior change for every step that still only ever runs once.

**A genuinely failed attempt is now genuinely recorded, not silently discarded (added 2026-07-30).** Before this, a raised step exception meant `advance_workflow` — the only method that ever wrote a `workflow_steps` row — was never reached, so a failed attempt left no trace at all; only an eventual successful retry (or nothing, if a bound was exhausted) was ever persisted, defeating quality_gate_engine.md §9's own "every gate execution must record ... error details" requirement. `WorkflowInstanceService.advance` now wraps the executor call in its own `try`/`except`: on any exception, a new `WorkflowInstanceRepository.record_failed_attempt` writes a real `workflow_steps` row (`status="failed"`, real `error` detail, the identical `MAX(attempt)+1`-computed `attempt` number `advance_workflow` uses) and a real `step.failed` event, guarded by the identical CAS pattern, before the *original* exception is re-raised completely unchanged (a bare `raise`) — `WorkflowAdvanceRunner`'s own retry/failure logic sees the exact same exception it always has; only the new persisted row is added. This applies to every step-executor exception, not only `QualityGateFailedError` — an `AgentOutputValidationError`/`ToolOutputValidationError` now also leaves a real, honest trace.

**§7 State Model:** verified against `workflow_engine/instance.py` — the 9-state list is real as an enum. **Correction (2026-08-08, found during a full pre-completion health audit — this line self-contradicted the Human Approval update elsewhere in this same file's own history):** `created`, `running`, `waiting_for_human`, and `completed` are genuinely written — `waiting_for_human` via `WorkflowInstanceRepository.mark_waiting_for_human`, real since `P03-S05-M14-T04`/`T05` (2026-08-02), five days before this line was last touched. `waiting_for_retry`, `quality_gate_failed`, `compensating`, and `failed` remain genuinely declared, unreached — see `../workflow/state_management.md`'s own Implementation Status for the full breakdown. **`cancelled` is real too, as of 2026-08-10 (`P06-S01-M36-T04`)** — `WorkflowInstanceRepository.cancel`/`POST /api/v1/workflows/{id}/cancel` (`api_architecture.md` §6.1), the last of the nine declared states this section's own text above still called unreached, closed as its own real, disclosed slice: only `created`/`running`/`waiting_for_human` are guarded as cancellable, since those are the only three of the nine real states any writer today ever actually produces. **Still true after the real `quality_gate` step type landed (2026-07-30, see the bullet above)**: a blocking gate failure raises `QualityGateFailedError`, halting `WorkflowAdvanceRunner.run_to_completion` with a structured `WorkflowRunOutcome.FAILED` — it does not write `workflow_instances.status = quality_gate_failed`, the identical "raise, don't write a new status" shape every other step-level failure (`AgentOutputValidationError`, etc.) already has; `quality_gate_failed` remains declared, unreached.

**§7.1 Concurrency, leasing, and idempotency is real and tested**: the lease claim/heartbeat/reclaim cycle and the `(workflow_id, step_name, attempt)` uniqueness constraint both exist and are exercised by the test suite. **Updated 2026-08-01 (`P02-S01-M05-T10`): the "declared in the data model" claim this line used to make about join policies was verified and found stale — no such structured declaration existed anywhere (`data_model.md`'s own `catalog.workflow_definitions.graph` is an opaque JSONB blob, nothing more specific).** Parallel join policies (`all`/`any`/`collect`) are real and enforced now — see the Step Executor bullet above. **`foreach`/`max_fanout` bounds are real too, as of `P08-S02-M30-T01` (2026-08-09) — closing this document's own previously-accurate "not even one of `StepType`'s 7 real values" gap.** `StepType` now has 8 real values; `WorkflowStep` gained the matching field-level contract, `ForeachSpec` (`sourceStepId`/`itemsField`/`maxFanOut`, all required together, the identical "closed-vocabulary, required-together" shape `DecisionCondition`/`ParallelStep`'s own contracts already established) plus the same `subWorkflowId` reference `sub_workflow` already uses. `DispatchingStepExecutor` now optionally routes `foreach` to `ai_os_kernel.workflow_engine.step_executor.ForeachStepExecutor`, which reads a named prior step's own real, persisted list output (`_latest_completed_output`, the identical helper `DecisionStepExecutor`/`SubWorkflowStepExecutor` already reuse), refuses the whole step before creating any child if the real item count exceeds the declared `maxFanOut` (ADR-0021's own "no unbounded agent-driven loop" rule), and otherwise creates, starts, and runs one real, separate child `WorkflowInstance` to completion per real item — `SubWorkflowStepExecutor`'s own per-item mechanism, reused sequentially rather than concurrently (a real, disclosed, narrower scope than `ParallelStepExecutor`; ADR-0021 names `foreach` as a bounded fan-out over a plan artifact, not a concurrency primitive). Proven against a real Postgres container: a two-item plan artifact (`technical-planner`'s own real `tasks` output shape) genuinely fans out into two real, separate, completed child instances, and an over-bound item count is genuinely refused before any child is created. **A real, previously-latent database gap found and fixed along the way**: `workflow.workflow_steps.ck_workflow_steps_step_type` (`0002_workflow_steps`) enumerated the same seven step-type literals `_STEP_TYPES` in `ai_os_kernel.persistence.schema` still declared — the first genuinely persisted `foreach` step (success or failure) raised a Postgres `CheckViolationError`, caught only by a real end-to-end run, never by `mypy`/unit tests with fakes. Fixed by migration `0036_workflow_steps_foreach` (drop/recreate the named constraint) plus the matching `_STEP_TYPES` update. **Updated the same day, later step: `foreach_executor` is now wired into a real composition too.** Chaining it into `se.product_creation`'s own step 8 first surfaced a second, separate, genuine mismatch: `technical-planner`'s own real plan-item shape (`taskId`/`title`/`description`) did not satisfy `se.implement_task`'s own then-real `inputs` schema (`{task: string}`, `additionalProperties: false`) — two independently-built, already-`done` tickets (`P03-S02-M29-T08`, `P08-S02-M30-T02`) whose contracts were never checked against each other until a real `foreach` step tried to connect them. Resolved via `AskUserQuestion`: `se.implement_task`'s own `inputs` were widened to `title`/`description` (matching `PlanTask` directly) rather than adding a per-item field-mapping mechanism to `foreach` itself. `ai_os_kernel.workflow_engine.product_creation` now builds a real `ForeachStepExecutor` reusing `implement_task.py`'s own `build_implement_task_instance_service` (a new, shared factory, so both callers build the identical child composition rather than a second, drifting copy). Proven end to end against a real Postgres container: the full 8-step `se.product_creation` run, including a real, one-task fan-out into one real, separate, completed `se.implement_task` child, reaches `WorkflowRunOutcome.COMPLETED`. **A second real, previously-latent gap found and fixed**: `ForeachStepExecutor`/`SubWorkflowStepExecutor` both fix `principal_id` at construction time — harmless for every test fixture so far, but genuinely wrong for a real trigger built once at startup and reused across many calls with different real callers, since it cannot know the real, per-call principal in advance. `build_product_creation_trigger` now builds its whole composition fresh per call, using that call's real `principal_id`; `resume_product_creation_after_approval` discovers it from the paused instance's own already-persisted record instead. `P08-S02-M30-T01` is now `done`.

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
