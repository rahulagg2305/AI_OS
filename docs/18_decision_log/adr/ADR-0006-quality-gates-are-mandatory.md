# ADR-0006: Quality Gates Are Mandatory and Machine-Evaluated

**Status:** Accepted
**Date:** 2026-07-25
**Decision Makers:** Chief Architect, Project Owner
**Related Documents:** `docs/03_architecture/quality/quality_gates_framework.md`, `docs/03_architecture/kernel/quality_gate_engine.md`

---

## Context

AI-generated output varies in quality run to run. Reviewing it by human judgement alone does not scale and produces no comparable signal. AI_OS needs a mechanism that both blocks bad output from advancing and produces the objective measurements that multi-LLM comparison depends on.

## Decision

Quality Gates are mandatory checkpoints declared in workflow definitions and executed by the **Quality Gate Engine**. Every gate is machine-evaluated against an explicit success criterion and returns a structured result (`pass` / `fail` / `warning` / `error`) with metrics.

Gates are `blocking` or `warning`. A failed blocking gate stops workflow progression; the Workflow Engine — not the Quality Gate Engine — decides the consequence (retry, corrective loop, compensate, or escalate to a human).

No workflow, agent, or Capability Pack may skip, disable, or self-certify a blocking gate at runtime. Changing a gate's severity or threshold is a configuration change subject to audit, not a runtime decision.

## Alternatives Considered

- **Advisory quality checks** — Rejected: advisory checks are ignored under delivery pressure, and the platform's central quality claim would be unenforced.
- **Human review as the primary gate** — Rejected as the primary mechanism: it does not scale to autonomous runs and yields subjective, non-comparable results. Human approval remains for governance decisions ([ADR-0007](ADR-0007-human-governance-for-critical-decisions.md)).
- **LLM-as-judge as the primary gate** — Rejected as the *primary* mechanism because it is non-deterministic and provider-dependent, which would contaminate cross-model comparison. Permitted only as a `warning`-severity supplementary gate, never as the sole blocking gate for a stage.

## Consequences

### Positive
- Low-quality output cannot advance silently.
- Gate results form the objective backbone of evaluation and benchmarking.

### Negative
- Requires real tooling (build, test, coverage, lint, type-check, security scan) before Stage C can complete.
- Poorly calibrated thresholds can block legitimate work; mitigated by making thresholds configuration and reviewing them against the NFR document.

### Neutral
- Gates run inside the sandbox defined in [ADR-0016](ADR-0016-tool-execution-sandboxing.md), since most of them execute untrusted generated code.

## Compliance

Complies with the Project Constitution (Quality Gates are Mandatory) and the AI Governance Framework (Quality Governance).

## References

- `docs/06_capability_packs/software_engineering/tools_quality_gates.md`
- `docs/10_testing/test_strategy.md`

---

## Implementation Status (appended 2026-07-28 — not part of the Accepted decision)

**Status in code:** Not yet implemented

Nothing enforces any quality gate anywhere in the code today: `ai_os_kernel.quality_gate_engine` is a docstring-only stub, and while `quality_gate` exists as a declared workflow step type and `quality_gate_failed` as a workflow state, no gate is ever declared, evaluated, or acted on. The Software Engineering pack declares no quality gates in its manifest.

Live status: [`feature_inventory.md`](../../19_roadmap/feature_inventory.md) · Build history: [`history/INDEX.md`](../../19_roadmap/history/INDEX.md)
