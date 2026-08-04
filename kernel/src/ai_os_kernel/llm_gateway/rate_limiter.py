"""The Rate Limiter (llm_gateway.md §3/§9, ``P02-S02-M06-T11``): a
real, proactive, per-provider request-volume gate — "respect
per-provider rate limits proactively" (this ticket's own Goal),
distinct from and complementary to
:func:`~ai_os_kernel.llm_gateway.error_taxonomy.classify_http_status`'s
existing, *reactive* ``llm.rate_limited`` classification (a provider's
own real ``429`` response, discovered only after a call was already
attempted).

Reuses the real Redis client already built
(:func:`~ai_os_kernel.caching.client.build_redis_client`) — no parallel
mechanism. A fixed-window counter (``INCR`` + ``EXPIRE``): the
simplest real distributed rate-limiting primitive a single atomic
Redis command supports correctly under concurrent access from multiple
Kernel processes sharing the same provider budget (ADR-0020: multiple
API/worker replicas) — no Lua script needed, since ``INCR`` is already
atomic and the only race (two concurrent first-requests both issuing
``EXPIRE``) is harmless: both set the identical, correct TTL.

``Protocol`` + one real implementation
(:class:`RedisRateLimiter`), mirroring
:class:`~ai_os_kernel.llm_gateway.circuit_breaker.CircuitBreaker`/
:class:`~ai_os_kernel.llm_gateway.circuit_breaker.InMemoryCircuitBreaker`'s
own "``Protocol`` justified, a real fake substitutes in tests that
don't need real Redis" shape (ADR-0004).

Real per-provider limit *values* are not decided here, and not
invented: :class:`ProviderRateLimit` is caller-supplied configuration,
never a literal inside this module. Wiring a real
:class:`RedisRateLimiter` into the real composition root
(``kernel/bootstrap.py``) — which would mean deciding real per-provider
numbers and adding real Redis construction to Kernel startup, neither
of which this ticket's own Input/Output ("Request volume" /
"Throttled dispatch") requires — is real, disclosed follow-up work,
not done here.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import NamedTuple, Protocol

from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis


class ProviderRateLimit(BaseModel):
    """A real, caller-supplied ceiling for one provider — never
    hardcoded inside this module; whoever constructs a
    :class:`RedisRateLimiter` decides the real numbers."""

    model_config = ConfigDict(frozen=True)

    max_requests: int = Field(gt=0)
    window_seconds: float = Field(gt=0)


class RateLimitResult(NamedTuple):
    """Whether a real request for ``provider`` may proceed right now,
    and — only when it may not — how long until the next window makes
    it possible again. Honoured exactly like a real provider's own
    ``Retry-After`` hint: passed as
    ``LLMProviderError.retry_after_seconds``, the identical mechanism
    :class:`~ai_os_kernel.llm_gateway.backoff.BackoffPolicy` already
    consults."""

    allowed: bool
    retry_after_seconds: float | None = None


class RateLimiter(Protocol):
    """Per-provider proactive rate gate the Retry & Fallback Manager
    consults before attempting a real call — the seam a cluster-shared
    or per-principal-scoped implementation substitutes later
    (ADR-0004)."""

    async def check(self, provider: str) -> RateLimitResult: ...


class RedisRateLimiter:
    """The one real implementation: a fixed-window counter per
    provider, held in Redis so every Kernel process sharing the same
    Redis instance shares the same real budget for a provider — unlike
    :class:`~ai_os_kernel.llm_gateway.circuit_breaker.InMemoryCircuitBreaker`'s
    deliberate per-process scope, a rate limit is meaningless if each
    process enforces its own independent count against one shared
    provider quota.

    A provider absent from ``limits`` is always allowed — no configured
    ceiling means unbounded, the identical "absent means no limit"
    shape
    :class:`~ai_os_kernel.llm_gateway.budget_enforcer.PerScopeBudgetEnforcer`
    already establishes for a scope it has never seen.
    """

    def __init__(self, client: Redis, *, limits: Mapping[str, ProviderRateLimit]) -> None:
        self._client = client
        self._limits = dict(limits)

    async def check(self, provider: str) -> RateLimitResult:
        limit = self._limits.get(provider)
        if limit is None:
            return RateLimitResult(allowed=True)

        now = time.time()
        window_start = int(now // limit.window_seconds)
        key = f"aios:rate_limit:{provider}:{window_start}"

        count = await self._client.incr(key)
        if count == 1:
            # First real request to land in this window — set a TTL
            # just past the window so the key expires on its own; no
            # separate cleanup job needed.
            await self._client.expire(key, int(limit.window_seconds) + 1)

        if count <= limit.max_requests:
            return RateLimitResult(allowed=True)

        seconds_into_window = now - (window_start * limit.window_seconds)
        retry_after_seconds = limit.window_seconds - seconds_into_window
        return RateLimitResult(allowed=False, retry_after_seconds=retry_after_seconds)
