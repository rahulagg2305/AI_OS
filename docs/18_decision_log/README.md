# Decision Log — AI_OS

**Document:** Architecture Decision Record Index
**Status:** Active
**Last Updated:** 2026-07-28 (added the *In code* column and the implementation-status summary; every ADR now carries an appended, clearly-delimited implementation-status note)

---

## Purpose

This is the central index of every Architecture Decision Record for AI_OS. Only **Accepted** ADRs are active. An ADR is never edited to reverse a decision — it is superseded by a new ADR that references it.

Process and template: `adr/adr_process_and_templates.md`.

**Decided ≠ built.** Every ADR below is Accepted, which records the decision, not its delivery. Each ADR file now ends with an appended *Implementation Status* note (dated 2026-07-28, explicitly outside the Accepted decision) stating what exists in code and what does not. The `In code` column here summarises those notes; the authoritative live views are [`feature_inventory.md`](../19_roadmap/feature_inventory.md) (the authority on per-module completeness).

---

## Index

`In code`: **Full** = the decision is honoured for everything built · **Partial** = the seam or mechanism exists but material parts of the decision are unbuilt · **None** = nothing of this decision exists in code yet.

| ADR | Title | Status | Date | In code | Summary |
|-----|-------|--------|------|---------|---------|
| [0001](adr/ADR-0001-modular-capability-pack-architecture.md) | Modular Capability Pack Architecture | Accepted | 2026-07-25 | Partial | Domain-agnostic Kernel; all domain logic in installable, manifest-declared packs. |
| [0002](adr/ADR-0002-llm-gateway-single-entry-point.md) | LLM Gateway as Single Entry Point | Accepted | 2026-07-25 | Partial | All model calls including embeddings pass through the Gateway; model selection by alias. |
| [0003](adr/ADR-0003-documentation-first-development.md) | Documentation-First Development | Accepted | 2026-07-25 | Full | Contracts documented before implementation; prototypes exempt until promoted. |
| [0004](adr/ADR-0004-interface-driven-and-configuration-over-code.md) | Interface-Driven + Configuration over Code | Accepted | 2026-07-25 | Partial | Protocols at real seams; behaviour from configuration, not literals. |
| [0005](adr/ADR-0005-agents-never-communicate-directly.md) | Agents Never Communicate Directly | Accepted | 2026-07-25 | Full | Workflow Engine owns all coordination and state; agents are isolated units. |
| [0006](adr/ADR-0006-quality-gates-are-mandatory.md) | Quality Gates Are Mandatory | Accepted | 2026-07-25 | None | Machine-evaluated blocking gates; LLM-as-judge may only warn. |
| [0007](adr/ADR-0007-human-governance-for-critical-decisions.md) | Human Governance for Critical Decisions | Accepted | 2026-07-25 | None | Defined approval set; timeout never implies approval; approvals are attributable. |
| [0008](adr/ADR-0008-primary-language-and-runtime.md) | Primary Language and Runtime | Accepted | 2026-07-25 | Partial | **Python 3.12**, asyncio, `mypy --strict`, Pydantic v2, Protocol interfaces. |
| [0009](adr/ADR-0009-packaging-and-dependency-management.md) | Packaging and Dependency Management | Accepted | 2026-07-25 | Partial | **uv workspace**, per-pack distributions, entry-point + filesystem discovery. |
| [0010](adr/ADR-0010-composition-and-dependency-injection.md) | Composition and Dependency Injection | Accepted | 2026-07-25 | Partial | Explicit composition root, constructor injection, **no DI container**. |
| [0011](adr/ADR-0011-persistence-and-workflow-state.md) | Persistence and Workflow State | Accepted | 2026-07-25 | Full | **PostgreSQL 16**, append-only event log + materialised snapshot, `SKIP LOCKED` leasing. |
| [0012](adr/ADR-0012-event-bus.md) | Event Bus | Accepted | 2026-07-25 | None | In-process asyncio bus + transactional outbox; Redis Streams at a stated trigger. |
| [0013](adr/ADR-0013-search-and-vector-store.md) | Search and Vector Store | Accepted | 2026-07-25 | Partial | **Postgres + pgvector**, hybrid RRF ranking, embeddings via the Gateway. |
| [0014](adr/ADR-0014-api-style-and-realtime-transport.md) | API Style and Real-Time Transport | Accepted | 2026-07-25 | Partial | **FastAPI** REST `/api/v1` + WebSocket; OpenAPI 3.1; RFC 9457 errors; MCP deferred. |
| [0015](adr/ADR-0015-testing-and-ci.md) | Testing Strategy and CI Toolchain | Accepted | 2026-07-25 | Partial | pytest, testcontainers, ruff, mypy, GitHub Actions; SDK-provided pack contract suite. |
| [0016](adr/ADR-0016-tool-execution-sandboxing.md) | Tool Execution Sandboxing | Accepted | 2026-07-25 | Partial (Tier 1 full) | Two trust tiers; ephemeral containers, no network by default; authority never from LLM output. |
| [0017](adr/ADR-0017-observability-stack.md) | Observability Stack | Accepted | 2026-07-25 | Partial | OpenTelemetry/OTLP for telemetry; hash-chained Postgres audit log. |
| [0018](adr/ADR-0018-dashboard-technology-stack.md) | Dashboard Technology Stack | Accepted | 2026-07-25 | None | React 19 + TypeScript + Vite; generated OpenAPI client. |
| [0019](adr/ADR-0019-speech-gateway.md) | Speech Gateway | Accepted | 2026-07-25 | None | Platform-level STT/TTS/wake-word abstraction; Voice pack holds no providers. |
| [0020](adr/ADR-0020-deployment-topology-and-scaling.md) | Deployment Topology and Scaling | Accepted | 2026-07-25 | Partial | Modular monolith, API + worker roles, horizontal via shared Postgres; extraction criteria. |
| [0021](adr/ADR-0021-declarative-workflows-no-dynamic-task-planner.md) | Declarative Workflows | Accepted | 2026-07-25 | Partial | No Task Planner component; dynamic work via plan artifact + `foreach`. |
| [0022](adr/ADR-0022-reproducibility-over-determinism.md) | Reproducibility over Determinism | Accepted | 2026-07-25 | Partial | Run manifest, deterministic platform behaviour, recorded non-determinism. |
| [0023](adr/ADR-0023-identity-roles-and-permissions.md) | Identity, Roles, and Permissions | Accepted | 2026-07-25 | Partial | Three principal types, five roles, monotonic narrowing; single-tenant v1. |
| [0024](adr/ADR-0024-secrets-management-backend.md) | Secrets Management | Accepted | 2026-07-25 | Partial | `secret://` references, pluggable backends (Vault reference), never in sandboxes. |
| [0025](adr/ADR-0025-caching-strategy.md) | Caching Strategy | Accepted | 2026-07-25 | None | Redis platform caches; provider prompt caching; response cache banned in experiments. |

**Summary (2026-07-28):** 25 Accepted — **3 fully implemented** (0003, 0005, 0011), **16 partially implemented**, **6 not yet implemented** (0006, 0007, 0012, 0018, 0019, 0025). No ADR has been contradicted by implementation; every gap is an unbuilt part of an accepted decision, not a deviation from one.

---

## Superseded and Deprecated

None.

---

## Open Decision Points (recorded, not yet decided)

These are known future decisions, deliberately deferred with a stated trigger rather than left undiscovered.

**None of these triggers has fired as of 2026-07-28**, and in most cases the trigger cannot yet be evaluated because the subsystem it measures is unbuilt. The *Trigger reachable today?* column records that honestly, so a reader does not mistake "not triggered" for "measured and found below threshold".

| Topic | Trigger for deciding | Related | Trigger reachable today? |
|---|---|---|---|
| Redis Streams as event transport | Multi-process consumption, or outbox relay lag > 5 s p95 | ADR-0012 | No — no Event Bus and no outbox relay exist; only the `platform.event_outbox` table |
| Dedicated vector store (Qdrant) | > ~20 M chunks, or vector p95 > 200 ms, or contention on primary DB | ADR-0013 | No — no vector search exists; only keyword FTS over `knowledge.chunks` |
| Durable-execution engine (Temporal) | Orchestration correctness effort dominates Stages C–E, or cross-region durability required | ADR-0011 | Partly — Stage B orchestration effort is being tracked; not yet dominant |
| Process isolation per pack | Irreconcilable pack dependency versions, or a compliance isolation requirement | ADR-0009, ADR-0020 | No — only one pack exists, so no version conflict is possible |
| gVisor / micro-VM sandbox default | Multi-tenant deployment, or hostile-input workloads | ADR-0016 | No — single-tenant, and no untrusted-repository ingestion path exists yet |
| External policy engine (OPA / Cedar) | Authorization rules outgrow role + permission intersection | ADR-0023 | No — 4 permissions, no roles, and the intersection rule itself is not yet enforced |
| Multi-tenancy | A second organisation must share one deployment | ADR-0023 | No — no second organisation; no tenant concept in code |
| MCP integration surface | Demand for AI_OS capabilities over MCP | ADR-0014 | No — no external consumers yet; MCP correctly absent from the codebase |

Two items previously carried here as "gaps" in `../19_roadmap/documentation_freeze.md` §5 remain open on the same terms: manifest signing (not in v1) and architecture diagrams beyond ASCII (`../03_architecture/diagrams/` is still empty).

---

## Maintenance

Update this index whenever an ADR is added, accepted, superseded, or deprecated. The index is a navigation aid; the individual ADRs are authoritative.

The `In code` column and each ADR's appended *Implementation Status* note are **derived, not authoritative** — they are a convenience so a reader of a decision is never misled about its delivery. They are refreshed when a step materially changes what exists; on any conflict, [`feature_inventory.md`](../19_roadmap/feature_inventory.md) governs. Refreshing such a note never touches the Accepted decision text above it: an Accepted ADR is revised only by superseding it.
