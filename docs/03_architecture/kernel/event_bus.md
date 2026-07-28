# Event Bus Design – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Event Bus Design  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## 1. Purpose

This document defines the design of the **Event Bus**, a core component of the AI_OS Platform Kernel.

The Event Bus provides asynchronous, decoupled communication between Kernel components and between the Kernel and Capability Packs. It allows components to publish events and subscribe to events without direct dependencies on one another.

This document is subordinate to:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Kernel Architecture  

---

## Implementation Status (2026-07-28)

**Built:** Nothing — this component is a documented design only; `kernel/src/ai_os_kernel/event_bus/` contains a docstring-only `__init__.py` and zero other `.py` files. The single real artifact anywhere in the codebase is the **table**: `platform.event_outbox`, defined in `kernel/src/ai_os_kernel/persistence/platform_schema.py` and specified in `../../08_database/data_model.md` §10. It has no writer and no reader.

**Not built:** every element of §4 — no `EventBus` Protocol (in the Kernel or in the Platform SDK), no in-process `asyncio` pub/sub, no bounded per-subscriber queues, no Outbox Relay, no Topic/Channel Manager, no Schema Registry of typed Pydantic event models, no observability hook. Nothing publishes to `platform.event_outbox`, so the failure mode §4 exists to prevent — committing a state change and losing its event — is currently avoided only by there being no cross-process observers at all. §5's event contract has no code shape. §7's claimed publishers do not publish: the Workflow Engine writes lifecycle rows to `workflow.workflow_events` (its own event-sourcing log, a different thing from this bus) and emits no events here; the Quality Gate Engine and Capability Manager publish nothing. **Redis is provisioned in `docker-compose` but no Kernel code uses Redis at all**, so the documented Redis Streams scale-out path in §4 has no starting point to migrate from. `LISTEN/NOTIFY` is not used. Roadmap stage: **B** — this is one of the components blocking Stage B exit.

Authoritative, always-current status: `../../19_roadmap/feature_inventory.md` (per-module completion table) and `../../19_roadmap/implementation_status.md`. Detailed build history: `../../19_roadmap/history/INDEX.md`.

---

## 2. Design Goals

The Event Bus must:

- Enable loose coupling between components
- Support reliable publish/subscribe semantics
- Carry sufficient context for downstream consumers (Trace ID, Workflow ID, etc.)
- Be observable
- Remain simple and robust
- Support both internal Kernel events and events relevant to Capability Packs

---

## 3. Core Responsibilities

- Accept events from publishers
- Deliver events to interested subscribers
- Preserve ordering guarantees where required (or clearly define the lack of them)
- Support event schemas / contracts
- Integrate with the platform’s observability model
- Handle back-pressure and failure scenarios gracefully

---

## 4. High-Level Structure

```text
Event Bus                        (ADR-0012)
│
├── EventBus (SDK Protocol)      one interface, swappable transport
├── In-process asyncio pub/sub   DEFAULT — bounded per-subscriber queues
├── Transactional Outbox         durable + cross-process events, written in the
│                                 SAME transaction as the state change
├── Outbox Relay                 publishes and marks dispatched
├── Topic / Channel Manager
├── Schema Registry              typed, versioned Pydantic event models
└── Observability Hook
```

**Technology decided in [ADR-0012](../../18_decision_log/adr/ADR-0012-event-bus.md).** Two mechanisms with a clear rule for choosing:

| Need | Mechanism |
|---|---|
| In-process notification, loss-tolerable (cache invalidation, metrics fan-out) | In-process asyncio bus |
| Must survive a crash, or must reach another process (workflow lifecycle, gate results, approvals, Dashboard updates) | **Transactional outbox** |

The outbox exists because of a specific failure mode: committing a state change and then losing its event leaves the platform's observers permanently out of step with reality. Writing both in one transaction removes that possibility.

**Delivery is at-least-once.** Subscribers must be idempotent on `event_id` — this is a contract, not a recommendation, and it is the property that survives the transport change below.

**Scale trigger → Redis Streams** (same Protocol, no call-site changes): multi-process consumption of the same stream, Dashboard served by separate processes, outbox relay lag > 5 s p95 (`../../02_requirements/non_functional/nfr.md`, NFR-023), or a consumer needing independent scaling. Redis rather than Kafka or NATS because Redis is already a **declared** platform dependency for caching ([ADR-0025](../../18_decision_log/adr/ADR-0025-caching-strategy.md)) and per-principal rate limiting, and is provisioned in `docker-compose.yml`. Accuracy note (2026-07-28): that dependency is declared, not yet exercised — **no Kernel code uses Redis at all**, and neither the cache nor the rate limiter is built, so adopting Streams would be Redis's first real use rather than a reuse of an existing client.

`LISTEN/NOTIFY` is used only as an optional low-latency wake-up hint for the relay — never as a delivery guarantee, since notifications are dropped when no listener is connected.

---

## 5. Event Contract (Conceptual)

Every event should carry at least:

- event_id
- event_type
- timestamp
- source (component / pack)
- trace_id / workflow_id (when applicable)
- payload (structured)
- schema_version

---

## 6. Key Design Rules

- Components should prefer the Event Bus for asynchronous notifications rather than direct calls when decoupling is beneficial.
- Critical synchronous control flow (e.g., Agent invocation) remains synchronous and is not replaced by events.
- Event payloads should be versioned so that evolution is possible.
- Capability Packs may publish and subscribe only to events they have been permitted to use.

---

## 7. Relationship with Other Components

- **Workflow Engine** publishes major lifecycle events.
- **Quality Gate Engine**, **LLM Gateway**, **Capability Manager**, and other Kernel components publish significant events.
- **Dashboard** and monitoring systems subscribe to relevant events.
- **Capability Packs** may publish domain events and subscribe to platform events through approved channels.
- **Observability** stack consumes events for tracing and auditing.

---

## 8. Observability Requirements

The Event Bus itself must emit metrics and logs about:

- Events published
- Delivery successes / failures
- Subscriber lag (when applicable)

---

## 9. Current Status

This document defines the design baseline for the Event Bus. **The three items v1.0 of this section deferred were all decided by [ADR-0012](../../18_decision_log/adr/ADR-0012-event-bus.md), and §4 above already records the decisions** — this section previously contradicted §4 by describing them as unresolved. Corrected:

| Item | Decision | Deciding authority |
|---|---|---|
| **Concrete technology choice** | Not open. In-process `asyncio` pub/sub is the default transport; a transactional outbox in PostgreSQL handles durable and cross-process events; Redis Streams is the pre-approved scale-out transport behind the same Protocol, adopted only on §4's stated trigger. No message broker (Kafka, NATS) is to be introduced. | [ADR-0012](../../18_decision_log/adr/ADR-0012-event-bus.md), with [ADR-0011](../../18_decision_log/adr/ADR-0011-persistence-and-workflow-state.md) for the outbox's same-transaction requirement |
| **Delivery guarantees** | Not open. **At-least-once**, and subscriber idempotency on `event_id` is a contract, not a recommendation. Ordering is guaranteed only per outbox sequence, never across topics. `LISTEN/NOTIFY` is a latency hint only, never a delivery mechanism. | [ADR-0012](../../18_decision_log/adr/ADR-0012-event-bus.md) |
| **Schema management** | Not open. Typed, versioned Pydantic v2 event models in a Schema Registry, with `schema_version` on every event (§5). | [ADR-0012](../../18_decision_log/adr/ADR-0012-event-bus.md), [ADR-0008](../../18_decision_log/adr/ADR-0008-primary-language-and-runtime.md) |

**What genuinely remains open** is one narrow, named question, not a technology choice: **the relay's failure policy** — how many delivery attempts an outbox row gets, with what backoff, and where a permanently undeliverable event goes (a dead-letter column on `platform.event_outbox`, a separate table, or an alert-and-halt). At-least-once delivery is meaningless without a bounded retry policy, and the current `platform.event_outbox` schema has no attempt counter or dead-letter destination, so answering it is a schema decision as well as a code one. It should be settled in the same step that builds the relay.

---

## 10. Final Authority

Order of precedence:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Kernel Architecture  
5. Event Bus Design  
6. Source Code

---

## 11. Related Documents

**Governing decisions (ADRs):**
- [ADR-0012 — Event Bus](../../18_decision_log/adr/ADR-0012-event-bus.md) — the governing decision for this component
- [ADR-0011 — Persistence and Workflow State](../../18_decision_log/adr/ADR-0011-persistence-and-workflow-state.md) — the outbox writes in the same transaction as the state change
- [ADR-0005 — Agents Never Communicate Directly](../../18_decision_log/adr/ADR-0005-agents-never-communicate-directly.md) — why events are notification, never orchestration
- [ADR-0020 — Deployment Topology and Scaling](../../18_decision_log/adr/ADR-0020-deployment-topology-and-scaling.md) — cross-process events between `api` and `worker`
- [ADR-0025 — Caching Strategy](../../18_decision_log/adr/ADR-0025-caching-strategy.md) — Redis as a declared platform dependency
- [ADR-0014 — API Style and Realtime Transport](../../18_decision_log/adr/ADR-0014-api-style-and-realtime-transport.md) — the WebSocket stream that will consume these events

**Superior documents:**
- `../platform/system_architecture.md`
- `kernel_architecture.md`

**Publishers and subscribers:**
- `workflow_engine.md` §5.11 — the primary publisher (lifecycle events); note its own `workflow.workflow_events` log is event *sourcing*, a separate concern from this bus
- `quality_gate_engine.md`, `capability_manager.md`, `llm_gateway.md` — Kernel publishers
- `observability.md` — consumes events for tracing and auditing
- `../platform/platform_sdk.md` §5.7 `EventBus` — the pack-facing Protocol (specified, not built)
- `../../13_dashboard/dashboard_architecture.md` — the main cross-process subscriber
- `../../07_api/api_architecture.md` — `/api/v1/stream`, the WebSocket fan-out

**Owned tables:**
- `../../08_database/data_model.md` §10 — `platform.event_outbox` (and `platform.idempotency_keys`, the related at-least-once companion)

**Reference:**
- `../../02_requirements/non_functional/nfr.md` — NFR-023, relay lag budget
- `../../20_glossary/glossary.md`
- `../../19_roadmap/feature_inventory.md`, `../../19_roadmap/implementation_status.md`, `../../19_roadmap/history/INDEX.md`
