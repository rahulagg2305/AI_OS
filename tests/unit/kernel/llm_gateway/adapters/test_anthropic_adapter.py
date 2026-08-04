"""Unit tests for :mod:`ai_os_kernel.llm_gateway.adapters.anthropic_adapter`.

No live Anthropic credentials and no cassette library are used here —
see this step's own report for why (``.github/workflows/ci.yml``'s
comment describing a future "recorded cassettes" approach describes
infrastructure that does not exist yet in this repository). Instead:

- ``_map_response`` (pure, no I/O) is exercised directly against real
  ``anthropic.types.Message``/``Usage``/``TextBlock`` objects — genuine
  SDK response shapes, not hand-rolled stand-ins.
- ``AnthropicAdapter.complete()``'s pre-flight validation (unconfigured
  alias/pricing) needs no network at all.
- ``AnthropicAdapter.complete()``'s error-wrapping around the real
  network call is exercised against **real** local TCP endpoints: a
  closed port (a genuine ``anthropic.APIConnectionError``) and a tiny
  local HTTP server returning a real 401 body (a genuine
  ``anthropic.APIStatusError``) — real transport and real SDK error
  parsing, never a mocked client or a monkeypatched method.

This is deliberately not a test of Anthropic's own service — no
assertion here depends on what the real API returns for a real prompt;
that is the opt-in live suite
(``tests/integration/llm_gateway/test_anthropic_adapter_live.py``).
"""

from __future__ import annotations

import contextlib
import http.server
import socket
import threading
from collections.abc import Generator
from decimal import Decimal

import anthropic
import pytest
from anthropic.types import Message, TextBlock, Usage

from ai_os_kernel.llm_gateway.adapters.anthropic_adapter import (
    PROVIDER_NAME,
    AnthropicAdapter,
    _map_response,
    build_anthropic_adapter,
)
from ai_os_kernel.llm_gateway.adapters.model_config import ModelPricing
from ai_os_kernel.llm_gateway.error_taxonomy import ErrorCategory
from ai_os_kernel.llm_gateway.errors import LLMProviderError, LLMRefusalError
from ai_os_kernel.llm_gateway.models import LLMRequest, MessageRole, StopReason
from ai_os_kernel.llm_gateway.models import Message as PlatformMessage
from ai_os_kernel.llm_gateway.router import RoutingDecision, StaticRouter
from ai_os_kernel.secrets_manager.env_provider import EnvSecretProvider

_PRICING = ModelPricing(
    input_per_million_usd=Decimal("5.00"), output_per_million_usd=Decimal("25.00")
)


def _router(model_ids: dict[str, str], *, provider: str = PROVIDER_NAME) -> StaticRouter:
    return StaticRouter(
        routes={
            alias: RoutingDecision(provider=provider, model_id=model_id)
            for alias, model_id in model_ids.items()
        }
    )


def _real_message(*, stop_reason: str, text: str = "hello") -> Message:
    return Message(
        id="msg_test",
        type="message",
        role="assistant",
        model="claude-opus-5",
        stop_reason=stop_reason,
        content=[TextBlock(type="text", text=text)],
        usage=Usage(input_tokens=100, output_tokens=20),
    )


def _request(*, system: str | None = None) -> LLMRequest:
    return LLMRequest(
        model_alias="coding-balanced",
        messages=[PlatformMessage(role=MessageRole.USER, content="hi")],
        max_output_tokens=1024,
        system=system,
    )


# --- _map_response: pure logic, real SDK response objects -----------------


def test_map_response_maps_a_real_end_turn_message() -> None:
    message = _real_message(stop_reason="end_turn", text="hello there")

    response = _map_response(message, latency_ms=42, pricing=_PRICING)

    assert response.content == "hello there"
    assert response.stop_reason.value == "end_turn"
    assert response.provider == "anthropic"
    assert response.model_id == "claude-opus-5"
    assert response.model_version == "claude-opus-5"
    assert response.usage.input_tokens == 100
    assert response.usage.output_tokens == 20
    assert response.usage.latency_ms == 42
    assert response.usage.retries == 0
    assert response.usage.fallback_used is False


def test_map_response_computes_cost_from_configured_pricing() -> None:
    message = _real_message(stop_reason="max_tokens")

    response = _map_response(message, latency_ms=0, pricing=_PRICING)

    # 100 input tokens @ $5/M + 20 output tokens @ $25/M
    expected = (Decimal(100) * Decimal("5.00") + Decimal(20) * Decimal("25.00")) / Decimal(
        1_000_000
    )
    assert response.usage.cost_usd == expected


def test_map_response_honestly_reports_zero_cache_tokens_when_absent() -> None:
    message = _real_message(stop_reason="end_turn")
    assert message.usage.cache_read_input_tokens is None
    assert message.usage.cache_creation_input_tokens is None

    response = _map_response(message, latency_ms=0, pricing=_PRICING)

    assert response.usage.cache_read_tokens == 0
    assert response.usage.cache_write_tokens == 0


def test_map_response_raises_llm_refusal_error_for_a_real_refusal() -> None:
    message = _real_message(stop_reason="refusal")

    with pytest.raises(LLMRefusalError, match="declined"):
        _map_response(message, latency_ms=0, pricing=_PRICING)


@pytest.mark.parametrize("stop_reason", ["tool_use", "pause_turn", "stop_sequence"])
def test_map_response_raises_for_an_unsupported_stop_reason(stop_reason: str) -> None:
    message = _real_message(stop_reason=stop_reason)

    with pytest.raises(LLMProviderError, match="does not represent") as exc_info:
        _map_response(message, latency_ms=0, pricing=_PRICING)

    assert exc_info.value.category == ErrorCategory.PERMANENT
    assert exc_info.value.error_code == "llm.capability_unsupported"
    assert exc_info.value.retriable is False


# --- AnthropicAdapter.complete(): pre-flight validation, no network -------


@pytest.mark.asyncio
async def test_complete_raises_for_an_unconfigured_model_alias() -> None:
    adapter = AnthropicAdapter(
        client=anthropic.AsyncAnthropic(api_key="unused"),
        router=_router({}),
        pricing={},
    )

    with pytest.raises(LLMProviderError, match="no configured route"):
        await adapter.complete(_request())


@pytest.mark.asyncio
async def test_complete_raises_for_unconfigured_pricing() -> None:
    adapter = AnthropicAdapter(
        client=anthropic.AsyncAnthropic(api_key="unused"),
        router=_router({"coding-balanced": "claude-sonnet-5"}),
        pricing={},
    )

    with pytest.raises(LLMProviderError, match="no configured pricing") as exc_info:
        await adapter.complete(_request())

    assert exc_info.value.category == ErrorCategory.PERMANENT
    assert exc_info.value.error_code == "llm.no_pricing"
    assert exc_info.value.retriable is False


@pytest.mark.asyncio
async def test_complete_refuses_a_routing_decision_for_a_different_provider() -> None:
    # This adapter only ever calls Anthropic — see PROVIDER_NAME's own
    # comment — so a Router naming a different provider for this alias
    # must be refused clearly, not silently routed around.
    adapter = AnthropicAdapter(
        client=anthropic.AsyncAnthropic(api_key="unused"),
        router=_router({"coding-balanced": "claude-sonnet-5"}, provider="openai"),
        pricing={"claude-sonnet-5": _PRICING},
    )

    with pytest.raises(LLMProviderError, match="does not serve") as exc_info:
        await adapter.complete(_request())

    assert exc_info.value.category == ErrorCategory.PERMANENT
    assert exc_info.value.error_code == "llm.misrouted"
    assert exc_info.value.retriable is False


# --- AnthropicAdapter.complete(): real network error paths -----------------


def _unused_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.mark.asyncio
async def test_complete_wraps_a_real_connection_failure() -> None:
    closed_port = _unused_local_port()
    adapter = AnthropicAdapter(
        client=anthropic.AsyncAnthropic(
            api_key="unused",
            base_url=f"http://127.0.0.1:{closed_port}",
            timeout=2.0,
            max_retries=0,
        ),
        router=_router({"coding-balanced": "claude-sonnet-5"}),
        pricing={"claude-sonnet-5": _PRICING},
    )

    with pytest.raises(LLMProviderError, match="could not reach Anthropic") as exc_info:
        await adapter.complete(_request())

    assert exc_info.value.category == ErrorCategory.TRANSIENT
    assert exc_info.value.error_code == "llm.network"
    assert exc_info.value.retriable is True
    assert exc_info.value.retry_after_seconds is None


class _AuthenticationErrorHandler(http.server.BaseHTTPRequestHandler):
    _body = (
        b'{"type":"error","error":{"type":"authentication_error","message":"invalid x-api-key"}}'
    )

    def do_POST(self) -> None:
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self._body)))
        self.end_headers()
        self.wfile.write(self._body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass


@pytest.fixture
def authentication_error_server() -> Generator[str, None, None]:
    server = http.server.HTTPServer(("127.0.0.1", 0), _AuthenticationErrorHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()


@pytest.mark.asyncio
async def test_complete_wraps_a_real_401_response(authentication_error_server: str) -> None:
    adapter = AnthropicAdapter(
        client=anthropic.AsyncAnthropic(
            api_key="unused",
            base_url=authentication_error_server,
            timeout=2.0,
            max_retries=0,
        ),
        router=_router({"coding-balanced": "claude-sonnet-5"}),
        pricing={"claude-sonnet-5": _PRICING},
    )

    with pytest.raises(LLMProviderError, match="HTTP 401") as exc_info:
        await adapter.complete(_request())

    assert exc_info.value.category == ErrorCategory.INFRASTRUCTURE
    assert exc_info.value.error_code == "llm.auth_failed"
    assert exc_info.value.retriable is False


class _SuccessfulMessageHandler(http.server.BaseHTTPRequestHandler):
    """Serves a real, well-formed ``Message`` JSON body — the SDK parses
    this exactly as it would a genuine Anthropic response, so a request
    against this server exercises ``complete()`` end to end (kwargs
    construction, the real network round trip, latency measurement, and
    response mapping) without any live credentials."""

    _body = (
        b'{"id":"msg_test123","type":"message","role":"assistant",'
        b'"model":"claude-sonnet-5","content":[{"type":"text","text":"pong"}],'
        b'"stop_reason":"end_turn","stop_sequence":null,'
        b'"usage":{"input_tokens":12,"output_tokens":3}}'
    )

    def do_POST(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self._body)))
        self.end_headers()
        self.wfile.write(self._body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass


@pytest.fixture
def successful_message_server() -> Generator[str, None, None]:
    server = http.server.HTTPServer(("127.0.0.1", 0), _SuccessfulMessageHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()


@pytest.mark.asyncio
async def test_complete_maps_a_real_successful_response_end_to_end(
    successful_message_server: str,
) -> None:
    adapter = AnthropicAdapter(
        client=anthropic.AsyncAnthropic(
            api_key="unused",
            base_url=successful_message_server,
            timeout=2.0,
            max_retries=0,
        ),
        router=_router({"coding-balanced": "claude-sonnet-5"}),
        pricing={"claude-sonnet-5": _PRICING},
    )

    response = await adapter.complete(_request(system="be terse"))

    assert response.content == "pong"
    assert response.stop_reason == StopReason.END_TURN
    assert response.provider == "anthropic"
    assert response.model_id == "claude-sonnet-5"
    assert response.usage.input_tokens == 12
    assert response.usage.output_tokens == 3
    assert response.usage.latency_ms >= 0


# --- AnthropicAdapter.complete(): Error Taxonomy classification -----------


class _StatusErrorHandler(http.server.BaseHTTPRequestHandler):
    """Serves a fixed HTTP status and, optionally, extra headers (e.g.
    ``Retry-After``) — a real local server, parametrised per test rather
    than one hand-written handler class per status code."""

    status_code = 500
    extra_headers: dict[str, str] = {}
    _body = b'{"type":"error","error":{"type":"error","message":"synthetic"}}'

    def do_POST(self) -> None:
        self.send_response(self.status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self._body)))
        for key, value in self.extra_headers.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(self._body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass


@contextlib.contextmanager
def _status_server(
    status_code: int, *, extra_headers: dict[str, str] | None = None
) -> Generator[str, None, None]:
    handler = type(
        "_Handler",
        (_StatusErrorHandler,),
        {"status_code": status_code, "extra_headers": extra_headers or {}},
    )
    server = http.server.HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()


def _adapter_against(base_url: str) -> AnthropicAdapter:
    return AnthropicAdapter(
        client=anthropic.AsyncAnthropic(
            api_key="unused", base_url=base_url, timeout=2.0, max_retries=0
        ),
        router=_router({"coding-balanced": "claude-sonnet-5"}),
        pricing={"claude-sonnet-5": _PRICING},
    )


@pytest.mark.parametrize(
    ("status_code", "expected_category", "expected_error_code", "expected_retriable"),
    [
        (400, ErrorCategory.PERMANENT, "llm.invalid_request", False),
        (401, ErrorCategory.INFRASTRUCTURE, "llm.auth_failed", False),
        (403, ErrorCategory.INFRASTRUCTURE, "llm.auth_failed", False),
        (404, ErrorCategory.PERMANENT, "llm.invalid_request", False),
        (429, ErrorCategory.TRANSIENT, "llm.rate_limited", True),
        (500, ErrorCategory.TRANSIENT, "llm.provider_error", True),
        (529, ErrorCategory.TRANSIENT, "llm.overloaded", True),
    ],
)
@pytest.mark.asyncio
async def test_complete_classifies_real_http_error_responses(
    status_code: int,
    expected_category: ErrorCategory,
    expected_error_code: str,
    expected_retriable: bool,
) -> None:
    with _status_server(status_code) as base_url:
        adapter = _adapter_against(base_url)

        with pytest.raises(LLMProviderError) as exc_info:
            await adapter.complete(_request())

    assert exc_info.value.category == expected_category
    assert exc_info.value.error_code == expected_error_code
    assert exc_info.value.retriable is expected_retriable


@pytest.mark.asyncio
async def test_complete_honours_a_real_retry_after_header() -> None:
    with _status_server(429, extra_headers={"retry-after": "7"}) as base_url:
        adapter = _adapter_against(base_url)

        with pytest.raises(LLMProviderError) as exc_info:
            await adapter.complete(_request())

    assert exc_info.value.retry_after_seconds == 7.0


# --- AnthropicAdapter.count_tokens(): real provider endpoint (§12) --------


class _SuccessfulCountTokensHandler(http.server.BaseHTTPRequestHandler):
    """Serves a real, well-formed ``MessageTokensCount`` JSON body — the
    SDK parses this exactly as it would a genuine Anthropic
    ``/v1/messages/count_tokens`` response."""

    _body = b'{"input_tokens":37}'

    def do_POST(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self._body)))
        self.end_headers()
        self.wfile.write(self._body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass


@pytest.fixture
def successful_count_tokens_server() -> Generator[str, None, None]:
    server = http.server.HTTPServer(("127.0.0.1", 0), _SuccessfulCountTokensHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()


@pytest.mark.asyncio
async def test_count_tokens_returns_the_real_provider_reported_count(
    successful_count_tokens_server: str,
) -> None:
    adapter = _adapter_against(successful_count_tokens_server)

    count = await adapter.count_tokens(_request(system="be terse"))

    assert count == 37


@pytest.mark.asyncio
async def test_count_tokens_refuses_a_routing_decision_for_a_different_provider() -> None:
    adapter = AnthropicAdapter(
        client=anthropic.AsyncAnthropic(api_key="unused"),
        router=_router({"coding-balanced": "claude-sonnet-5"}, provider="openai"),
        pricing={"claude-sonnet-5": _PRICING},
    )

    with pytest.raises(LLMProviderError, match="does not serve") as exc_info:
        await adapter.count_tokens(_request())

    assert exc_info.value.category == ErrorCategory.PERMANENT
    assert exc_info.value.error_code == "llm.misrouted"
    assert exc_info.value.retriable is False


@pytest.mark.asyncio
async def test_count_tokens_wraps_a_real_connection_failure() -> None:
    closed_port = _unused_local_port()
    adapter = AnthropicAdapter(
        client=anthropic.AsyncAnthropic(
            api_key="unused",
            base_url=f"http://127.0.0.1:{closed_port}",
            timeout=2.0,
            max_retries=0,
        ),
        router=_router({"coding-balanced": "claude-sonnet-5"}),
        pricing={"claude-sonnet-5": _PRICING},
    )

    with pytest.raises(LLMProviderError, match="could not reach Anthropic") as exc_info:
        await adapter.count_tokens(_request())

    assert exc_info.value.category == ErrorCategory.TRANSIENT
    assert exc_info.value.error_code == "llm.network"
    assert exc_info.value.retriable is True


@pytest.mark.parametrize(
    ("status_code", "expected_category", "expected_error_code", "expected_retriable"),
    [
        (400, ErrorCategory.PERMANENT, "llm.invalid_request", False),
        (401, ErrorCategory.INFRASTRUCTURE, "llm.auth_failed", False),
        (429, ErrorCategory.TRANSIENT, "llm.rate_limited", True),
        (500, ErrorCategory.TRANSIENT, "llm.provider_error", True),
    ],
)
@pytest.mark.asyncio
async def test_count_tokens_classifies_real_http_error_responses(
    status_code: int,
    expected_category: ErrorCategory,
    expected_error_code: str,
    expected_retriable: bool,
) -> None:
    with _status_server(status_code) as base_url:
        adapter = _adapter_against(base_url)

        with pytest.raises(LLMProviderError) as exc_info:
            await adapter.count_tokens(_request())

    assert exc_info.value.category == expected_category
    assert exc_info.value.error_code == expected_error_code
    assert exc_info.value.retriable is expected_retriable


# --- build_anthropic_adapter: resolves the key via SecretProvider ---------


@pytest.mark.asyncio
async def test_build_anthropic_adapter_resolves_the_key_through_secret_provider() -> None:
    env = {"AIOS_SECRET_LLM_ANTHROPIC_API_KEY": "test-key-value"}

    adapter = await build_anthropic_adapter(
        secret_provider=EnvSecretProvider(env=env),
        api_key_secret_reference="secret://env/llm/anthropic-api-key",  # noqa: S106 — a reference URI, not a credential
        router=_router({"coding-balanced": "claude-sonnet-5"}),
        pricing={"claude-sonnet-5": _PRICING},
    )

    assert isinstance(adapter, AnthropicAdapter)
