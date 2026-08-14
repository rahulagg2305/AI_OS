"""`InMemoryCache` (`P02-S07-M23-T03`) — the real fake ADR-0004 asks for
at this seam, and the reason `ResponseCache` can now be exercised
without a Redis container.

A fake that ignored TTL would let tests pass against behaviour Redis
would never produce, so TTL expiry is asserted directly rather than
assumed.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from ai_os_kernel.caching.cache import Cache, InMemoryCache
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


def _seam(cache: InMemoryCache) -> Cache:
    """Proves at type-check time that `InMemoryCache` really does
    satisfy the Protocol — the whole point of the seam."""
    return cache


@pytest.mark.asyncio
async def test_a_stored_value_is_returned_verbatim() -> None:
    cache = InMemoryCache()
    await _seam(cache).set("k", b"real-bytes", ttl_seconds=60)

    assert await cache.get("k") == b"real-bytes"


@pytest.mark.asyncio
async def test_an_absent_key_is_a_miss_not_an_error() -> None:
    assert await InMemoryCache().get("never-written") is None


@pytest.mark.asyncio
async def test_ttl_is_genuinely_honoured(monkeypatch: pytest.MonkeyPatch) -> None:
    """The assertion that stops this being a dict with extra steps.

    The monotonic clock is advanced rather than slept on: a real sleep
    would make this test slow and timing-sensitive, which is exactly the
    R-015 family of defect this codebase has already hit five times.
    """
    clock = {"now": 1_000.0}
    monkeypatch.setattr("ai_os_kernel.caching.cache.time.monotonic", lambda: clock["now"])

    cache = InMemoryCache()
    await cache.set("k", b"v", ttl_seconds=30)
    assert await cache.get("k") == b"v"

    clock["now"] += 29.0
    assert await cache.get("k") == b"v", "expired a full second early"

    clock["now"] += 2.0
    assert await cache.get("k") is None, "served an entry past its TTL"


@pytest.mark.asyncio
async def test_delete_invalidates_explicitly() -> None:
    """§2 of `caching_strategy.md` requires explicit invalidation — the
    reason `delete` is on the Protocol at all."""
    cache = InMemoryCache()
    await cache.set("k", b"v", ttl_seconds=3600)

    await cache.delete("k")

    assert await cache.get("k") is None


@pytest.mark.asyncio
async def test_deleting_an_absent_key_is_not_an_error() -> None:
    """`delete` expresses "ensure this is not cached"; a caller
    invalidating something never cached has already got what it asked
    for."""
    await InMemoryCache().delete("never-written")


@pytest.mark.asyncio
async def test_a_rewrite_replaces_both_the_value_and_its_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = {"now": 500.0}
    monkeypatch.setattr("ai_os_kernel.caching.cache.time.monotonic", lambda: clock["now"])

    cache = InMemoryCache()
    await cache.set("k", b"first", ttl_seconds=10)
    clock["now"] += 9.0
    await cache.set("k", b"second", ttl_seconds=10)

    clock["now"] += 5.0
    assert await cache.get("k") == b"second", "the rewrite did not extend the deadline"


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


@pytest.mark.asyncio
async def test_response_cache_round_trips_with_no_redis_at_all() -> None:
    """The reason this ticket exists, demonstrated directly.

    `ResponseCache` previously required a real Redis container to
    exercise at all — which is why nothing outside its own package ever
    tested against it, and why wiring it into the LLM Gateway (`T04`)
    would have dragged Redis into every model-call test. This is that
    same real class, round-tripping a real response, in a plain unit
    test.
    """
    cache = ResponseCache(InMemoryCache())
    request = _request()

    assert await cache.get(request) is None

    await cache.set(request, _response())
    hit = await cache.get(request)

    assert hit is not None
    assert hit.content == "a real computed answer"
    # The real hit marker, not a plain echo of what was stored.
    assert hit.served_from_cache is True


@pytest.mark.asyncio
async def test_an_experiment_call_is_still_never_cached_through_this_seam() -> None:
    """ADR-0025 §3's exclusion rule is structural, so swapping the
    backend must not create a way around it."""
    cache = ResponseCache(InMemoryCache())
    request = _request(experiment_id="exp-1")

    await cache.set(request, _response())

    assert await cache.get(request) is None
