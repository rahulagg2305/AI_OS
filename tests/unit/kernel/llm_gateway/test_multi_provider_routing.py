"""Proves the specific capability this step adds: one real
:class:`~ai_os_kernel.llm_gateway.router.StaticRouter` and one real
:class:`~ai_os_kernel.llm_gateway.gateway.DispatchingLLMGateway`
genuinely reaching **two different real, network-calling provider
adapters** — :class:`~ai_os_kernel.llm_gateway.adapters.
anthropic_adapter.AnthropicAdapter` and :class:`~ai_os_kernel.
llm_gateway.adapters.local_adapter.LocalAdapter` — for two different
aliases, each adapter talking to its own real local HTTP endpoint
(standing in for the real Anthropic/local-model-server APIs exactly
the way every other adapter test in this codebase already does; no
mocked client, no monkeypatching).
"""

from __future__ import annotations

import http.server
import threading
from collections.abc import Generator
from decimal import Decimal

import anthropic
import httpx
import pytest

from ai_os_kernel.llm_gateway.adapters.anthropic_adapter import PROVIDER_NAME as ANTHROPIC
from ai_os_kernel.llm_gateway.adapters.anthropic_adapter import AnthropicAdapter
from ai_os_kernel.llm_gateway.adapters.local_adapter import PROVIDER_NAME as LOCAL
from ai_os_kernel.llm_gateway.adapters.local_adapter import LocalAdapter
from ai_os_kernel.llm_gateway.adapters.model_config import ModelPricing
from ai_os_kernel.llm_gateway.gateway import DispatchingLLMGateway
from ai_os_kernel.llm_gateway.models import LLMRequest, Message, MessageRole
from ai_os_kernel.llm_gateway.router import RoutingDecision, StaticRouter

_PRICING = ModelPricing(
    input_per_million_usd=Decimal("1.00"), output_per_million_usd=Decimal("1.00")
)


class _AnthropicShapedHandler(http.server.BaseHTTPRequestHandler):
    _body = (
        b'{"id":"msg_test","type":"message","role":"assistant",'
        b'"model":"claude-sonnet-5","content":[{"type":"text","text":"from anthropic"}],'
        b'"stop_reason":"end_turn","stop_sequence":null,'
        b'"usage":{"input_tokens":1,"output_tokens":1}}'
    )

    def do_POST(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self._body)))
        self.end_headers()
        self.wfile.write(self._body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass


class _LocalShapedHandler(http.server.BaseHTTPRequestHandler):
    _body = (
        b'{"id":"chatcmpl-1","model":"llama3.1:8b",'
        b'"choices":[{"index":0,"finish_reason":"stop",'
        b'"message":{"role":"assistant","content":"from local"}}],'
        b'"usage":{"prompt_tokens":1,"completion_tokens":1}}'
    )

    def do_POST(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self._body)))
        self.end_headers()
        self.wfile.write(self._body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass


def _run_server(handler: type[http.server.BaseHTTPRequestHandler]) -> Generator[str, None, None]:
    server = http.server.HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()


@pytest.fixture
def anthropic_shaped_server() -> Generator[str, None, None]:
    yield from _run_server(_AnthropicShapedHandler)


@pytest.fixture
def local_shaped_server() -> Generator[str, None, None]:
    yield from _run_server(_LocalShapedHandler)


def _request(model_alias: str) -> LLMRequest:
    return LLMRequest(
        model_alias=model_alias,
        messages=[Message(role=MessageRole.USER, content="hi")],
        max_output_tokens=16,
    )


@pytest.mark.asyncio
async def test_one_router_and_dispatcher_genuinely_reach_both_real_provider_adapters(
    anthropic_shaped_server: str, local_shaped_server: str
) -> None:
    router = StaticRouter(
        routes={
            "coding-balanced": RoutingDecision(provider=ANTHROPIC, model_id="claude-sonnet-5"),
            "local-fast": RoutingDecision(provider=LOCAL, model_id="llama3.1:8b"),
        }
    )
    anthropic_adapter = AnthropicAdapter(
        client=anthropic.AsyncAnthropic(
            api_key="unused", base_url=anthropic_shaped_server, timeout=2.0, max_retries=0
        ),
        router=router,
        pricing={"claude-sonnet-5": _PRICING},
    )
    local_adapter = LocalAdapter(
        client=httpx.AsyncClient(base_url=local_shaped_server, timeout=2.0),
        router=router,
        pricing={"llama3.1:8b": _PRICING},
    )
    dispatcher = DispatchingLLMGateway(
        router=router, gateways={ANTHROPIC: anthropic_adapter, LOCAL: local_adapter}
    )

    anthropic_response = await dispatcher.complete(_request("coding-balanced"))
    local_response = await dispatcher.complete(_request("local-fast"))

    assert anthropic_response.content == "from anthropic"
    assert anthropic_response.provider == "anthropic"
    assert local_response.content == "from local"
    assert local_response.provider == "local"
