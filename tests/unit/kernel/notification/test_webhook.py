"""Real tests for :mod:`ai_os_kernel.notification.webhook` — a real,
self-hosted local HTTP server (mirrors
``tests/chaos/test_provider_outage_recovery.py``'s own "no mocked
client, real local TCP endpoint" strategy), never monkeypatched.
"""

from __future__ import annotations

import contextlib
import http.server
import threading
from collections.abc import Generator

import pytest

from ai_os_kernel.notification.models import Notification
from ai_os_kernel.notification.webhook import WebhookChannel


class _RecordingHandler(http.server.BaseHTTPRequestHandler):
    """A real HTTP handler whose class-level state every instance
    shares — genuinely records the real request body it received."""

    response_status = 200
    received_bodies: list[bytes] = []

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        type(self).received_bodies.append(self.rfile.read(length))
        self.send_response(type(self).response_status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass


@contextlib.contextmanager
def _webhook_server(
    *, response_status: int = 200
) -> Generator[type[_RecordingHandler], None, None]:
    handler = type(
        "_Handler",
        (_RecordingHandler,),
        {"response_status": response_status, "received_bodies": []},
    )
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


def _notification() -> Notification:
    return Notification(
        notification_type="approval",
        channel="webhook",
        status="pending",
        workflow_id="wf-real-1",
        trace_id="trace-real-1",
        payload={"stepId": "approve-release"},
    )


def test_webhook_url_must_not_be_blank() -> None:
    with pytest.raises(ValueError, match="webhook_url"):
        WebhookChannel(webhook_url="")


async def test_a_real_2xx_response_is_a_genuine_delivery() -> None:
    with _webhook_server(response_status=200) as handler:
        channel = WebhookChannel(webhook_url=handler.base_url)  # type: ignore[attr-defined]

        delivered = await channel.deliver(_notification())

        assert delivered is True
        assert len(handler.received_bodies) == 1
        import json

        real_body = json.loads(handler.received_bodies[0])
        assert real_body["notification_type"] == "approval"
        assert real_body["workflow_id"] == "wf-real-1"
        # `status` is deliberately never sent over the wire — see
        # `webhook.py`'s own docstring for why.
        assert "status" not in real_body


async def test_a_real_non_2xx_response_is_a_genuine_delivery_failure() -> None:
    with _webhook_server(response_status=500) as handler:
        channel = WebhookChannel(webhook_url=handler.base_url)  # type: ignore[attr-defined]

        delivered = await channel.deliver(_notification())

        assert delivered is False


async def test_an_unreachable_target_is_a_genuine_delivery_failure_not_an_exception() -> None:
    # A real, closed port — nothing is listening, a genuine connection
    # refusal, not a simulated one.
    channel = WebhookChannel(webhook_url="http://127.0.0.1:1", timeout_seconds=1.0)

    delivered = await channel.deliver(_notification())

    assert delivered is False
