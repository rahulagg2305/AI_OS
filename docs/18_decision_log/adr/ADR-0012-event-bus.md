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
