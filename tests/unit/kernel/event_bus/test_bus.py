"""Real, non-stub proof of :class:`InProcessEventBus` publish/subscribe
behavior (P02-S07-M17-T02): genuine fan-out to multiple real
subscribers over real ``asyncio.Queue``-backed consumer tasks, a slow
subscriber not delaying another's delivery, unsubscribe genuinely
stopping further delivery, and a real backpressure-drop under a full
queue.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import pytest

from ai_os_kernel.event_bus import Event, InProcessEventBus
from ai_os_kernel.event_bus.bus import DEFAULT_SUBSCRIBER_QUEUE_SIZE


@pytest.fixture
async def bus() -> AsyncGenerator[InProcessEventBus, None]:
    instance = InProcessEventBus()
    try:
        yield instance
    finally:
        await instance.aclose()


async def _wait_until(
    predicate: object, *, timeout_seconds: float = 2.0, interval: float = 0.01
) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    while loop.time() < deadline:
        if predicate():  # type: ignore[operator]
            return True
        await asyncio.sleep(interval)
    return False


def _event(event_type: str = "workflow.completed", **payload: object) -> Event:
    return Event(event_type=event_type, source="test", payload=dict(payload))


async def test_a_real_published_event_is_delivered_to_a_real_subscriber(
    bus: InProcessEventBus,
) -> None:
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe("workflow.completed", handler)
    event = _event(workflow_id="wf_123")
    await bus.publish(event)

    assert await _wait_until(lambda: len(received) == 1)
    assert received[0].event_id == event.event_id
    assert received[0].payload == {"workflow_id": "wf_123"}


async def test_multiple_real_subscribers_each_genuinely_receive_the_same_event(
    bus: InProcessEventBus,
) -> None:
    received_a: list[Event] = []
    received_b: list[Event] = []

    async def handler_a(event: Event) -> None:
        received_a.append(event)

    async def handler_b(event: Event) -> None:
        received_b.append(event)

    bus.subscribe("workflow.completed", handler_a)
    bus.subscribe("workflow.completed", handler_b)
    await bus.publish(_event())

    assert await _wait_until(lambda: len(received_a) == 1 and len(received_b) == 1)


async def test_a_subscriber_only_receives_events_of_its_own_subscribed_type(
    bus: InProcessEventBus,
) -> None:
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe("workflow.completed", handler)
    await bus.publish(_event(event_type="workflow.failed"))
    await bus.publish(_event(event_type="workflow.completed"))

    assert await _wait_until(lambda: len(received) == 1)
    assert received[0].event_type == "workflow.completed"


async def test_a_wildcard_subscriber_receives_every_event_type(bus: InProcessEventBus) -> None:
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe(None, handler)
    await bus.publish(_event(event_type="workflow.completed"))
    await bus.publish(_event(event_type="workflow.failed"))

    assert await _wait_until(lambda: len(received) == 2)


async def test_one_slow_subscriber_does_not_delay_delivery_to_a_fast_subscriber(
    bus: InProcessEventBus,
) -> None:
    slow_started = asyncio.Event()
    slow_release = asyncio.Event()
    fast_received: list[Event] = []

    async def slow_handler(event: Event) -> None:
        slow_started.set()
        await slow_release.wait()

    async def fast_handler(event: Event) -> None:
        fast_received.append(event)

    bus.subscribe("workflow.completed", slow_handler)
    bus.subscribe("workflow.completed", fast_handler)
    await bus.publish(_event())

    await asyncio.wait_for(slow_started.wait(), timeout=2.0)
    assert await _wait_until(lambda: len(fast_received) == 1)

    slow_release.set()


async def test_unsubscribe_genuinely_stops_further_delivery(bus: InProcessEventBus) -> None:
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    subscription = bus.subscribe("workflow.completed", handler)
    await bus.publish(_event())
    assert await _wait_until(lambda: len(received) == 1)

    bus.unsubscribe(subscription)
    await bus.publish(_event())
    await asyncio.sleep(0.05)
    assert len(received) == 1


async def test_a_full_subscriber_queue_drops_the_event_instead_of_blocking_publish(
    bus: InProcessEventBus,
) -> None:
    release = asyncio.Event()
    started = asyncio.Event()

    async def blocking_handler(event: Event) -> None:
        started.set()
        await release.wait()

    bus.subscribe("workflow.completed", blocking_handler)

    # Fill the one in-flight slot plus the entire bounded queue.
    await bus.publish(_event())
    await asyncio.wait_for(started.wait(), timeout=2.0)
    for _ in range(DEFAULT_SUBSCRIBER_QUEUE_SIZE):
        await bus.publish(_event())

    # One more publish must return immediately (dropped), never block.
    await asyncio.wait_for(bus.publish(_event()), timeout=1.0)

    release.set()


async def test_a_failing_handler_does_not_block_delivery_of_the_next_event(
    bus: InProcessEventBus,
) -> None:
    received: list[Event] = []

    async def flaky_handler(event: Event) -> None:
        if event.payload.get("fail"):
            raise RuntimeError("boom")
        received.append(event)

    bus.subscribe("workflow.completed", flaky_handler)
    await bus.publish(_event(fail=True))
    await bus.publish(_event(fail=False))

    assert await _wait_until(lambda: len(received) == 1)


async def test_aclose_stops_every_subscriber_consumer_task(bus: InProcessEventBus) -> None:
    async def handler(event: Event) -> None:
        pass

    bus.subscribe("workflow.completed", handler)
    bus.subscribe("workflow.failed", handler)

    await bus.aclose()

    assert bus._subscribers == {}  # noqa: SLF001 -- verifying real internal cleanup
