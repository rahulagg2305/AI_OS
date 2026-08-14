# Quality Gate Engine Design – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Quality Gate Engine Design  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## Implementation Status (2026-07-31; Gate Registry added 2026-08-05; pack-declared gate definitions added 2026-08-05; QualityGateStepExecutor cross-wired to the registry 2026-08-05; Policy Enforcer added 2026-08-06; concurrent multi-gate evaluation added 2026-08-06)

**The Gate Registry is now real (`P02-S06-M15-T05`) — the first real code this package has ever had.** `ai_os_kernel.quality_gate_engine.registry.InMemoryGateRegistry` resolves a declared `gateId` to a real `GateDefinition`, derived (`derive_gate_definitions`) from a pack manifest's own real, already-schema-validated `qualityGates[]` array (`platform_sdk/schemas/manifest.schema.json`'s own complete Gate Contract shape — `id`/`name`/`version`/`description`/`entrypoint`/`type`/`severity`/`successCriteria`/`timeoutSeconds`) — no new `catalog.quality_gates` table (a real, undecided schema-authority fork this ticket's own scope did not need to open). Gate ids are resolved raw, never derived with a `pack_id/` prefix the way agent/tool ids are — confirmed via direct inspection of the one real reference that exists today (`delivery_pipeline.yaml`'s own top-level `qualityGates: [se.build_lint_clean, se.build_tests_pass]`, already in this un-prefixed, dot-namespaced shape). A real collision across two packs' own declared ids is refused (`DuplicateGateIdError`), not silently resolved by picking a winner. Kernel-owned gates are a disclosed, deliberate scope reduction: §10 documents that ownership category, but no concrete Kernel-level gate exists anywhere with real content to resolve. Proven with real, schema-conformant test fixtures (independently validated against the real JSON Schema via `jsonschema.validate()`), not fabricated data — the identical "build the real component before anything wires it in" precedent already established for `KnowledgeResolver`/`MemoryResolver` before their own later production-wiring tickets (`P02-S03-M08-T05`/`T06`, wired `T12`/`T13`). Wiring this registry against the real Software Engineering pack's own manifest happened next, `P02-S06-M15-T06` — see below.

**The one real pack's own manifest now genuinely declares both real gates (2026-08-05, `P02-S06-M15-T06`).** `capability_packs/software-engineering/manifest.yaml` gained a real top-level `qualityGates:` section — `se.build_lint_clean`/`se.build_tests_pass`, the exact ids `delivery_pipeline.yaml`'s own `qualityGates:` list already referenced with no real definition to back them. Each `entrypoint` names the real Lint/QA-Test Agent class that actually performs the check today (`ai_os_pack_software_engineering.agents.lint:LintAgentEntrypoint` / `...agents.verification:TestAgentEntrypoint`) — quality_gates_framework.md §4's own "evaluationMethod: how the gate is evaluated," not a standalone gate-evaluator class (none exists yet; Gate Executor remains unbuilt). `successCriteria` honestly describes the one real mechanism that actually enforces these gates today (`QualityGateStepExecutor` reading the source step's own real `passed` field) — the `entrypoint` string itself is schema-only, nothing resolves or invokes it yet, the identical "schema only, nothing reads this column yet" precedent `catalog.agents.entrypoint`/`catalog.tools.entrypoint` already establish. Proven against the real, on-disk manifest, loaded through the real, schema-validating `ManifestLoader` (never a hand-typed fixture): both gates genuinely resolve through the real Gate Registry with their real, declared fields intact.

**`QualityGateStepExecutor` now genuinely resolves through the registry too (2026-08-05, `P02-S06-M15-T09`).** New, optional `gate_registry`/`gate_ids` constructor parameters (`None` by default — every existing caller/test unaffected) let a composition supply the real registry plus the identical composition-level `{workflow_step_id: real gateId}` mapping shape `gate_sources` already establishes (`WorkflowStep` has no field of its own linking a step to a pack-declared gate id either). **The evaluation itself is completely unchanged** — it is still the identical `source_output.get(success_field)` check this executor already made; only the returned `gateId`/`gateVersion` become the real, registry-resolved values instead of the workflow-local step id.

**Evaluating a result is now separated from enforcing its severity (2026-08-06, `P02-S06-M15-T07`, the Policy Enforcer) — the one real, disclosed limit `P02-S06-M15-T09` left open.** A resolved gate's real `severity` now decides the *consequence* of a non-passing evaluation, never the evaluation itself: `"blocking"` (the default when no registry entry resolves, matching every prior caller unchanged) still raises `QualityGateFailedError`, halting the run exactly as before; `"warning"` returns normally instead, with `severity: "warning"` in the real, persisted output — genuinely recorded (`gate_result_recorder.py`'s own `severity` column now reads this real value instead of a hardcoded constant, so a warning gate's own result is never mislabeled `"blocking"`), never blocking progression. The now-dead `UnsupportedGateSeverityError` (its only reason to exist) was removed. Both of the one real pack's own declared gates remain `severity="blocking"` today, so this is a genuine zero-behaviour-change for `se.delivery_pipeline`'s own real runs — proven for the new, real `"warning"` case with a real, schema-conformant `GateDefinition` fixture in `test_quality_gate_step_executor.py` (no manifest anywhere declares a warning-severity gate yet — the identical "build real, wire later" precedent the Gate Registry itself was built under).

**§5's own "gates are executed (optionally in parallel when safe)" is now real too (2026-08-06, `P02-S06-M15-T08`) — for one step checking several independent gates, not the Workflow Engine's own `parallel` step type.** Investigated reusing `ParallelStepExecutor` first and ruled it out on the validator's own already-documented grounds: `WorkflowStep`'s `parallelSteps` branches are restricted to `agent`/`tool` precisely because a nested branch's own cross-step reference cannot resolve inside an isolated concurrent branch — a `quality_gate` branch's `gate_sources`/`sourceStepId` reference has the identical problem. Instead, `QualityGateStepExecutor` gained a new, optional `gate_checks: Mapping[str, Sequence[GateCheck]]` (a step id → several real `(gateId, sourceStepId)` pairs) — real `asyncio.gather` concurrency over each check's own registry resolution (never a sequential loop), joined under an all-must-pass consequence policy identical in spirit to `ParallelStepExecutor`'s own `all` (every check runs to real completion before any consequence is decided; a failing `"warning"` check never blocks, the identical Policy Enforcer distinction `P02-S06-M15-T07` established). Requires a real `gate_registry` — a multi-gate step with no registry to resolve real `gateId`/`severity` from has no real gate to concurrently evaluate. Proven by real wall-clock timing (three checks each genuinely resolving in 0.2s complete in well under 0.6s) — the identical technique `ParallelStepExecutor`'s own tests already established. Unwired into any real composition yet (no manifest anywhere declares a multi-gate checkpoint today), the identical "build real, wire later" precedent this whole package has followed since the Gate Registry itself.

**Everything else in this package itself remains unbuilt** — no Gate Executor for a *single* gate's own execution mechanics, no Observability Hook (§4 above); Result Store/Emitter is real but lives in the Workflow Engine, not this package (see §9's own writer, below). That full design remains mostly unbuilt.

**§9's own `evaluation.gate_results` writer now exists — the Evaluation Engine's first real consumer (added 2026-07-31)**, built in the Workflow Engine (`ai_os_kernel.workflow_engine.gate_result_recorder.SqlGateResultRecorder`), not this package, the identical "the functional gap is closed elsewhere" shape already established for the executor itself below. `WorkflowInstanceService._maybe_record_gate_result` reads back a resolved `quality_gate` step's own real, just-persisted `workflow_steps` row (after `record_failed_attempt`/`advance_workflow` — not before, since only they compute the real `attempt` number) and hands it to the injected recorder, for both real gate categories (Testing, Static Analysis), pass or fail. See `evaluation_engine.md`'s own Implementation Status and `gate_result_recorder.py`'s own module docstring for the full placement reasoning and column mapping (including the one honest, currently-always-zero limitation: `duration_ms`, since the underlying `started_at`/`completed_at` timestamps are stamped identically at write time).

**But the `quality_gate` workflow step type is no longer a no-op, for one real, narrow, deliberately-scoped case.** `ai_os_kernel.workflow_engine.quality_gate.QualityGateStepExecutor` (2026-07-30) reads a configured source step's own real, persisted output and raises `QualityGateFailedError` — genuinely halting `WorkflowAdvanceRunner.run_to_completion` (`WorkflowRunOutcome.FAILED`) — unless that output's `passed` field is literally `True`. `se.delivery_pipeline` (the Software Engineering pack's own workflow) is its first real caller: a new `quality-gate-tests-pass` step now sits between `test` and `documentation`, so a genuinely failing test run halts the pipeline before Documentation ever runs. This is this step's own approved framing, verbatim: "formalizing that pass/fail into a real, declared quality_gate-type workflow step that actually blocks progression on failure, rather than a brand new gate concept" — not a substitute for the full engine above, which remains the eventual, larger destination (the Gate Registry is real now, `P02-S06-M15-T05` — see above; still needed: pack-declared gate ids actually resolving through it, a real Gate Executor, parallel gate execution). Proof: `tests/integration/workflow_engine/test_delivery_pipeline.py`'s own new test, a genuinely failing build (`sys.exit(1)`) halting the pipeline with Documentation never invoked.

**A real, bounded retry now sits on top of that halt (added 2026-07-30, same day).** A failed gate no longer halts on its very first failure when its own workflow declares a `retryPolicy` and the caller has configured a retry target for it: `WorkflowAdvanceRunner.run_to_completion` retries from a named earlier step (`se.delivery_pipeline` retries from `build`, not the whole pipeline — Requirements Analyst's/Architecture's own design decisions are unrelated to why a build/test cycle failed), bounded by both `max_attempts` and `max_duration_seconds`. This answers §7's own "support re-evaluation after corrective actions" for exactly this one case — see `../../19_roadmap/history/` and `workflow_engine.md`'s own Implementation Status for the full mechanism.

**A second, distinct gate category (Static Analysis) proved this mechanism generalizes via configuration alone, with one real tool-choice pivot along the way (added 2026-07-30, later the same day)** — see `../../06_capability_packs/software_engineering/agents.md`'s own "Currently Implemented Subset" for the full record.

**§9's own "every gate execution must record ... error details" requirement is now genuinely satisfied, closing the one remaining gap this thread had left open (added 2026-07-30, later still the same day).** A failed attempt used to leave **no** trace in `workflow_steps` at all — the raised exception meant `advance_workflow`, the only writer, was never reached, so only an eventual successful retry (or nothing, if the bound was exhausted) was ever persisted. `WorkflowInstanceService.advance` now wraps the executor call in its own `try`/`except`: on any exception, `WorkflowInstanceRepository.record_failed_attempt` writes a real `workflow_steps` row (`status="failed"`, real `error` detail, a real `attempt` number from the same `MAX(attempt)+1` query the successful path already uses) and a real `step.failed` event before the *original* exception is re-raised unchanged — every existing caller's retry/failure logic is completely unaffected; only a new, genuine side effect (the persisted row) is added. Proof: `tests/integration/workflow_engine/test_delivery_pipeline.py`'s own retry test now shows two real, distinct rows for the same gate — attempt 1, `status="failed"`, and attempt 2, `status="completed"`, `passed=True` — not just the one, eventually-successful row it used to see.

The [ADR-0006](../../18_decision_log/adr/ADR-0006-quality-gates-are-mandatory.md) invariant that blocking gates cannot be skipped is therefore **enforced for three real, in-pipeline gate categories (Static Analysis/`se.build_lint_clean`, Testing/`se.build_tests_pass`, and Code Review/`se.code_review_clean`, added `P03-S03-M30-T03` — corrected 2026-08-08, found during a full pre-completion health audit: this line was never updated the day the third gate landed — each with a bounded retry, and now a genuinely complete audit trail of every attempt, successful or not) — still an architectural commitment rather than a general mechanism everywhere else.** Framework-level policy: `../quality/quality_gates_framework.md`.

**§5's Observability Hook is real as of 2026-08-13 (`P02-S06-M15-T10`) — the last component of this package that had no code at all.** Verified by direct inspection before the work: the package was `__init__.py`, `errors.py` and `registry.py`, and searching it for `logger`/`metric`/`span` returned nothing, so §8's observability requirements had no producer whatsoever. `quality_gate_engine/observability.py` now emits a real `quality_gate.resolved`/`quality_gate.blocked` structured event, a real `aios.quality_gate.resolutions` counter (created once and cached, the contract `get_http_requests_counter` documents), and a real span around gate execution. **A blocked gate and a failing warning-severity gate are deliberately distinct outcomes** — ADR-0006 treats them differently, so collapsing both into "failed" would make the metric unable to answer the question an operator actually asks. **Telemetry only, never a second store** (gate results are already persisted durably to `evaluation.gate_results`), and every emission is guarded: a metric-backend outage must never be able to fail a gate that genuinely passed. **Gate duration is a real measurement too (`P02-S06-M15-T11`)** — see `evaluation_engine.md` for why it was structurally always `0` before.

Authoritative, always-current status: `../../19_roadmap/feature_inventory.md`. Build history: `../../19_roadmap/history/INDEX.md`.

## 1. Purpose

This document defines the detailed design of the **Quality Gate Engine**, a core component of the AI_OS Platform Kernel.

The Quality Gate Engine is responsible for executing Quality Gates at defined points in a workflow, evaluating their results, and enforcing the rule that blocking gates must pass before progression is allowed.

It implements the policies defined in the Quality Gates Framework.

This document is subordinate to:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Kernel Architecture  
5. Workflow Architecture  
6. Quality Gates Framework  

---

## 2. Design Goals

The Quality Gate Engine must:

- Execute gates reliably and consistently
- Support both Kernel-level and Capability-Pack-provided gates
- Produce clear, structured results
- Block progression on mandatory (blocking) failures
- Integrate tightly with the Workflow Engine
- Emit rich observability data
- Support re-evaluation after corrective actions
- Remain domain-agnostic at the Kernel level

---

## 3. Core Responsibilities

- Register available Quality Gates (from Kernel and from Capability Packs)
- Execute gates when requested by the Workflow Engine
- Evaluate success / failure according to the gate’s criteria
- Return structured results
- Enforce blocking behaviour
- Record all gate executions for audit and for the Evaluation Engine
- Support timeout and error handling for gate execution itself

---

## 4. High-Level Structure

```text
Quality Gate Engine
│
├── Gate Registry
├── Gate Executor
├── Result Evaluator
├── Policy Enforcer (blocking vs warning)
├── Result Store / Emitter
└── Observability Hook
```

---

## 5. Execution Flow

1. Workflow Engine reaches a Quality Gate point.
2. Workflow Engine requests execution of one or more gates.
3. Quality Gate Engine resolves the gate definitions.
4. Gates are executed (optionally in parallel when safe).
5. Results are collected and evaluated.
6. Structured result is returned to the Workflow Engine.
7. If any blocking gate failed, the Workflow Engine stops progression and follows the configured failure handling.

---

## 6. Gate Result Contract (Conceptual)

Every gate execution should return:

- gate_id
- status (pass / fail / warning / error)
- metrics / scores (optional)
- messages / details
- execution duration
- timestamp

---

## 7. Key Design Rules

- **This engine executes gates and returns results; it never decides workflow consequence.** The Workflow Engine's Gate Coordinator interprets a result and applies the consequence (proceed, retry, corrective loop, compensate, escalate). v1.0 of the Workflow Engine document listed its own "Quality Gate Executor", duplicating this component; that is resolved — execution here, consequence there ([ADR-0006](../../18_decision_log/adr/ADR-0006-quality-gates-are-mandatory.md)).
- **Gates execute inside a Tier 1 sandbox** when they run builds, tests, or analysis over generated code, which is most of them ([ADR-0016](../../18_decision_log/adr/ADR-0016-tool-execution-sandboxing.md)).
- **An LLM-as-judge gate may only be `warning` severity**, never the sole blocking gate for a stage: it is non-deterministic and provider-dependent, and using one as a blocking gate would contaminate cross-model comparison with the judge model's own behaviour.
- Gates contributed by Capability Packs must comply with the Quality Gates Framework and be properly declared.
- Gate execution should be idempotent where practical.
- Results must be durable and available to the Evaluation Engine and Dashboard.

---

## 8. Relationship with Other Components

- **Workflow Engine** is the primary caller.
- **Quality Gates Framework** defines the rules and categories of gates.
- **Capability Packs** may contribute domain-specific gates.
- **Evaluation Engine** consumes gate results for scoring and multi-LLM comparison.
- **Observability** components record every gate execution.
- **Dashboard** surfaces gate results to users.

---

## 9. Observability Requirements

Every gate execution must record:

- Workflow ID / Trace ID / Step ID
- Gate ID and version
- Result
- Duration
- Details of failure (when applicable)

---

## 10. Current Status

This document defines the design baseline for the Quality Gate Engine.

Detailed gate registration mechanisms, execution isolation, and result schemas will be refined during implementation.

---

## 11. Final Authority

Order of precedence:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Kernel Architecture  
5. Quality Gates Framework  
6. Quality Gate Engine Design  
7. Source Code
