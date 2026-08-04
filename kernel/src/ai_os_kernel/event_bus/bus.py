"""The in-process asyncio pub/sub bus (event_bus.md §4's "In-process
asyncio pub/sub DEFAULT -- bounded per-subscriber queues" box).

Scoped to exactly this ticket's own Goal/Input/Output ("Publish and
subscribe in-process." / "An event." / "Delivered to subscribers.") --
deliberately not the Transactional Outbox, Outbox Relay, Topic/Channel
Manager, or Schema Registry boxes in the same diagram, each a separate,
not-yet-built component.

§4's own classification table marks in-process delivery
"loss-tolerable (cache invalidation, metrics fan-out)", unlike the
outbox, which must never lose an event. That is the deliberate design
here: each subscriber gets its own bounded ``asyncio.Queue``, and
``publish`` never blocks -- a full queue drops the event for that one
slow subscriber (logged, not silent) rather than the publisher, or any
other subscriber, ever waiting on it.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from ai_os_kernel.event_bus.models import Event
from ai_os_kernel.observability.logging import get_logger

_logger = get_logger(__name__)

EventHandler = Callable[[Event], Awaitable[None]]

# One second of buffer at NFR-022's own documented "at least 1,000
# events per second" in-process throughput target
# (docs/02_requirements/non_functional/nfr.md) -- a real, checked
# number, not an arbitrary guess. A slow subscriber past this backlog
# is genuinely falling behind its handler's own real work, not merely
# scheduled unluckily.
DEFAULT_SUBSCRIBER_QUEUE_SIZE = 1_000

_subscription_ids = itertools.count(1)


@dataclass(frozen=True)
class Subscription:
    """Opaque handle returned by :meth:`InProcessEventBus.subscribe`,
    passed back to :meth:`InProcessEventBus.unsubscribe`."""

    subscription_id: int
    event_type: str | None


class EventBus(Protocol):
    """Kernel-local Protocol for this ticket's scope. §4 also names a
    separate ``EventBus (SDK Protocol)`` box for ``platform_sdk`` --
    not defined here, matching this codebase's own established
    precedent of defining Kernel-local Protocols first (CLAUDE.md:
    ``platform_sdk`` holds exactly one real file today)."""

    async def publish(self, event: Event) -> None: ...

    def subscribe(self, event_type: str | None, handler: EventHandler) -> Subscription: ...

    def unsubscribe(self, subscription: Subscription) -> None: ...

    async def aclose(self) -> None: ...


class _Subscriber:
    def __init__(self, subscription: Subscription, handler: EventHandler) -> None:
        self.subscription = subscription
        self.handler = handler
        self.queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=DEFAULT_SUBSCRIBER_QUEUE_SIZE)
        self.task = asyncio.create_task(self._consume())

    async def _consume(self) -> None:
        try:
            while True:
                event = await self.queue.get()
                try:
                    await self.handler(event)
                except Exception as exc:
                    _logger.error(
                        "event_bus.handler_failed",
                        event_id=event.event_id,
                        event_type=event.event_type,
                        error=str(exc),
                    )
        except asyncio.CancelledError:
            raise

    def stop(self) -> None:
        self.task.cancel()


class InProcessEventBus:
    """Real, non-stub in-process pub/sub. Each subscriber runs its own
    consumer task over its own bounded queue, so one slow or failing
    handler never delays delivery to any other subscriber, or the
    publisher itself."""

    def __init__(self) -> None:
        self._subscribers: dict[int, _Subscriber] = {}

    async def publish(self, event: Event) -> None:
        matched = [
            subscriber
            for subscriber in self._subscribers.values()
            if subscriber.subscription.event_type in (None, event.event_type)
        ]
        for subscriber in matched:
            try:
                subscriber.queue.put_nowait(event)
            except asyncio.QueueFull:
                _logger.warning(
                    "event_bus.dropped_backpressure",
                    event_id=event.event_id,
                    event_type=event.event_type,
                    subscription_id=subscriber.subscription.subscription_id,
                )
        _logger.debug(
            "event_bus.published",
            event_id=event.event_id,
            event_type=event.event_type,
            subscriber_count=len(matched),
        )

    def subscribe(self, event_type: str | None, handler: EventHandler) -> Subscription:
        subscription = Subscription(subscription_id=next(_subscription_ids), event_type=event_type)
        self._subscribers[subscription.subscription_id] = _Subscriber(subscription, handler)
        return subscription

    def unsubscribe(self, subscription: Subscription) -> None:
        subscriber = self._subscribers.pop(subscription.subscription_id, None)
        if subscriber is not None:
            subscriber.stop()

    async def aclose(self) -> None:
        """Stops every remaining subscriber's consumer task -- real
        cleanup for tests and process shutdown, not an implicit
        "task leaks until GC" default."""
        subscribers = list(self._subscribers.values())
        self._subscribers.clear()
        for subscriber in subscribers:
            subscriber.stop()
        for subscriber in subscribers:
            with contextlib.suppress(asyncio.CancelledError):
                await subscriber.task
