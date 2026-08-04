"""Real proof of :class:`ResponseCache` against a real Redis instance
(ADR-0015 — no mocking infrastructure): a genuine cache hit avoids a
real recomputation, a cache miss falls through correctly, and
ADR-0025 §3's "unconditionally disabled for experiments" rule
genuinely holds — an experiment call is never served from cache and
never even writes to Redis.

Same testcontainers-first pattern
``tests/integration/caching/test_redis_client.py`` already establishes
for this package — a single real caller here too, so no shared
fixture module is extracted (ADR-0004).
"""

from __future__ import annotations

from collections.abc import Generator
from decimal import Decimal

import docker
import docker.errors
import pytest
from testcontainers.community.redis import RedisContainer

from ai_os_kernel.caching.client import build_redis_client
from ai_os_kernel.caching.response_cache import ResponseCache
from ai_os_kernel.llm_gateway.models import (
    LLMRequest,
    LLMResponse,
    Message,
    MessageRole,
    StopReason,
    TraceContext,
    UsageRecord,
)

_IMAGE = "redis:7-alpine"


@pytest.fixture(scope="module")
def redis_url() -> Generator[str, None, None]:
    try:
        docker.from_env().ping()
    except (docker.errors.DockerException, OSError) as exc:
        pytest.skip(f"Docker daemon is not reachable — this live-container suite is opt-in: {exc}")

    with RedisContainer(_IMAGE) as container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(container.port)
        yield f"redis://{host}:{port}/0"


@pytest.fixture
def cache(redis_url: str) -> ResponseCache:
    return ResponseCache(build_redis_client(redis_url))


def _request(*, experiment_id: str | None = None, content: str = "hello") -> LLMRequest:
    metadata = TraceContext(experiment_id=experiment_id) if experiment_id is not None else None
    return LLMRequest(
        model_alias="fast-cheap",
        messages=[Message(role=MessageRole.USER, content=content)],
        max_output_tokens=100,
        metadata=metadata,
    )


def _response(content: str = "a real computed answer") -> LLMResponse:
    return LLMResponse(
        content=content,
        stop_reason=StopReason.END_TURN,
        usage=UsageRecord(
            input_tokens=10,
            output_tokens=5,
            cache_read_tokens=0,
            cache_write_tokens=0,
            cost_usd=Decimal("0.01"),
            latency_ms=250,
            provider="anthropic",
            model_id="claude-x",
            retries=0,
            fallback_used=False,
        ),
        provider="anthropic",
        model_id="claude-x",
        model_version="1",
    )


async def test_a_cache_miss_falls_through_and_a_subsequent_call_avoids_recomputation(
    cache: ResponseCache,
) -> None:
    request = _request()
    computed = _response()
    real_calls = 0

    async def compute() -> LLMResponse:
        nonlocal real_calls
        real_calls += 1
        return computed

    async def call_with_cache(req: LLMRequest) -> LLMResponse:
        cached = await cache.get(req)
        if cached is not None:
            return cached
        response = await compute()
        await cache.set(req, response)
        return response

    first = await call_with_cache(request)
    second = await call_with_cache(request)

    assert real_calls == 1
    assert first.served_from_cache is False
    assert second.content == computed.content
    assert second.served_from_cache is True


async def test_a_cache_miss_returns_none_and_writes_nothing_until_set_is_called(
    cache: ResponseCache,
) -> None:
    request = _request(content="never seen before")

    assert await cache.get(request) is None


async def test_two_different_requests_do_not_collide_in_the_cache(cache: ResponseCache) -> None:
    request_a = _request(content="request A")
    request_b = _request(content="request B")
    response_a = _response(content="answer A")

    await cache.set(request_a, response_a)

    assert (await cache.get(request_a)) is not None
    assert await cache.get(request_b) is None


async def test_an_experiment_call_is_never_served_from_cache_even_after_a_matching_set(
    cache: ResponseCache,
) -> None:
    plain_request = _request(content="shared content")
    experiment_request = _request(content="shared content", experiment_id="exp-1")

    await cache.set(plain_request, _response())
    assert await cache.get(plain_request) is not None

    assert await cache.get(experiment_request) is None


async def test_an_experiment_call_never_writes_to_the_cache_at_all(cache: ResponseCache) -> None:
    experiment_request = _request(content="only ever seen in an experiment", experiment_id="exp-2")

    await cache.set(experiment_request, _response())

    non_experiment_request = _request(content="only ever seen in an experiment")
    assert await cache.get(non_experiment_request) is None
