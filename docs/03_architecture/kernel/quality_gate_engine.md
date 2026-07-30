# Quality Gate Engine Design – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Quality Gate Engine Design  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## Implementation Status (2026-07-30)

**The `kernel/src/ai_os_kernel/quality_gate_engine/` package itself is still a docstring-only `__init__.py`** — no Gate Registry, no Gate Executor, no Result Evaluator, no Policy Enforcer, no `evaluation.gate_results` writer, no pack-declared gate definitions. That full design (§4 above) remains unbuilt.

**But the `quality_gate` workflow step type is no longer a no-op, for one real, narrow, deliberately-scoped case.** `ai_os_kernel.workflow_engine.quality_gate.QualityGateStepExecutor` (2026-07-30) reads a configured source step's own real, persisted output and raises `QualityGateFailedError` — genuinely halting `WorkflowAdvanceRunner.run_to_completion` (`WorkflowRunOutcome.FAILED`) — unless that output's `passed` field is literally `True`. `se.delivery_pipeline` (the Software Engineering pack's own workflow) is its first real caller: a new `quality-gate-tests-pass` step now sits between `test` and `documentation`, so a genuinely failing test run halts the pipeline before Documentation ever runs. This is this step's own approved framing, verbatim: "formalizing that pass/fail into a real, declared quality_gate-type workflow step that actually blocks progression on failure, rather than a brand new gate concept" — not a substitute for the full engine above, which remains the eventual, larger destination (Gate Registry, pack-declared gate ids resolving to real `evaluationMethod`/`successCriteria`, an `evaluation.gate_results` writer, parallel gate execution). Proof: `tests/integration/workflow_engine/test_delivery_pipeline.py`'s own new test, a genuinely failing build (`sys.exit(1)`) halting the pipeline with Documentation never invoked.

**A real, bounded retry now sits on top of that halt (added 2026-07-30, same day).** A failed gate no longer halts on its very first failure when its own workflow declares a `retryPolicy` and the caller has configured a retry target for it: `WorkflowAdvanceRunner.run_to_completion` retries from a named earlier step (`se.delivery_pipeline` retries from `build`, not the whole pipeline — Requirements Analyst's/Architecture's own design decisions are unrelated to why a build/test cycle failed), bounded by both `max_attempts` and `max_duration_seconds`. This answers §7's own "support re-evaluation after corrective actions" for exactly this one case — see `../../19_roadmap/history/` and `workflow_engine.md`'s own Implementation Status for the full mechanism.

The [ADR-0006](../../18_decision_log/adr/ADR-0006-quality-gates-are-mandatory.md) invariant that blocking gates cannot be skipped is therefore **enforced for exactly one, real, in-pipeline case (now with a bounded retry before it gives up) — still an architectural commitment rather than a general mechanism everywhere else.** Framework-level policy: `../quality/quality_gates_framework.md`.

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
