"""Unit tests for :mod:`ai_os_kernel.llm_gateway.adapters.local_adapter`.

Mirrors ``test_anthropic_adapter.py``'s own testing strategy exactly —
no mocked client, no cassette library: ``LocalAdapter.complete()``'s
pre-flight validation needs no network at all, and its real network
round trip is exercised against real local TCP endpoints (a closed
port for a genuine connection failure, a tiny local HTTP server
returning a real OpenAI-compatible chat-completion body or a real
error status) — real transport, never a monkeypatched method.
"""

from __future__ import annotations

import contextlib
import http.server
import socket
import threading
from collections.abc import Generator
from decimal import Decimal

import httpx
import pytest

from ai_os_kernel.llm_gateway.adapters.local_adapter import (
    PROVIDER_NAME,
    LocalAdapter,
    _map_response,
    build_local_adapter,
)
from ai_os_kernel.llm_gateway.adapters.model_config import ModelPricing
from ai_os_kernel.llm_gateway.error_taxonomy import ErrorCategory
from ai_os_kernel.llm_gateway.errors import LLMProviderError
from ai_os_kernel.llm_gateway.models import EmbeddingRequest, LLMRequest, MessageRole
from ai_os_kernel.llm_gateway.models import Message as PlatformMessage
from ai_os_kernel.llm_gateway.router import RoutingDecision, StaticRouter

_PRICING = ModelPricing(
    input_per_million_usd=Decimal("0.00"), output_per_million_usd=Decimal("0.00")
)

# R-015: a real local HTTP server responds near-instantly in the success
# case, so a generous ceiling costs nothing when the server is healthy —
# it only matters under genuine host-level thread-scheduling contention
# (observed on this project's own local Windows full-suite runs, never
# on the real Ubuntu CI runners), where a too-tight deadline can be
# exceeded even though the server would have replied correctly.
_HTTP_TIMEOUT_SECONDS = 10.0


def _router(model_ids: dict[str, str], *, provider: str = PROVIDER_NAME) -> StaticRouter:
    return StaticRouter(
        routes={
            alias: RoutingDecision(provider=provider, model_id=model_id)
            for alias, model_id in model_ids.items()
        }
    )


def _request(*, system: str | None = None) -> LLMRequest:
    return LLMRequest(
        model_alias="local-fast",
        messages=[PlatformMessage(role=MessageRole.USER, content="hi")],
        max_output_tokens=1024,
        system=system,
    )


# --- _map_response: pure logic, real OpenAI-compatible payload shapes -----


def test_map_response_maps_a_real_stop_payload() -> None:
    payload = {
        "model": "llama3.1:8b",
        "choices": [{"finish_reason": "stop", "message": {"content": "hello there"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 2},
    }

    response = _map_response(payload, latency_ms=42, pricing=_PRICING)

    assert response.content == "hello there"
    assert response.stop_reason.value == "end_turn"
    assert response.provider == "local"
    assert response.model_id == "llama3.1:8b"
    assert response.usage.input_tokens == 10
    assert response.usage.output_tokens == 2
    assert response.usage.cost_usd == 0
    assert response.usage.retries == 0
    assert response.usage.fallback_used is False


def test_map_response_maps_a_real_length_payload() -> None:
    payload = {
        "model": "llama3.1:8b",
        "choices": [{"finish_reason": "length", "message": {"content": "cut off"}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 1},
    }

    response = _map_response(payload, latency_ms=0, pricing=_PRICING)

    assert response.stop_reason.value == "max_tokens"


def test_map_response_computes_cost_from_configured_pricing() -> None:
    pricing = ModelPricing(
        input_per_million_usd=Decimal("1.00"), output_per_million_usd=Decimal("2.00")
    )
    payload = {
        "model": "m",
        "choices": [{"finish_reason": "stop", "message": {"content": "x"}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    }

    response = _map_response(payload, latency_ms=0, pricing=pricing)

    expected = (Decimal(100) * Decimal("1.00") + Decimal(50) * Decimal("2.00")) / Decimal(1_000_000)
    assert response.usage.cost_usd == expected


def test_map_response_raises_for_an_unsupported_finish_reason() -> None:
    payload = {
        "model": "m",
        "choices": [{"finish_reason": "content_filter", "message": {"content": "x"}}],
        "usage": {},
    }

    with pytest.raises(LLMProviderError, match="does not represent") as exc_info:
        _map_response(payload, latency_ms=0, pricing=_PRICING)

    assert exc_info.value.category == ErrorCategory.PERMANENT
    assert exc_info.value.error_code == "llm.capability_unsupported"
    assert exc_info.value.retriable is False


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"choices": []},
        {"choices": [{}]},
        {"choices": [{"finish_reason": "stop"}]},
    ],
)
def test_map_response_raises_clearly_for_a_malformed_payload(payload: dict[str, object]) -> None:
    with pytest.raises(LLMProviderError, match="could not parse") as exc_info:
        _map_response(payload, latency_ms=0, pricing=_PRICING)

    assert exc_info.value.category == ErrorCategory.TRANSIENT
    assert exc_info.value.error_code == "llm.provider_error"
    assert exc_info.value.retriable is True


def test_map_response_defaults_missing_usage_to_zero() -> None:
    payload = {
        "model": "m",
        "choices": [{"finish_reason": "stop", "message": {"content": "x"}}],
    }

    response = _map_response(payload, latency_ms=0, pricing=_PRICING)

    assert response.usage.input_tokens == 0
    assert response.usage.output_tokens == 0


# --- LocalAdapter.complete(): pre-flight validation, no network -----------


@pytest.mark.asyncio
async def test_complete_raises_for_an_unconfigured_model_alias() -> None:
    adapter = LocalAdapter(client=httpx.AsyncClient(), router=_router({}), pricing={})

    with pytest.raises(LLMProviderError, match="no configured route"):
        await adapter.complete(_request())


@pytest.mark.asyncio
async def test_complete_raises_for_unconfigured_pricing() -> None:
    adapter = LocalAdapter(
        client=httpx.AsyncClient(),
        router=_router({"local-fast": "llama3.1:8b"}),
        pricing={},
    )

    with pytest.raises(LLMProviderError, match="no configured pricing") as exc_info:
        await adapter.complete(_request())

    assert exc_info.value.category == ErrorCategory.PERMANENT
    assert exc_info.value.error_code == "llm.no_pricing"
    assert exc_info.value.retriable is False


@pytest.mark.asyncio
async def test_complete_refuses_a_routing_decision_for_a_different_provider() -> None:
    adapter = LocalAdapter(
        client=httpx.AsyncClient(),
        router=_router({"local-fast": "llama3.1:8b"}, provider="anthropic"),
        pricing={"llama3.1:8b": _PRICING},
    )

    with pytest.raises(LLMProviderError, match="does not serve") as exc_info:
        await adapter.complete(_request())

    assert exc_info.value.category == ErrorCategory.PERMANENT
    assert exc_info.value.error_code == "llm.misrouted"
    assert exc_info.value.retriable is False


# --- LocalAdapter.complete(): real network error paths ---------------------


def _unused_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.mark.asyncio
async def test_complete_wraps_a_real_connection_failure() -> None:
    closed_port = _unused_local_port()
    adapter = LocalAdapter(
        client=httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{closed_port}", timeout=_HTTP_TIMEOUT_SECONDS
        ),
        router=_router({"local-fast": "llama3.1:8b"}),
        pricing={"llama3.1:8b": _PRICING},
    )

    with pytest.raises(LLMProviderError, match="could not reach local model server") as exc_info:
        await adapter.complete(_request())

    assert exc_info.value.category == ErrorCategory.TRANSIENT
    assert exc_info.value.error_code == "llm.network"
    assert exc_info.value.retriable is True


class _ServerErrorHandler(http.server.BaseHTTPRequestHandler):
    _body = b'{"error": {"message": "model not found"}}'

    def do_POST(self) -> None:
        self.send_response(500)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self._body)))
        self.end_headers()
        self.wfile.write(self._body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass


@pytest.fixture
def server_error_server() -> Generator[str, None, None]:
    server = http.server.HTTPServer(("127.0.0.1", 0), _ServerErrorHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


@pytest.mark.asyncio
async def test_complete_wraps_a_real_error_response(server_error_server: str) -> None:
    adapter = LocalAdapter(
        client=httpx.AsyncClient(base_url=server_error_server, timeout=_HTTP_TIMEOUT_SECONDS),
        router=_router({"local-fast": "llama3.1:8b"}),
        pricing={"llama3.1:8b": _PRICING},
    )

    with pytest.raises(LLMProviderError, match="HTTP 500") as exc_info:
        await adapter.complete(_request())

    assert exc_info.value.category == ErrorCategory.TRANSIENT
    assert exc_info.value.error_code == "llm.provider_error"
    assert exc_info.value.retriable is True


class _SuccessfulChatCompletionHandler(http.server.BaseHTTPRequestHandler):
    """Serves a real, well-formed OpenAI-compatible chat-completion JSON
    body — exercises ``complete()`` end to end without any real local
    model server."""

    _body = (
        b'{"id":"chatcmpl-1","model":"llama3.1:8b",'
        b'"choices":[{"index":0,"finish_reason":"stop",'
        b'"message":{"role":"assistant","content":"pong"}}],'
        b'"usage":{"prompt_tokens":12,"completion_tokens":3}}'
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
def successful_chat_completion_server() -> Generator[str, None, None]:
    server = http.server.HTTPServer(("127.0.0.1", 0), _SuccessfulChatCompletionHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


@pytest.mark.asyncio
async def test_complete_maps_a_real_successful_response_end_to_end(
    successful_chat_completion_server: str,
) -> None:
    adapter = LocalAdapter(
        client=httpx.AsyncClient(
            base_url=successful_chat_completion_server, timeout=_HTTP_TIMEOUT_SECONDS
        ),
        router=_router({"local-fast": "llama3.1:8b"}),
        pricing={"llama3.1:8b": _PRICING},
    )

    response = await adapter.complete(_request(system="be terse"))

    assert response.content == "pong"
    assert response.provider == "local"
    assert response.model_id == "llama3.1:8b"
    assert response.usage.input_tokens == 12
    assert response.usage.output_tokens == 3
    assert response.usage.latency_ms >= 0


# --- LocalAdapter.complete(): Error Taxonomy classification ---------------


class _StatusErrorHandler(http.server.BaseHTTPRequestHandler):
    """Serves a fixed HTTP status and, optionally, extra headers (e.g.
    ``Retry-After``) — mirrors ``test_anthropic_adapter.py``'s own
    identically-named, identically-shaped handler."""

    status_code = 500
    extra_headers: dict[str, str] = {}
    _body = b'{"error": {"message": "synthetic"}}'

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
        server.server_close()


def _adapter_against(base_url: str) -> LocalAdapter:
    return LocalAdapter(
        client=httpx.AsyncClient(base_url=base_url, timeout=_HTTP_TIMEOUT_SECONDS),
        router=_router({"local-fast": "llama3.1:8b"}),
        pricing={"llama3.1:8b": _PRICING},
    )


@pytest.mark.parametrize(
    ("status_code", "expected_category", "expected_error_code", "expected_retriable"),
    [
        (400, ErrorCategory.PERMANENT, "llm.invalid_request", False),
        (401, ErrorCategory.INFRASTRUCTURE, "llm.auth_failed", False),
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
    with _status_server(429, extra_headers={"retry-after": "3"}) as base_url:
        adapter = _adapter_against(base_url)

        with pytest.raises(LLMProviderError) as exc_info:
            await adapter.complete(_request())

    assert exc_info.value.retry_after_seconds == 3.0


# --- LocalAdapter.embed(): real provider endpoint (§11) -------------------


def _embedding_request(*, inputs: list[str] | None = None) -> EmbeddingRequest:
    return EmbeddingRequest(model_alias="embedding-fast", inputs=inputs or ["hello", "world"])


class _SuccessfulEmbeddingsHandler(http.server.BaseHTTPRequestHandler):
    """Serves a real, well-formed OpenAI-compatible ``/v1/embeddings``
    JSON body — deliberately out of index order, to prove
    ``_map_embedding_response`` sorts by each entry's own ``index``
    rather than trusting array order."""

    _body = (
        b'{"object":"list","model":"nomic-embed-text",'
        b'"data":['
        b'{"object":"embedding","index":1,"embedding":[0.4,0.5,0.6]},'
        b'{"object":"embedding","index":0,"embedding":[0.1,0.2,0.3]}'
        b'],"usage":{"prompt_tokens":7,"total_tokens":7}}'
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
def successful_embeddings_server() -> Generator[str, None, None]:
    server = http.server.HTTPServer(("127.0.0.1", 0), _SuccessfulEmbeddingsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def _embedding_adapter_against(base_url: str) -> LocalAdapter:
    return LocalAdapter(
        client=httpx.AsyncClient(base_url=base_url, timeout=_HTTP_TIMEOUT_SECONDS),
        router=_router({"embedding-fast": "nomic-embed-text"}),
        pricing={"nomic-embed-text": _PRICING},
    )


@pytest.mark.asyncio
async def test_embed_returns_real_vectors_in_the_real_requested_order(
    successful_embeddings_server: str,
) -> None:
    adapter = _embedding_adapter_against(successful_embeddings_server)

    response = await adapter.embed(_embedding_request(inputs=["hello", "world"]))

    # The server (deliberately) returned index 1 before index 0 — a
    # genuine sort-by-index bug here would silently swap these.
    assert response.vectors == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    assert response.model_id == "nomic-embed-text"
    assert response.dimensions == 3
    assert response.usage.input_tokens == 7
    assert response.usage.output_tokens == 0
    assert response.usage.provider == "local"


@pytest.mark.asyncio
async def test_embed_refuses_a_routing_decision_for_a_different_provider() -> None:
    adapter = LocalAdapter(
        client=httpx.AsyncClient(),
        router=_router({"embedding-fast": "nomic-embed-text"}, provider="anthropic"),
        pricing={"nomic-embed-text": _PRICING},
    )

    with pytest.raises(LLMProviderError, match="does not serve") as exc_info:
        await adapter.embed(_embedding_request())

    assert exc_info.value.error_code == "llm.misrouted"


@pytest.mark.asyncio
async def test_embed_wraps_a_real_connection_failure() -> None:
    closed_port = _unused_local_port()
    adapter = LocalAdapter(
        client=httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{closed_port}", timeout=_HTTP_TIMEOUT_SECONDS
        ),
        router=_router({"embedding-fast": "nomic-embed-text"}),
        pricing={"nomic-embed-text": _PRICING},
    )

    with pytest.raises(LLMProviderError, match="could not reach local model server") as exc_info:
        await adapter.embed(_embedding_request())

    assert exc_info.value.category == ErrorCategory.TRANSIENT
    assert exc_info.value.error_code == "llm.network"


@pytest.mark.asyncio
async def test_embed_classifies_a_real_http_error_response() -> None:
    with _status_server(500) as base_url:
        adapter = LocalAdapter(
            client=httpx.AsyncClient(base_url=base_url, timeout=_HTTP_TIMEOUT_SECONDS),
            router=_router({"embedding-fast": "nomic-embed-text"}),
            pricing={"nomic-embed-text": _PRICING},
        )

        with pytest.raises(LLMProviderError) as exc_info:
            await adapter.embed(_embedding_request())

    assert exc_info.value.category == ErrorCategory.TRANSIENT
    assert exc_info.value.error_code == "llm.provider_error"


class _MismatchedCountEmbeddingsHandler(http.server.BaseHTTPRequestHandler):
    """A real, well-formed response that is nonetheless a real provider
    bug: two inputs requested, one vector returned."""

    _body = (
        b'{"object":"list","model":"nomic-embed-text",'
        b'"data":[{"object":"embedding","index":0,"embedding":[0.1,0.2]}],'
        b'"usage":{"prompt_tokens":7,"total_tokens":7}}'
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
def mismatched_count_embeddings_server() -> Generator[str, None, None]:
    server = http.server.HTTPServer(("127.0.0.1", 0), _MismatchedCountEmbeddingsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


@pytest.mark.asyncio
async def test_embed_refuses_a_real_vector_count_mismatch(
    mismatched_count_embeddings_server: str,
) -> None:
    adapter = _embedding_adapter_against(mismatched_count_embeddings_server)

    with pytest.raises(LLMProviderError, match="returned 1 embedding") as exc_info:
        await adapter.embed(_embedding_request(inputs=["hello", "world"]))

    assert exc_info.value.error_code == "llm.provider_error"


# --- build_local_adapter -----------------------------------------------


def test_build_local_adapter_constructs_a_real_adapter() -> None:
    adapter = build_local_adapter(
        base_url="http://127.0.0.1:11434/v1",
        router=_router({"local-fast": "llama3.1:8b"}),
        pricing={"llama3.1:8b": _PRICING},
    )

    assert isinstance(adapter, LocalAdapter)
