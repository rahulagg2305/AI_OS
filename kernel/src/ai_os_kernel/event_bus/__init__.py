"""Event Bus — decoupled communication between Kernel components and packs.

In-process asyncio pub/sub by default, plus a transactional outbox for
durable or cross-process events (written in the same transaction as the
state change that produced them). Delivery is at-least-once; subscribers
must be idempotent on `event_id`. Redis Streams is the documented
scale-out transport, adopted only when its trigger condition is met
(ADR-0012).

See docs/03_architecture/kernel/event_bus.md, ADR-0012.

Implemented so far: the in-process asyncio pub/sub box
(:class:`InProcessEventBus`, ``P02-S07-M17-T02``) and the Outbox Relay
(:class:`OutboxRelay`, ``P02-S07-M17-T03``, draining
``platform.event_outbox`` into the in-process bus). No writer for
``platform.event_outbox`` exists yet; the Topic/Channel Manager and
Schema Registry boxes remain not yet implemented.
"""

from ai_os_kernel.event_bus.bus import (
    DEFAULT_SUBSCRIBER_QUEUE_SIZE,
    EventBus,
    EventHandler,
    InProcessEventBus,
    Subscription,
)
from ai_os_kernel.event_bus.ids import new_event_id, new_outbox_id
from ai_os_kernel.event_bus.models import Event
from ai_os_kernel.event_bus.outbox_relay import (
    OUTBOX_RELAY_BATCH_LIMIT,
    OUTBOX_RELAY_INTERVAL_SECONDS,
    OUTBOX_RELAY_SOURCE,
    OutboxRelay,
    OutboxRelayResult,
    run_outbox_relay_loop,
)

__all__ = [
    "DEFAULT_SUBSCRIBER_QUEUE_SIZE",
    "OUTBOX_RELAY_BATCH_LIMIT",
    "OUTBOX_RELAY_INTERVAL_SECONDS",
    "OUTBOX_RELAY_SOURCE",
    "Event",
    "EventBus",
    "EventHandler",
    "InProcessEventBus",
    "OutboxRelay",
    "OutboxRelayResult",
    "Subscription",
    "new_event_id",
    "new_outbox_id",
    "run_outbox_relay_loop",
]
