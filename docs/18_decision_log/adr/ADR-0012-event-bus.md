# ADR-0012: Event Bus — In-Process Async Bus with a Transactional Outbox

**Status:** Accepted
**Date:** 2026-07-25
**Decision Makers:** Chief Architect
**Related Documents:** `docs/03_architecture/kernel/event_bus.md`, `docs/03_architecture/platform/technology_stack.md`

---

## Context

The Event Bus decouples Kernel components, Capability Packs, the Dashboard, and the observability pipeline. Its technology choice determines the deployment topology, so leaving it open blocks both implementation and scaling design. The requirement set is modest today (a handful of publishers, ordered per workflow, delivered to the Dashboard and telemetry) but must not need rewriting when the platform runs on multiple processes.

## Decision

**A two-part design, with an explicit scale trigger.**

**Part 1 — In-process async bus (default, Stage A onward).** An `asyncio`-based publish/subscribe bus inside the Kernel process. Typed, Pydantic-validated events; per-workflow ordering preserved; bounded per-subscriber queues; a slow subscriber is dropped and logged rather than allowed to block a publisher.

**Part 2 — Transactional outbox (from Stage B, for durable and cross-process events).** Events that must survive a crash or reach another process are written to an `event_outbox` table **in the same transaction as the state change that produced them**. A relay publishes them and marks them dispatched. This eliminates the classic failure where state is committed but its event is lost, and it is why the outbox is not deferred.

Every event carries `event_id`, `event_type`, `schema_version`, `timestamp`, `source`, `trace_id`, `workflow_id` (when applicable), and a structured payload. Delivery is **at-least-once**; subscribers must be idempotent on `event_id`. This is stated as a contract, not an aspiration, because it is the property that survives the transport change below.

**Scale trigger — the condition that moves us to Part 3.** Adopt **Redis Streams** as the transport, behind the same `EventBus` Protocol, when any of these becomes true:
1. more than one Kernel process must consume the same event stream;
2. the Dashboard is served by processes separate from the workflow workers;
3. outbox relay lag exceeds 5 seconds at p95 under normal load;
4. an event consumer must scale independently of the Kernel.

Redis is chosen for that step over Kafka or NATS because Redis is already a platform dependency for caching and rate limiting ([ADR-0025](ADR-0025-caching-strategy.md)), Streams provide consumer groups and replay, and it adds no new operational technology. Kafka remains the option beyond Redis if durable multi-day replay across many consumers is ever needed; that would be a further ADR.

## Alternatives Considered

- **Kafka / Redpanda from the start** — Rejected: significant operational weight, and partition-level ordering plus consumer-group design cost is unjustified for the current publisher set.
- **RabbitMQ** — Solid routing; rejected because replay is weak and it introduces a technology used for nothing else.
- **NATS / JetStream** — Excellent fit technically; rejected only because Redis is already required, and adding one dependency rather than two is the better trade at this stage.
- **PostgreSQL `LISTEN/NOTIFY` as the cross-process transport** — Tempting since Postgres is already present; rejected as the primary transport because payloads are size-limited, notifications are dropped when no listener is connected (no replay), and it does not provide consumer groups. It is used only as an optional low-latency wake-up hint for the outbox relay, never as the delivery guarantee.
- **In-process bus only, indefinitely** — Rejected: it silently caps the platform at one process and makes the eventual change a rewrite of every call site.

## Consequences

### Positive
- Stage A and B ship with no broker to operate.
- The outbox makes state-change events reliable from the start.
- The transport is swappable behind one Protocol, with a written trigger so the decision is not indefinitely deferred.

### Negative
- Two mechanisms (in-process fast path, outbox durable path) mean authors must decide which an event needs; the Event Bus design document specifies the rule.
- At-least-once delivery pushes idempotency onto subscribers.

### Neutral
- Event schemas are versioned from the first event, which costs a little ceremony and buys evolution.

## Compliance

Complies with `docs/03_architecture/kernel/event_bus.md` and the Constitution's loose-coupling requirement.

## References

- [ADR-0011](ADR-0011-persistence-and-workflow-state.md), [ADR-0020](ADR-0020-deployment-topology-and-scaling.md)

---

## Implementation Status (appended 2026-07-28, corrected 2026-08-12 — not part of the Accepted decision)

**Status in code:** Both parts of this decision are built and running; two named sub-components are not.

**This section was materially stale until 2026-08-12** and is preserved here as a correction rather than silently rewritten. It read: *"Not yet implemented — `ai_os_kernel.event_bus` is a docstring-only stub — there is no in-process asyncio bus, no event envelope type, no publisher, and no subscriber anywhere in the codebase. The only part of this decision that exists is the `platform.event_outbox` table in the persistence schema, which has no writer and no relay."* Every clause of that had become false: `bus.py`'s `InProcessEventBus` and `models.py`'s typed `Event` envelope shipped in `P02-S07-M17-T02`; `outbox_relay.py`'s `OutboxRelay` in `P02-S07-M17-T03`; real subscribers in `routes/stream.py` (`P06-S02-M37-T01`) and `notification/service.py` (`P06-S05-M22-T01`); and a real publisher in `evaluation_engine/cost_anomaly.py` (`P07-S03-M42-T02`).

**Part 1 (in-process bus) — built and running.** `InProcessEventBus` is constructed unconditionally in `bootstrap.py`'s `_lifespan`, with real production subscribers (the `/api/v1/stream` WebSocket endpoint, `NotificationService`) and a real production publisher (`cost.anomaly`).

**Part 2 (transactional outbox) — built and running as of `P02-S07-M17-T04` (2026-08-12).** The table, a real writer, and a continuously-running relay all now exist. `event_bus.outbox_writer.write_outbox_event` takes the caller's `AsyncConnection` rather than an engine, so this decision's defining requirement — the event row written "in the same transaction as the state change that produced them" — is enforced structurally and proven by a test that rolls the transaction back and asserts no row survives. Its first producer is the Workflow Engine's terminal `workflow.completed` transition; `run_outbox_relay_loop` runs as a registered background task.

**Not built:** the relay's bounded-retry / dead-letter policy (this decision's at-least-once guarantee is honoured, but `attempts` has no cutoff and `platform.event_outbox` has no dead-letter destination — `event_bus.md` §10 names this as the one genuinely open question, and it now matters because real rows finally flow); the Topic/Channel Manager; the Schema Registry (versioning exists only as `Event.schema_version`). Redis Streams remains unadopted, and correctly so — none of §"Scale trigger"'s conditions has been met, and **no Kernel code uses Redis at all**.

Live status: [`feature_inventory.md`](../../19_roadmap/feature_inventory.md) — the authority on per-module completeness · Build history: [`history/INDEX.md`](../../19_roadmap/history/INDEX.md)
