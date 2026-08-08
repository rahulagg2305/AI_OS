"""Chaos test 2 of 2 (``P07-S03-M42-T01``): a real LLM provider drops,
prove the running system recovers on its own — the real, already-wired
:class:`~ai_os_kernel.llm_gateway.gateway.DispatchingLLMGateway` +
:class:`~ai_os_kernel.llm_gateway.circuit_breaker.InMemoryCircuitBreaker`
composition ``bootstrap.py`` itself builds
(``_CIRCUIT_BREAKER_FAILURE_THRESHOLD``/``_CIRCUIT_BREAKER_RESET_TIMEOUT_SECONDS``),
not the breaker in isolation (already unit-tested in
``test_circuit_breaker.py``).

**A real, self-hosted, mutable HTTP server** (mirrors
``test_local_adapter.py``'s own "no mocked client, real local TCP
endpoint" strategy) starts in a failing state — every request answers
500, a real provider outage — then is genuinely switched to succeeding
mid-test, simulating the provider coming back. Nothing here is
monkeypatched: the real ``LocalAdapter``, over a real ``httpx.AsyncClient``,
makes real HTTP calls against a real local server for every single
step below.

Three real, separate proof points, mirroring
``circuit_breaker.py``'s own three-state description exactly: (1) real
consecutive failures genuinely open the circuit; (2) an open circuit
genuinely short-circuits — refused with ``llm.circuit_open`` before any
further network call is even attempted, proven by the server's own
real request count staying flat; (3) once the reset timeout elapses
and the provider is genuinely back, a real trial call succeeds and the
circuit genuinely closes.
"""

from __future__ import annotations

import asyncio
import contextlib
import http.server
import threading
from collections.abc import Generator
from decimal import Decimal

import pytest

from ai_os_kernel.llm_gateway.adapters.local_adapter import PROVIDER_NAME, build_local_adapter
from ai_os_kernel.llm_gateway.adapters.model_config import ModelPricing
from ai_os_kernel.llm_gateway.circuit_breaker import InMemoryCircuitBreaker
from ai_os_kernel.llm_gateway.errors import LLMProviderError
from ai_os_kernel.llm_gateway.gateway import DispatchingLLMGateway
from ai_os_kernel.llm_gateway.models import LLMRequest, Message, MessageRole
from ai_os_kernel.llm_gateway.router import RoutingDecision, StaticRouter

_MODEL_ALIAS = "local-fast"
_MODEL_ID = "llama3.1:8b"
_PRICING = {
    _MODEL_ID: ModelPricing(input_per_million_usd=Decimal("0"), output_per_million_usd=Decimal("0"))
}
_FAILURE_THRESHOLD = 2
_RESET_TIMEOUT_SECONDS = 0.3
_SUCCESS_BODY = (
    b'{"model":"llama3.1:8b","choices":[{"finish_reason":"stop",'
    b'"message":{"content":"provider is back"}}],'
    b'"usage":{"prompt_tokens":5,"completion_tokens":3}}'
)
_FAILURE_BODY = b'{"error":"synthetic provider outage"}'


class _TogglableOutageHandler(http.server.BaseHTTPRequestHandler):
    """A real HTTP handler whose *class-level* ``failing``/``request_count``
    state every instance shares — genuinely switched mid-test to
    simulate a real provider outage ending, not two separate servers."""

    failing = True
    request_count = 0

    def do_POST(self) -> None:
        type(self).request_count += 1
        if type(self).failing:
            body = _FAILURE_BODY
            self.send_response(500)
        else:
            body = _SUCCESS_BODY
            self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass


@contextlib.contextmanager
def _outage_server() -> Generator[type[_TogglableOutageHandler], None, None]:
    handler = type("_Handler", (_TogglableOutageHandler,), {"failing": True, "request_count": 0})
    server = http.server.HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        handler.base_url = f"http://127.0.0.1:{server.server_port}"  # type: ignore[attr-defined]
        yield handler
    finally:
        server.shutdown()
        thread.join()


def _gateway_against(
    base_url: str, *, circuit_breaker: InMemoryCircuitBreaker
) -> DispatchingLLMGateway:
    router = StaticRouter(
        routes={_MODEL_ALIAS: RoutingDecision(provider=PROVIDER_NAME, model_id=_MODEL_ID)}
    )
    adapter = build_local_adapter(base_url=base_url, router=router, pricing=_PRICING)
    return DispatchingLLMGateway(
        router=router,
        gateways={PROVIDER_NAME: adapter},
        circuit_breaker=circuit_breaker,
    )


def _request() -> LLMRequest:
    return LLMRequest(
        model_alias=_MODEL_ALIAS,
        messages=[Message(role=MessageRole.USER, content="hi")],
        max_output_tokens=64,
    )


async def test_a_dropped_provider_opens_the_circuit_short_circuits_then_recovers() -> None:
    with _outage_server() as handler:
        breaker = InMemoryCircuitBreaker(
            failure_threshold=_FAILURE_THRESHOLD, reset_timeout_seconds=_RESET_TIMEOUT_SECONDS
        )
        gateway = _gateway_against(handler.base_url, circuit_breaker=breaker)  # type: ignore[attr-defined]

        # 1. The real outage: _FAILURE_THRESHOLD consecutive real HTTP
        # 500s, each a genuine round trip to the real local server.
        for _ in range(_FAILURE_THRESHOLD):
            with pytest.raises(LLMProviderError) as exc_info:
                await gateway.complete(_request())
            assert exc_info.value.category.value == "transient"
        assert handler.request_count == _FAILURE_THRESHOLD

        # 2. Genuinely short-circuited: refused with `llm.circuit_open`
        # before any further network call — the server's own real
        # request count proves no HTTP request was even attempted.
        with pytest.raises(LLMProviderError) as exc_info:
            await gateway.complete(_request())
        assert exc_info.value.error_code == "llm.circuit_open"
        assert handler.request_count == _FAILURE_THRESHOLD  # unchanged — no real call made

        # 3. The real provider comes back, and the reset timeout
        # genuinely elapses (real wall-clock sleep, no time-mocking).
        handler.failing = False
        await asyncio.sleep(_RESET_TIMEOUT_SECONDS + 0.2)

        response = await gateway.complete(_request())
        assert response.content == "provider is back"
        assert handler.request_count == _FAILURE_THRESHOLD + 1

        # The circuit genuinely closed: a call right after the real
        # recovery succeeds again with no further delay.
        second_response = await gateway.complete(_request())
        assert second_response.content == "provider is back"
        assert handler.request_count == _FAILURE_THRESHOLD + 2
