# ADR-0021: Declarative Workflows; Planning Is an Agent, Not a Kernel Component

**Status:** Accepted
**Date:** 2026-07-25
**Decision Makers:** Chief Architect
**Related Documents:** `docs/03_architecture/workflow/workflow_architecture.md`, `docs/03_architecture/kernel/workflow_engine.md`

---

## Context

The documentation contained an unresolved contradiction. The Workflow Architecture's lifecycle included "Task Decomposition" and "Agent Assignment", and the System Architecture listed a "Task Planner" and "Agent Orchestrator" as orchestration components — implying runtime planning. Meanwhile workflows and their participating agents are statically declared in the pack manifest, and the Workflow Engine design has no planner. An implementer could not tell whether execution follows a declared graph or is planned at runtime.

This matters beyond tidiness: dynamic planning would undermine replay, reproducible experiments, and static validation of agent and tool references.

## Decision

**Workflows are declarative. There is no Task Planner or Agent Orchestrator Kernel component; both are removed from the architecture.**

1. A workflow definition is a **statically declared, validated graph** of typed steps: `agent`, `tool`, `decision`, `parallel`, `foreach`, `sub_workflow`, `quality_gate`, `human_approval`, `compensate`. It is validated at pack load time — every agent, tool, and gate reference must resolve, or the pack does not activate.
2. **Dynamic decomposition is achieved without dynamic control flow.** Where a plan must be derived at runtime (for example "implement each module of this specification"), the `technical-planner` agent produces a **plan artifact** conforming to a declared schema. A `foreach` step consumes that artifact and executes a declared sub-workflow per item. The *content* of the work is dynamic; the *shape* of the control flow remains declared and validated.
3. Iteration is always bounded: `foreach` declares a maximum fan-out, and review–revise loops declare maximum iterations plus a token/cost ceiling. There is no unbounded agent-driven loop.
4. Agent selection is by declared `agent_ref` in the step, not chosen at runtime by a model.

## Alternatives Considered

- **A runtime Task Planner that composes steps from an agent capability registry** — The more "autonomous" design and genuinely appealing. Rejected because it makes each run's control flow unique, which defeats replay, makes experiment comparison unfair (two models would execute different graphs), prevents static validation of references, and makes cost unpredictable. The `foreach`-over-plan-artifact pattern delivers the practical benefit while keeping these properties.
- **An LLM chooses the next step at each point (ReAct-style)** — Rejected for the same reasons, more acutely: no bounded cost, no reproducibility, and no way to guarantee a Quality Gate is reached.
- **Fully static graphs with no dynamic fan-out** — Rejected as too rigid: the product must handle "build N modules" where N is unknown until requirements are analysed.

## Consequences

### Positive
- Every run has a known, validatable shape; replay and fair comparison hold.
- Broken agent/tool references fail at pack activation, not mid-run.
- Cost and duration are boundable before execution.
- Two Kernel components are removed rather than specified — a net simplification.

### Negative
- Genuinely novel task shapes require a new declared workflow rather than emergent planning.
- The plan-artifact schema becomes a contract that must be versioned.

### Neutral
- Should evidence later show declarative workflows to be materially limiting, revisiting this requires a new ADR and an explicit plan for preserving replay and comparability.

## Compliance

Resolves the contradiction between `workflow_architecture.md` (task decomposition, agent assignment) and `workflow_engine.md` (no planner component). Preserves [ADR-0005](ADR-0005-agents-never-communicate-directly.md) and [ADR-0022](ADR-0022-reproducibility-over-determinism.md).

## References

- `docs/03_architecture/workflow/workflow_patterns.md`
- `docs/05_agents/agent_specifications.md`

---

## Implementation Status (appended 2026-07-28 — not part of the Accepted decision)

**Status in code:** Partially implemented

The decision is honoured in the sense that matters most: workflow definitions are static, declared YAML validated at load time, `agent_ref` is always declared, and no Task Planner or Agent Orchestrator component exists anywhere — nothing in the codebase can choose a next step at runtime. Of the nine decided step types only `agent` and `tool` actually execute; `decision`, `parallel`, `foreach`, `sub_workflow`, `quality_gate`, and `compensate` are declared in the enum without executors, and `human_approval` completes as a NoOp — so the plan-artifact-plus-`foreach` pattern for dynamic decomposition is not yet available.

Live status: [`feature_inventory.md`](../../19_roadmap/feature_inventory.md) · Build history: [`history/INDEX.md`](../../19_roadmap/history/INDEX.md)
