"""Real proof of :class:`RedisRateLimiter` and its wiring into
:class:`DispatchingLLMGateway` against a real Redis instance (ADR-0015
— no mocking infrastructure): requests within a provider's configured
limit succeed; a request that would exceed it is genuinely refused,
with a real ``retry_after_seconds`` computed from the real window
countdown; the window resetting genuinely allows further requests
again.

Every test uses its own, distinct provider name — the module-scoped
``redis_url`` fixture shares one real Redis instance across every test
in this file, and a fixed-window counter keys its real Redis entry by
``provider`` + the current window bucket, so two tests reusing the same
provider name within the same real-world second would genuinely share
counter state. Distinct names keep each test's own real Redis state
isolated without needing to flush the database between tests.

Same testcontainers-first pattern
``tests/integration/caching/test_redis_client.py`` already establishes
— a single real caller here too, so no shared fixture module is
extracted (ADR-0004).
"""

from __future__ import annotations

import asyncio
from collections.abc import Generator

import docker
import docker.errors
import pytest
from testcontainers.community.redis import RedisContainer

from ai_os_kernel.caching.client import build_redis_client
from ai_os_kernel.llm_gateway.error_taxonomy import RATE_LIMIT_EXCEEDED
from ai_os_kernel.llm_gateway.errors import LLMProviderError
from ai_os_kernel.llm_gateway.gateway import DispatchingLLMGateway, EchoLLMGateway
from ai_os_kernel.llm_gateway.models import LLMRequest, LLMResponse, Message, MessageRole
from ai_os_kernel.llm_gateway.rate_limiter import ProviderRateLimit, RedisRateLimiter
from ai_os_kernel.llm_gateway.router import RoutingDecision, StaticRouter

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


def _request(model_alias: str = "fast-cheap") -> LLMRequest:
    return LLMRequest(
        model_alias=model_alias,
        messages=[Message(role=MessageRole.USER, content="hello")],
        max_output_tokens=16,
    )


async def test_requests_within_the_limit_succeed(redis_url: str) -> None:
    provider = "provider-within-limit"
    limiter = RedisRateLimiter(
        build_redis_client(redis_url),
        limits={provider: ProviderRateLimit(max_requests=3, window_seconds=60.0)},
    )

    first = await limiter.check(provider)
    second = await limiter.check(provider)
    third = await limiter.check(provider)

    assert first.allowed is True
    assert second.allowed is True
    assert third.allowed is True


async def test_a_request_exceeding_the_limit_is_genuinely_refused(redis_url: str) -> None:
    provider = "provider-over-limit"
    limiter = RedisRateLimiter(
        build_redis_client(redis_url),
        limits={provider: ProviderRateLimit(max_requests=2, window_seconds=60.0)},
    )

    await limiter.check(provider)
    await limiter.check(provider)
    third = await limiter.check(provider)

    assert third.allowed is False
    assert third.retry_after_seconds is not None
    assert 0 < third.retry_after_seconds <= 60.0


async def test_a_provider_with_no_configured_limit_is_always_allowed(redis_url: str) -> None:
    limiter = RedisRateLimiter(build_redis_client(redis_url), limits={})

    for _ in range(10):
        result = await limiter.check("unconfigured-provider")
        assert result.allowed is True


async def test_different_providers_have_independent_budgets(redis_url: str) -> None:
    limiter = RedisRateLimiter(
        build_redis_client(redis_url),
        limits={
            "provider-independent-a": ProviderRateLimit(max_requests=1, window_seconds=60.0),
            "provider-independent-b": ProviderRateLimit(max_requests=1, window_seconds=60.0),
        },
    )

    await limiter.check("provider-independent-a")
    a_second = await limiter.check("provider-independent-a")
    b_first = await limiter.check("provider-independent-b")

    assert a_second.allowed is False
    assert b_first.allowed is True


async def test_the_window_resetting_allows_further_requests_again(redis_url: str) -> None:
    provider = "provider-window-reset"
    limiter = RedisRateLimiter(
        build_redis_client(redis_url),
        limits={provider: ProviderRateLimit(max_requests=1, window_seconds=1.0)},
    )

    first = await limiter.check(provider)
    refused = await limiter.check(provider)
    await asyncio.sleep(1.1)
    after_reset = await limiter.check(provider)

    assert first.allowed is True
    assert refused.allowed is False
    assert after_reset.allowed is True


async def test_genuinely_throttled_dispatch_at_the_gateway_level(redis_url: str) -> None:
    """The literal proof this ticket's own Output names: "Throttled
    dispatch" — a real DispatchingLLMGateway, wired with a real
    RedisRateLimiter, genuinely refuses a call once the configured
    provider limit is exhausted, without ever reaching the registered
    LLMGateway's own complete()."""
    provider = "provider-throttled-dispatch"
    calls = 0
    real_echo = EchoLLMGateway()

    class _CountingGateway:
        async def complete(self, request: LLMRequest) -> LLMResponse:
            nonlocal calls
            calls += 1
            return await real_echo.complete(request)

    router = StaticRouter(
        routes={"fast-cheap": RoutingDecision(provider=provider, model_id="claude-x")}
    )
    limiter = RedisRateLimiter(
        build_redis_client(redis_url),
        limits={provider: ProviderRateLimit(max_requests=2, window_seconds=60.0)},
    )
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={provider: _CountingGateway()},
        rate_limiter=limiter,
    )

    await dispatcher.complete(_request())
    await dispatcher.complete(_request())
    assert calls == 2

    with pytest.raises(LLMProviderError) as excinfo:
        await dispatcher.complete(_request())

    assert calls == 2  # the third, refused call never reached the real gateway
    assert excinfo.value.error_code == RATE_LIMIT_EXCEEDED.error_code
    assert excinfo.value.retriable is True
    assert excinfo.value.retry_after_seconds is not None
