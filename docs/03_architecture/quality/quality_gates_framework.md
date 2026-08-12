# Quality Gates Framework – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Quality Gates Framework  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## Implementation Status (2026-07-30)

**No full Quality Gate Engine exists** — `kernel/src/ai_os_kernel/quality_gate_engine/` is still a docstring-only `__init__.py`; no Gate Registry, no `evaluation.gate_results` writer, no pack-declared gate definitions. This document's full Gate Contract (§4) and Standard Categories (§5) remain design specification, not built infrastructure.

**One real, narrow exception, added 2026-07-30**: the `quality_gate` workflow step type is no longer unconditionally a no-op. `ai_os_kernel.workflow_engine.quality_gate.QualityGateStepExecutor` genuinely blocks progression when a configured source step's own real, persisted output does not report success — wired into `se.delivery_pipeline` as a real `quality-gate-tests-pass` step gating Documentation on the Test Agent's own real `passed` field. This is the Testing category (§5.3) alone, for one pipeline, evaluated by one fixed field-name convention — not the general Gate Contract (id/severity/evaluationMethod/successCriteria per §4), which still needs a real Gate Registry. See `../kernel/quality_gate_engine.md`'s own Implementation Status for the full detail.

Consequence a reader must not miss: the "blocking gates cannot be skipped" invariant stated in `PROJECT_INDEX.md` and [ADR-0006](../../18_decision_log/adr/ADR-0006-quality-gates-are-mandatory.md) is now **enforced for exactly this one real case, still an architectural commitment rather than a general mechanism everywhere else.** Building the full engine remains an outstanding Stage B deliverable.

Authoritative, always-current status: the per-module completion table in `feature_inventory.md`; build history in `history/INDEX.md` (all under `docs/19_roadmap/`).

## 1. Purpose

This document defines the official Quality Gates Framework for AI_OS.

Quality Gates are mandatory checkpoints that must pass before a workflow is allowed to progress to the next stage. They enforce engineering standards, prevent low-quality outputs from advancing, and support measurable multi-LLM comparison.

This document is subordinate to:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Capability Pack Contract  
5. Kernel Architecture  
6. Agent Architecture & Agent Contract  
7. Workflow Architecture  

---

## 2. Design Goals

Quality Gates must be:

- Objective and measurable
- Deterministic where practical
- Configurable
- Observable
- Enforceable by the Workflow Engine
- Applicable across different Capability Packs
- Supportive of multi-LLM benchmarking

---

## 3. Core Principles

- No workflow may skip a mandatory Quality Gate.
- Failed gates block progression.
- Gates must produce clear, structured results.
- Corrective actions may be taken, after which gates can be re-evaluated.
- Quality is preferred over speed.

---

## 4. Quality Gate Contract

Every Quality Gate must define:

| Field             | Description                                      | Required |
|-------------------|--------------------------------------------------|----------|
| id                | Globally unique identifier                       | Yes      |
| name              | Human-readable name                              | Yes      |
| description       | What the gate validates                          | Yes      |
| type              | automated / semi-automated / manual              | Yes      |
| severity          | blocking / warning                               | Yes      |
| evaluationMethod  | How the gate is evaluated                        | Yes      |
| successCriteria   | Clear pass condition                             | Yes      |
| failureAction     | What happens on failure                          | Yes      |
| timeout           | Maximum evaluation time                          | No       |
| owner             | Owning Capability Pack or Kernel component       | Yes      |

---

## 5. Standard Quality Gate Categories

### 5.1 Build & Compilation
- Build succeeds
- No compilation errors
- Dependency resolution succeeds

### 5.2 Static Analysis
- Linting passes
- Type checking passes
- Code complexity within thresholds
- No critical static analysis findings

### 5.3 Testing
- Unit tests pass
- Integration tests pass
- Minimum code coverage threshold met
- No critical test failures

### 5.4 Security
- No critical or high vulnerabilities
- Secrets detection passes
- Dependency vulnerability scan passes
- Secure coding checks pass

### 5.5 Architecture & Design
- Architecture compliance
- Dependency direction rules respected
- Naming and structure conventions followed
- No forbidden patterns

### 5.6 Documentation
- Required documentation exists
- Public APIs are documented
- Decision records updated (where applicable)

### 5.7 Performance (where applicable)
- Performance thresholds met
- No major regressions

### 5.8 Release Readiness
- Versioning correct
- Changelog updated
- Deployment configuration valid

---

## 6. Gate Severity

- **Blocking**: Workflow cannot proceed until the gate passes.
- **Warning**: Workflow may proceed, but the issue is recorded and visible on the Dashboard.

---

## 7. Integration with Workflow Engine

- The Workflow Engine is responsible for executing Quality Gates at defined points.
- Gates may run before, during, or after Agent execution.
- Gate results are stored as part of the workflow execution record.
- Failed blocking gates trigger the configured failure handling (retry, compensation, or human escalation).

---

## 8. Multi-LLM Benchmarking Support

Quality Gate results form a key part of the Evaluation and Benchmarking system.

For every experiment / LLM run the platform shall record:

- Which gates passed / failed
- Scores or metrics produced by gates
- Number of retries caused by gate failures
- Final quality score derived from gate outcomes

This enables objective comparison between different LLMs on the same project.

---

## 9. Observability Requirements

Every Quality Gate evaluation must emit:

- Gate ID
- Workflow ID / Trace ID
- Result (pass / fail / warning)
- Metrics / scores
- Execution duration
- Error details (if any)

---

## 10. Ownership

- Core / platform-level gates are owned by the Kernel (Quality Gate Engine).
- Domain-specific gates are owned by Capability Packs and declared in their manifests.

---

## 11. Current Status

This document establishes the baseline Quality Gates Framework.

Detailed gate definitions for the Software Engineering Pack and concrete implementation of the Quality Gate Engine will be defined in later documents.

---

## 12. Final Authority

Order of precedence:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Capability Pack Contract  
5. Kernel Architecture  
6. Agent Architecture & Agent Contract  
7. Workflow Architecture  
8. Quality Gates Framework  
9. Source Code
