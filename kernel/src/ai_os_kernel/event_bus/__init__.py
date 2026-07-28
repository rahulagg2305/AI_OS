"""Event Bus — decoupled communication between Kernel components and packs.

In-process asyncio pub/sub by default, plus a transactional outbox for
durable or cross-process events (written in the same transaction as the
state change that produced them). Delivery is at-least-once; subscribers
must be idempotent on `event_id`. Redis Streams is the documented
scale-out transport, adopted only when its trigger condition is met
(ADR-0012).

See docs/03_architecture/kernel/event_bus.md, ADR-0012.
Not yet implemented — Implementation Roadmap Stage B.
"""
