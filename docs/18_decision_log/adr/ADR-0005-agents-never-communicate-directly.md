# ADR-0005: Agents Never Communicate Directly; the Workflow Engine Orchestrates

**Status:** Accepted
**Date:** 2026-07-25
**Decision Makers:** Chief Architect, Project Owner
**Related Documents:** `docs/03_architecture/agents/agent_communication.md`, `docs/03_architecture/workflow/workflow_architecture.md`, `docs/03_architecture/workflow/state_management.md`

---

## Context

Multi-agent systems commonly fail by becoming unobservable: agents call each other, share mutable state, retry each other, and the resulting behaviour cannot be explained, reproduced, or compared. AI_OS must produce runs that are auditable, resumable, and comparable across models, which is impossible if control flow is emergent.

## Decision

Agents never communicate with each other. All sequencing, data passing, retry, escalation, and decision-making between agents is performed by the **Workflow Engine**, which is the sole owner of workflow state.

An agent may only:
1. receive a structured work item plus context assembled by the Context Manager,
2. return a structured result,
3. invoke approved Tools (the only route to side effects),
4. call the LLM Gateway,
5. publish events it has been explicitly permitted to publish.

Data that must travel from one agent to another travels through durable Workflow State. Large artifacts are passed by content-addressed reference rather than by value.

## Alternatives Considered

- **Direct agent-to-agent messaging (actor model / agent mesh)** — More flexible and superficially more "agentic"; rejected because it makes state ownership ambiguous, defeats replay, and makes cost attribution and fair multi-LLM comparison impossible.
- **Blackboard / shared mutable memory** — Rejected: concurrent writers with no arbiter produce non-deterministic, unexplainable runs.
- **Hierarchical agents where a lead agent calls sub-agents directly** — Rejected as an architectural default. The same pattern is available as a *workflow* (fan-out/fan-in, sub-workflow steps) with the Engine retaining state ownership.

## Consequences

### Positive
- Every interaction is recorded, replayable, and attributable.
- Failure handling and retry policy live in one place instead of being reinvented per agent.
- Runs are comparable across models, which is what makes the benchmarking goal achievable.

### Negative
- Coordination patterns must be expressed as workflow definitions, which is more verbose than an agent simply calling another.
- The Workflow Engine is a central component and a potential bottleneck; addressed by the concurrency model in [ADR-0020](ADR-0020-deployment-topology-and-scaling.md).

### Neutral
- Dynamic decomposition is supported through a planning *agent* that emits a plan artifact consumed by a `foreach` or sub-workflow step, not through agents spawning agents. See [ADR-0021](ADR-0021-declarative-workflows-no-dynamic-task-planner.md).

## Compliance

Complies with the AI Governance Framework (Separation of Responsibilities) and the Agent Architecture & Agent Contract.

## References

- `docs/03_architecture/workflow/workflow_patterns.md`

---

## Implementation Status (appended 2026-07-28 — not part of the Accepted decision)

**Status in code:** Fully implemented

Honoured for everything built so far: the four chained agents of `se.delivery_pipeline` never reference one another, and each step's output reaches the next step's input only through durable workflow state, read back by the Context Manager's `WorkflowStepOutputResolver`. No agent-invocation capability exists on `PackContext`, so the prohibition is structural rather than advisory; content-addressed passing of large artifacts is not needed yet and is not built.

Live status: [`feature_inventory.md`](../../19_roadmap/feature_inventory.md) · Build history: [`history/INDEX.md`](../../19_roadmap/history/INDEX.md)
