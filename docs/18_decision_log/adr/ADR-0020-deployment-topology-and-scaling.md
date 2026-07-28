# ADR-0020: Deployment Topology and Scaling Path

**Status:** Accepted
**Date:** 2026-07-25
**Decision Makers:** Chief Architect, Project Owner
**Related Documents:** `docs/11_deployment/deployment_architecture.md`, `docs/02_requirements/non_functional/nfr.md`

---

## Context

The System Architecture describes a modular monolith while the Kernel Architecture claims horizontal scaling, with no design connecting the two. Without a stated topology and scaling path, the concurrency model, the event transport, and the state design cannot be validated against each other, and "horizontal scaling" remains an unsupported assertion.

## Decision

**A modular monolith deployed as two process roles that scale horizontally over shared PostgreSQL and Redis.**

| Role | Contains | Scaling |
|---|---|---|
| **API process** | FastAPI app, WebSocket endpoint, read queries, workflow submission | Horizontal, stateless. N replicas behind a load balancer with sticky routing for WebSocket. |
| **Worker process** | Workflow Engine execution loop, agent invocation, tool invocation, quality gates | Horizontal. N replicas that lease work via `SELECT … FOR UPDATE SKIP LOCKED`. |

Both roles run the **same Kernel image** with the same composition root, differing only in which entry point they start. This is the property that makes the monolith scale without becoming a distributed system: there is one codebase, one dependency graph, one deployment artifact.

**How horizontal scaling actually works** — the mechanism the previous documents asserted without describing:
1. Workflow state lives in PostgreSQL, not in worker memory ([ADR-0011](ADR-0011-persistence-and-workflow-state.md)), so any worker can pick up any workflow.
2. Workers lease workflow steps with `SKIP LOCKED`; leases expire, so a crashed worker's work is reclaimed rather than lost.
3. Steps are idempotent and keyed, so a reclaimed step re-executes safely.
4. Cross-process events go through the outbox and, past the trigger in [ADR-0012](ADR-0012-event-bus.md), Redis Streams.
5. Sandboxed execution is per-step and stateless, so it follows the worker.

**Environments:** Docker Compose for local development and single-node deployment (Kernel, Postgres, Redis, OTel Collector, Grafana stack). Kubernetes with a Helm chart for multi-node production, using `Deployment` for both roles, `HorizontalPodAutoscaler` on worker queue depth, and readiness/liveness probes wired to the Health & Lifecycle endpoints.

**Sandboxing in Kubernetes:** worker pods require access to a container runtime for Tier 1 execution. The Docker socket is never mounted. The supported patterns are a rootless Podman sidecar or a dedicated sandbox node pool with gVisor; the Deployment Architecture document specifies the exact configuration.

**When to split into services.** Recorded explicitly so the decision is evidence-driven rather than fashion-driven. Extract a component only when at least one holds:
- it needs a resource profile the shared process cannot satisfy (for example GPU-bound local inference);
- it must scale on an axis genuinely independent of API and worker load;
- two Capability Packs require irreconcilable dependency versions ([ADR-0009](ADR-0009-packaging-and-dependency-management.md));
- a compliance boundary requires process or network isolation.

Absent one of these, extraction adds network failure modes, deployment complexity, and distributed-tracing burden for no benefit.

## Alternatives Considered

- **Single process, vertical scaling only** — Simplest; rejected because it caps throughput and provides no availability during deploys or restarts.
- **Microservices per Kernel component** — Rejected: turns every in-process call into a network call with partial-failure semantics, at a scale where a single process is not the bottleneck. The Capability Pack contract already provides the modularity benefit without the distribution cost.
- **Serverless functions per step** — Rejected: cold starts, execution time limits incompatible with long agent steps, and no natural home for a container-based sandbox.
- **Celery / RQ as the work distribution mechanism** — Rejected: adds a broker and a second state model alongside the workflow event log; `SKIP LOCKED` leasing keeps state ownership in one place.

## Consequences

### Positive
- Horizontal scaling is real and mechanically described, with no broker required initially.
- One image and one composition root for both roles keeps operational and cognitive surface small.
- Extraction criteria are written down, so future splits require evidence.

### Negative
- Shared PostgreSQL is the scaling ceiling and a single point of failure; addressed by managed Postgres with replicas, connection pooling, and PITR.
- All packs share one process, so a pathological pack can affect others; bounded by per-step timeouts, resource limits, and health monitoring.
- Kubernetes sandbox execution needs deliberate node configuration.

### Neutral
- Long-running steps are the norm; probes and graceful-shutdown drain periods are sized accordingly (see the NFR document).

## Compliance

Resolves the contradiction between `system_architecture.md` (modular monolith) and `kernel_architecture.md` (horizontal scaling) by specifying the mechanism that makes both true.

## References

- `docs/11_deployment/deployment_architecture.md`
- `docs/12_operations/operations_runbook.md`

---

## Implementation Status (appended 2026-07-28 — not part of the Accepted decision)

**Status in code:** Partially implemented

The two-process-role split is real in code: `ai_os_kernel.entrypoints.api` and `ai_os_kernel.entrypoints.worker` start from the same composition root, and the `SKIP LOCKED` leasing that makes worker scaling possible works (ADR-0011). Everything operational is missing: there is **no Dockerfile anywhere**, so no image exists; `infra/docker/`, `infra/kubernetes/`, and `infra/terraform/` are empty; `infra/docker-compose.yml` brings up only Postgres and Redis, not the Kernel; and no multi-instance worker loop exists — `run_to_completion`/`reap_once` handle one instance or one bounded pass, with nothing scheduling either across many instances.

Live status: [`feature_inventory.md`](../../19_roadmap/feature_inventory.md) · Build history: [`history/INDEX.md`](../../19_roadmap/history/INDEX.md)
