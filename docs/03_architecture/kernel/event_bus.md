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

## Implementation Status (2026-08-04)

**Built (`P02-S07-M17-T02`):** the §4 "In-process asyncio pub/sub DEFAULT — bounded per-subscriber queues" box — `kernel/src/ai_os_kernel/event_bus/models.py` (a typed, versioned Pydantic `Event` per §5/§9: `event_id`, `event_type`, `timestamp`, `source`, optional `trace_id`/`workflow_id`, structured `payload`, `schema_version`), `ids.py` (`bevt_`-prefixed ULIDs — deliberately distinct from `workflow_engine.ids.new_event_id`'s `evt_` prefix, a different, event-*sourcing* concept per §7's own disclaimer), and `bus.py` (a Kernel-local `EventBus` Protocol plus `InProcessEventBus`: bounded per-subscriber `asyncio.Queue`, non-blocking `publish` that drops and logs on a full queue rather than ever blocking the publisher or another subscriber — matching §4's own "loss-tolerable" classification for this box — one consumer task per subscriber so a slow or failing handler cannot delay another's delivery, and `aclose()` for real shutdown). Proven by 9 real tests (`tests/unit/kernel/event_bus/test_bus.py`): fan-out, event-type filtering, a wildcard subscriber, slow-subscriber isolation, unsubscribe, a real backpressure drop, and failing-handler isolation.

**Built (`P02-S07-M17-T03`):** the §4 "Outbox Relay" box — `outbox_relay.py`'s `OutboxRelay`, draining `platform.event_outbox` (no writer existed at the time — rows were seeded directly in tests, mirroring how `tests/integration/workflow_engine/test_scheduler.py` seeds `scheduled_at`; `P02-S07-M17-T04` below added the real writer) into the same, unchanged `InProcessEventBus`. Row-claiming reuses the identical `SELECT ... FOR UPDATE SKIP LOCKED` pattern `workflow_engine.lease.SqlWorkflowLeaseRepository.reap_expired` already established. A rebuilt `Event.event_id` reuses the row's own `outbox_id`; `Event.source` is the fixed, honest `"platform.event_outbox"` since the table has no producer-identity column (a real, disclosed schema limitation, not a workaround); `Event.workflow_id` is always `None` for the same reason. A failed dispatch increments `attempts` and leaves `dispatched_at` null, so the row is a genuine candidate again next pass — no max-attempts/dead-letter cutoff exists, since the table has no column for one. Proven by 4 real tests against a real Postgres container (`tests/integration/event_bus/test_outbox_relay.py`): relay-and-deliver, no-redispatch-of-an-already-dispatched-row, a genuine dispatch failure leaving the row retryable and a second pass then delivering it, and an empty pass on an empty backlog.

**Built (`P06-S02-M37-T01`, 2026-08-08):** the first real subscriber outside this package and `outbox_relay.py` — `ai_os_kernel.routes.stream`'s real WebSocket endpoint (`/api/v1/stream`, ADR-0014) genuinely calls `subscribe`/`unsubscribe` on `app.state.event_bus`, a real `InProcessEventBus` now built unconditionally in `_lifespan`. See that route's own module docstring for the real topic -> `Event`-field mapping it uses in place of a Topic/Channel Manager, and for the still-real, still-disclosed gap this does not close: no Kernel component publishes to the bus in production yet (the paragraph below is otherwise unchanged).

**Built (`P02-S07-M17-T04`, 2026-08-12):** the outbox **writer**, and the relay genuinely running — the two halves that turn §4's durable path from tested-in-isolation into a real production route. `outbox_writer.py`'s `write_outbox_event` takes the caller's `AsyncConnection`, deliberately **not** an `AsyncEngine` like every other persistence collaborator in this codebase: §5's requirement is that the event row is written "in the same transaction as the state change that produced them" (ADR-0012, ADR-0011), which is only real if the writer joins a transaction its caller already opened. Its first producer is the Workflow Engine's own terminal transition — `SqlWorkflowInstanceRepository.advance_workflow`'s completion branch, which was *already* emitting the byte-identical `"workflow.completed"` string into `workflow.workflow_events` inside that same transaction, so no new transaction boundary was introduced. `run_outbox_relay_loop` is now started in `bootstrap.py` (`register_task("outbox_relay", …)`, cancellation-based, mirroring `scheduler` exactly as this section previously predicted it would), with a real `outbox_relay_interval_seconds` test-override knob defaulting to the decided `OUTBOX_RELAY_INTERVAL_SECONDS`. **Which mechanism this event uses was not a judgement call:** §5's own decision table assigns "workflow lifecycle" to the transactional outbox, so a direct `InProcessEventBus.publish` from the Workflow Engine would have contradicted this document. Net effect: a committed workflow completion now reaches `NotificationService`, which had been subscribed but unreachable for that category since it was built. `workflow_id` travels in the `payload` because the table has no such column (the T03 limitation above, unchanged). Proven by 4 real tests against a real Postgres container (`tests/integration/event_bus/test_workflow_completion_outbox.py`): the whole chain end to end with every class real except the delivery channel (status → outbox row → relay → bus → service → a real `notification.notification_deliveries` row); a rolled-back transaction leaving **no** outbox row, which is ADR-0012's guarantee proven directly rather than assumed; a non-terminal advance writing no row; and a genuinely failed completion notifying nobody.

**Built (`P02-S07-M17-T05`, 2026-08-12):** the second real outbox producer, and the one that closes §5's own "approvals" row of the decision table — `workflow_engine.human_approval.SqlApprovalRepository` now writes `approval.requested` from `create_pending` and `approval.decided` from `decide`, each through `write_outbox_event` inside the transaction that already records the approval itself. Nothing in production had ever published an `approval.`-prefixed event, so `NotificationService`'s approval branch (`_APPROVAL_EVENT_TYPE_PREFIX`, built with the service) had never once fired: a run could pause durably on a *human being* and no channel anywhere was told. **The mechanism was again not a choice** — §5's table lists "approvals" beside workflow lifecycle under **Transactional outbox**, so a direct `InProcessEventBus.publish` here would contradict this document. `approval.decided` carries `decided_by`, because ADR-0007/R-001 make attributable human approval a permanent hard rule; the same-transaction write is what makes that attribution trustworthy, since a decision that does not commit can never be announced. Proven by 3 real tests against a real Postgres container (`tests/integration/event_bus/test_approval_outbox.py`): a paused workflow reaching a real delivery and a real `notification.notification_deliveries` row through the whole chain; a decision announced with its decider; and a refused double-decide (`ApprovalNotPendingError`, guarded by `WHERE status = 'pending'`) publishing **nothing** — the governance property proven rather than assumed.

**Not built:** the `EventBus (SDK Protocol)` in `platform_sdk` (this module's own `module_path` and CLAUDE.md's "platform_sdk holds exactly one real file" together justify a Kernel-local Protocol first, matching established precedent elsewhere in this codebase); no Topic/Channel Manager; no Schema Registry component (schema versioning exists only as `Event.schema_version`); no dedicated observability hook beyond this module's own structured `event_bus.*`/`outbox_relay.*` log lines. **§7's claimed publishers are now only partly real:** the Workflow Engine does publish, but for exactly one event — its terminal `workflow.completed`, via the outbox (`P02-S07-M17-T04`). **`workflow.failed` is real too, as of 2026-08-13 (`P02-S01-M05-T18`)** — this line's own prior reasoning has been overtaken twice in three days and both corrections matter. It used to say the event could not exist because no production code ever persisted an instance as `failed`; `P02-S01-M05-T17` made that state real (R-016), and `T18` then gave the event its producer: `SqlWorkflowInstanceRepository.mark_failed` writes `workflow.failed` to `platform.event_outbox` inside its own already-open transaction, exactly as the completion branch does. So the Workflow Engine now publishes **two** real lifecycle events, not one. It still writes every other lifecycle row only to `workflow.workflow_events`, its own separate event-sourcing log — ordinary step progress is not outboxed, and per-*step* failures remain `record_failed_attempt` rows rather than events. The Quality Gate Engine and Capability Manager still publish nothing. **`approval.*` now has a real producer** (`P02-S07-M17-T05`, above), and as of 2026-08-13 so does `failure` (`P02-S01-M05-T18`) — **all four of `NotificationService`'s categories are now genuinely reachable in a configured production deployment**, the last one having been subscribed since that service was built while nothing anywhere emitted its event. Proven end to end by `tests/integration/event_bus/test_workflow_failure_outbox.py`, including from the real worker loop's own retry exhaustion. The relay's retry policy also remains unbounded — see §10's own named open question, which this step did not settle and which now genuinely matters, since real rows finally flow. **Redis is provisioned in `docker-compose` but no Kernel code uses Redis at all** — the documented Redis Streams scale-out path in §4 has no starting point to migrate from. `LISTEN/NOTIFY` is not used. Roadmap stage: **B** — the in-process bus, the outbox relay, and a real writer are all done; the Topic/Channel Manager and the Schema Registry still block Stage B exit for this component.

Authoritative, always-current status: `../../19_roadmap/feature_inventory.md` (per-module completion table — the authority on per-module completeness per the 2026-08-11 ruling; `implementation_status.md` is **superseded** and authoritative for nothing). Detailed build history: `../../19_roadmap/history/INDEX.md`.

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
- `../../19_roadmap/feature_inventory.md`, `../../19_roadmap/history/INDEX.md`
