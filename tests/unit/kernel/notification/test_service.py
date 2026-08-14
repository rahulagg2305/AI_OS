"""Real, end-to-end tests for :mod:`ai_os_kernel.notification.service`
— a real `InProcessEventBus`, a real `WebhookChannel`, and a real local
HTTP server, exactly the way a real Kernel process would compose them
(no fakes, no mocks): publishing a real `Event` to the real bus must
genuinely reach the real server as a real HTTP POST.
"""

from __future__ import annotations

import asyncio
import contextlib
import http.server
import json
import threading
from collections.abc import Callable, Generator

from ai_os_kernel.event_bus.bus import InProcessEventBus
from ai_os_kernel.event_bus.models import Event
from ai_os_kernel.notification.models import Notification
from ai_os_kernel.notification.service import NotificationService
from ai_os_kernel.notification.webhook import (
    _DEFAULT_TIMEOUT_SECONDS as _DEFAULT_WEBHOOK_TIMEOUT_SECONDS,
)
from ai_os_kernel.notification.webhook import WebhookChannel


class _FakeNotificationDeliveryRecorder:
    """A real, deterministic fake (ADR-0004: interface-driven,
    configuration over code) — this file proves the service's own
    real event-classification and delivery logic, not the real
    Postgres-backed recorder, which has its own dedicated,
    real-database test (`test_recorder.py`)."""

    def __init__(self) -> None:
        self.recorded: list[Notification] = []

    async def record(self, notification: Notification) -> None:
        self.recorded.append(notification)


# Real per-consumer-task delivery is genuinely asynchronous (the bus's
# own per-subscriber queue + consumer task, `event_bus/bus.py`'s own
# docstring) — a short, bounded real wait for the real HTTP POST to
# land, not a fixed sleep guessing at timing.
#
# **Derived from the channel's own timeout, never hand-picked
# (`P07-S03-M42-T03`, R-015's 5th occurrence).** This was a flat `2.0`
# while `WebhookChannel`'s own per-delivery budget is `5.0`, so a test
# awaiting *two* sequential deliveries could give up after 2s while
# every component was still behaving exactly as designed — the
# assertion failed for a reason that had nothing to do with the code
# under test. It passed 5/5 on an idle machine and failed only under
# concurrent load, which is precisely why it survived so long.
#
# The fix is the link, not a bigger number: the deadline is now
# computed from the real production constant, so raising or lowering
# that timeout can never again silently outrun this file's patience.
_MAX_SEQUENTIAL_DELIVERIES_AWAITED = 2
_POLL_GRACE_SECONDS = 1.0
_POLL_TIMEOUT_SECONDS = (
    _DEFAULT_WEBHOOK_TIMEOUT_SECONDS * _MAX_SEQUENTIAL_DELIVERIES_AWAITED + _POLL_GRACE_SECONDS
)
_POLL_INTERVAL_SECONDS = 0.02


class _RecordingHandler(http.server.BaseHTTPRequestHandler):
    received_bodies: list[bytes] = []

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        type(self).received_bodies.append(self.rfile.read(length))
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass


@contextlib.contextmanager
def _webhook_server() -> Generator[type[_RecordingHandler], None, None]:
    handler = type("_Handler", (_RecordingHandler,), {"received_bodies": []})
    server = http.server.HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        handler.base_url = f"http://127.0.0.1:{server.server_port}"  # type: ignore[attr-defined]
        yield handler
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


async def _wait_until(
    predicate: Callable[[], bool], *, timeout_seconds: float, interval: float
) -> bool:
    deadline = asyncio.get_event_loop().time() + timeout_seconds
    while asyncio.get_event_loop().time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(interval)
    return predicate()


async def test_a_real_approval_event_genuinely_reaches_the_real_webhook() -> None:
    with _webhook_server() as handler:
        bus = InProcessEventBus()
        channel = WebhookChannel(webhook_url=handler.base_url)  # type: ignore[attr-defined]
        recorder = _FakeNotificationDeliveryRecorder()
        service = NotificationService(event_bus=bus, channel=channel, recorder=recorder)
        try:
            await bus.publish(
                Event(
                    event_type="approval.requested",
                    source="test",
                    workflow_id="wf-real-1",
                    payload={"approvalId": "appr-1"},
                )
            )

            assert await _wait_until(
                lambda: len(handler.received_bodies) == 1,
                timeout_seconds=_POLL_TIMEOUT_SECONDS,
                interval=_POLL_INTERVAL_SECONDS,
            )
            body = json.loads(handler.received_bodies[0])
            assert body["notification_type"] == "approval"
            assert body["workflow_id"] == "wf-real-1"
            assert body["payload"] == {"approvalId": "appr-1"}

            assert await _wait_until(
                lambda: len(recorder.recorded) == 1,
                timeout_seconds=_POLL_TIMEOUT_SECONDS,
                interval=_POLL_INTERVAL_SECONDS,
            )
            assert recorder.recorded[0].status == "sent"
            assert recorder.recorded[0].notification_type == "approval"
        finally:
            service.close()
            await bus.aclose()


async def test_real_failure_and_completion_events_both_genuinely_notify() -> None:
    with _webhook_server() as handler:
        bus = InProcessEventBus()
        channel = WebhookChannel(webhook_url=handler.base_url)  # type: ignore[attr-defined]
        service = NotificationService(
            event_bus=bus, channel=channel, recorder=_FakeNotificationDeliveryRecorder()
        )
        try:
            await bus.publish(
                Event(event_type="workflow.failed", source="test", workflow_id="wf-a")
            )
            await bus.publish(
                Event(event_type="workflow.completed", source="test", workflow_id="wf-b")
            )

            assert await _wait_until(
                lambda: len(handler.received_bodies) == 2,
                timeout_seconds=_POLL_TIMEOUT_SECONDS,
                interval=_POLL_INTERVAL_SECONDS,
            )
            types = {json.loads(b)["notification_type"] for b in handler.received_bodies}
            assert types == {"failure", "completion"}
        finally:
            service.close()
            await bus.aclose()


async def test_a_real_cost_anomaly_event_genuinely_reaches_the_real_webhook() -> None:
    with _webhook_server() as handler:
        bus = InProcessEventBus()
        channel = WebhookChannel(webhook_url=handler.base_url)  # type: ignore[attr-defined]
        service = NotificationService(
            event_bus=bus, channel=channel, recorder=_FakeNotificationDeliveryRecorder()
        )
        try:
            await bus.publish(
                Event(
                    event_type="cost.anomaly",
                    source="evaluation_engine.cost_anomaly",
                    payload={"current_hour_spend_usd": "10.000000"},
                )
            )

            assert await _wait_until(
                lambda: len(handler.received_bodies) == 1,
                timeout_seconds=_POLL_TIMEOUT_SECONDS,
                interval=_POLL_INTERVAL_SECONDS,
            )
            body = json.loads(handler.received_bodies[0])
            assert body["notification_type"] == "cost_anomaly"
            assert body["payload"] == {"current_hour_spend_usd": "10.000000"}
        finally:
            service.close()
            await bus.aclose()


async def test_an_unrelated_event_type_is_genuinely_not_notified() -> None:
    with _webhook_server() as handler:
        bus = InProcessEventBus()
        channel = WebhookChannel(webhook_url=handler.base_url)  # type: ignore[attr-defined]
        service = NotificationService(
            event_bus=bus, channel=channel, recorder=_FakeNotificationDeliveryRecorder()
        )
        try:
            await bus.publish(Event(event_type="system.pack_activated", source="test"))
            # A real, bounded wait proving *absence* — the same "genuinely
            # did not happen, not merely not-yet-observed" discipline
            # every other negative-outcome test in this codebase uses.
            await asyncio.sleep(0.1)

            assert handler.received_bodies == []
        finally:
            service.close()
            await bus.aclose()


async def test_close_genuinely_unsubscribes() -> None:
    with _webhook_server() as handler:
        bus = InProcessEventBus()
        channel = WebhookChannel(webhook_url=handler.base_url)  # type: ignore[attr-defined]
        service = NotificationService(
            event_bus=bus, channel=channel, recorder=_FakeNotificationDeliveryRecorder()
        )
        service.close()

        await bus.publish(
            Event(event_type="approval.requested", source="test", workflow_id="wf-real-1")
        )
        await asyncio.sleep(0.1)

        assert handler.received_bodies == []
        await bus.aclose()
