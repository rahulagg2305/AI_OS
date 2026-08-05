# Quality Gate Engine Design – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Quality Gate Engine Design  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## Implementation Status (2026-07-31; Gate Registry added 2026-08-05)

**The Gate Registry is now real (`P02-S06-M15-T05`) — the first real code this package has ever had.** `ai_os_kernel.quality_gate_engine.registry.InMemoryGateRegistry` resolves a declared `gateId` to a real `GateDefinition`, derived (`derive_gate_definitions`) from a pack manifest's own real, already-schema-validated `qualityGates[]` array (`platform_sdk/schemas/manifest.schema.json`'s own complete Gate Contract shape — `id`/`name`/`version`/`description`/`entrypoint`/`type`/`severity`/`successCriteria`/`timeoutSeconds`) — no new `catalog.quality_gates` table (a real, undecided schema-authority fork this ticket's own scope did not need to open). Gate ids are resolved raw, never derived with a `pack_id/` prefix the way agent/tool ids are — confirmed via direct inspection of the one real reference that exists today (`delivery_pipeline.yaml`'s own top-level `qualityGates: [se.build_lint_clean, se.build_tests_pass]`, already in this un-prefixed, dot-namespaced shape). A real collision across two packs' own declared ids is refused (`DuplicateGateIdError`), not silently resolved by picking a winner. Kernel-owned gates are a disclosed, deliberate scope reduction: §10 documents that ownership category, but no concrete Kernel-level gate exists anywhere with real content to resolve. Proven with real, schema-conformant test fixtures (independently validated against the real JSON Schema via `jsonschema.validate()`), not fabricated data — the identical "build the real component before anything wires it in" precedent already established for `KnowledgeResolver`/`MemoryResolver` before their own later production-wiring tickets (`P02-S03-M08-T05`/`T06`, wired `T12`/`T13`). Wiring this registry against the real Software Engineering pack's own manifest is `P02-S06-M15-T06`'s own, separate Goal, not yet done.

**Everything else in this package remains unbuilt** — no Gate Executor, no Result Evaluator, no Policy Enforcer, no pack-declared gate definitions in the one real pack's own manifest yet. That full design (§4 above) remains mostly unbuilt.

**§9's own `evaluation.gate_results` writer now exists — the Evaluation Engine's first real consumer (added 2026-07-31)**, built in the Workflow Engine (`ai_os_kernel.workflow_engine.gate_result_recorder.SqlGateResultRecorder`), not this package, the identical "the functional gap is closed elsewhere" shape already established for the executor itself below. `WorkflowInstanceService._maybe_record_gate_result` reads back a resolved `quality_gate` step's own real, just-persisted `workflow_steps` row (after `record_failed_attempt`/`advance_workflow` — not before, since only they compute the real `attempt` number) and hands it to the injected recorder, for both real gate categories (Testing, Static Analysis), pass or fail. See `evaluation_engine.md`'s own Implementation Status and `gate_result_recorder.py`'s own module docstring for the full placement reasoning and column mapping (including the one honest, currently-always-zero limitation: `duration_ms`, since the underlying `started_at`/`completed_at` timestamps are stamped identically at write time).

**But the `quality_gate` workflow step type is no longer a no-op, for one real, narrow, deliberately-scoped case.** `ai_os_kernel.workflow_engine.quality_gate.QualityGateStepExecutor` (2026-07-30) reads a configured source step's own real, persisted output and raises `QualityGateFailedError` — genuinely halting `WorkflowAdvanceRunner.run_to_completion` (`WorkflowRunOutcome.FAILED`) — unless that output's `passed` field is literally `True`. `se.delivery_pipeline` (the Software Engineering pack's own workflow) is its first real caller: a new `quality-gate-tests-pass` step now sits between `test` and `documentation`, so a genuinely failing test run halts the pipeline before Documentation ever runs. This is this step's own approved framing, verbatim: "formalizing that pass/fail into a real, declared quality_gate-type workflow step that actually blocks progression on failure, rather than a brand new gate concept" — not a substitute for the full engine above, which remains the eventual, larger destination (the Gate Registry is real now, `P02-S06-M15-T05` — see above; still needed: pack-declared gate ids actually resolving through it, a real Gate Executor, parallel gate execution). Proof: `tests/integration/workflow_engine/test_delivery_pipeline.py`'s own new test, a genuinely failing build (`sys.exit(1)`) halting the pipeline with Documentation never invoked.

**A real, bounded retry now sits on top of that halt (added 2026-07-30, same day).** A failed gate no longer halts on its very first failure when its own workflow declares a `retryPolicy` and the caller has configured a retry target for it: `WorkflowAdvanceRunner.run_to_completion` retries from a named earlier step (`se.delivery_pipeline` retries from `build`, not the whole pipeline — Requirements Analyst's/Architecture's own design decisions are unrelated to why a build/test cycle failed), bounded by both `max_attempts` and `max_duration_seconds`. This answers §7's own "support re-evaluation after corrective actions" for exactly this one case — see `../../19_roadmap/history/` and `workflow_engine.md`'s own Implementation Status for the full mechanism.

**A second, distinct gate category (Static Analysis) proved this mechanism generalizes via configuration alone, with one real tool-choice pivot along the way (added 2026-07-30, later the same day)** — see `../../06_capability_packs/software_engineering/agents.md`'s own "Currently Implemented Subset" for the full record.

**§9's own "every gate execution must record ... error details" requirement is now genuinely satisfied, closing the one remaining gap this thread had left open (added 2026-07-30, later still the same day).** A failed attempt used to leave **no** trace in `workflow_steps` at all — the raised exception meant `advance_workflow`, the only writer, was never reached, so only an eventual successful retry (or nothing, if the bound was exhausted) was ever persisted. `WorkflowInstanceService.advance` now wraps the executor call in its own `try`/`except`: on any exception, `WorkflowInstanceRepository.record_failed_attempt` writes a real `workflow_steps` row (`status="failed"`, real `error` detail, a real `attempt` number from the same `MAX(attempt)+1` query the successful path already uses) and a real `step.failed` event before the *original* exception is re-raised unchanged — every existing caller's retry/failure logic is completely unaffected; only a new, genuine side effect (the persisted row) is added. Proof: `tests/integration/workflow_engine/test_delivery_pipeline.py`'s own retry test now shows two real, distinct rows for the same gate — attempt 1, `status="failed"`, and attempt 2, `status="completed"`, `passed=True` — not just the one, eventually-successful row it used to see.

The [ADR-0006](../../18_decision_log/adr/ADR-0006-quality-gates-are-mandatory.md) invariant that blocking gates cannot be skipped is therefore **enforced for two real, in-pipeline gate categories (each with a bounded retry, and now a genuinely complete audit trail of every attempt, successful or not) — still an architectural commitment rather than a general mechanism everywhere else.** Framework-level policy: `../quality/quality_gates_framework.md`.

Authoritative, always-current status: `../../19_roadmap/feature_inventory.md` and `../../19_roadmap/implementation_status.md`. Build history: `../../19_roadmap/history/INDEX.md`.

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
