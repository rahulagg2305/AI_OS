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

**Scale trigger → Redis Streams** (same Protocol, no call-site changes): multi-process consumption of the same stream, Dashboard served by separate processes, outbox relay lag > 5 s p95 (NFR-023), or a consumer needing independent scaling. Redis rather than Kafka or NATS because Redis is already a platform dependency for caching and rate limiting.

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

This document defines the design baseline for the Event Bus.

Concrete technology choice (in-process, message broker, etc.), delivery guarantees, and schema management details will be refined during implementation.

---

## 10. Final Authority

Order of precedence:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Kernel Architecture  
5. Event Bus Design  
6. Source Code
