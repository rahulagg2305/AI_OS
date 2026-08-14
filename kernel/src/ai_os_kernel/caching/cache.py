"""The `Cache` Protocol `caching_strategy.md` §1 describes, plus the
in-memory implementation that makes it a real substitution seam
(`P02-S07-M23-T03`).

**What was missing.** This package had exactly one concrete class,
`ResponseCache`, bound directly to a real `Redis` client — no Protocol
and no second implementation. Every cache call therefore required a real
Redis container, which is a large part of why nothing outside this
package's own tests ever exercised caching at all.

**Why the in-memory adapter is the point, not a bonus.** ADR-0004 asks
for interface-driven design with real fakes substituted at the seam. The
next ticket wires `ResponseCache` into the LLM Gateway's real call path;
without an in-memory `Cache`, that would force Redis into every test
that touches a model call. This is what makes that wiring testable.

**The three operations are grounded, not invented.** `caching_strategy.md`
declines to fix a signature ("concrete cache implementations, key
designs, TTLs, and invalidation mechanisms will be refined during
implementation"), so `get`/`set` come from what `ResponseCache` genuinely
uses against Redis today, and `delete` from §2's own explicit
requirement to "support explicit invalidation" — a cache with no
invalidation would not satisfy the document it implements.
"""

from __future__ import annotations

import time
from typing import Protocol

from redis.asyncio import Redis


class Cache(Protocol):
    """A byte-level cache backend.

    Deliberately typed in ``bytes``, not in domain objects: serialisation
    belongs to the caller that knows the shape (``ResponseCache`` already
    round-trips ``LLMResponse`` through Pydantic JSON), and a backend
    that understood domain types could not be reused for the
    configuration, document and retrieval caches §3 also calls for.
    """

    async def get(self, key: str) -> bytes | None: ...

    async def set(self, key: str, value: bytes, *, ttl_seconds: int) -> None: ...

    async def delete(self, key: str) -> None: ...


class InMemoryCache:
    """A real, process-local `Cache` — the substitution seam ADR-0004
    asks for, not a mock.

    **TTL is genuinely honoured**, using a monotonic clock rather than
    wall time so a system clock adjustment cannot resurrect an expired
    entry or expire a live one. A fake that ignored TTL would let a test
    pass against behaviour Redis would never produce, which is precisely
    the failure mode a real fake exists to avoid.

    Expiry is evaluated lazily on read. There is no eviction and no size
    bound, which is correct for its intended scope — tests and
    single-process use — and is stated here rather than discovered
    later: this is not a production cache backend.
    """

    def __init__(self) -> None:
        self._entries: dict[str, tuple[bytes, float]] = {}

    async def get(self, key: str) -> bytes | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.monotonic() >= expires_at:
            # Drop it on read rather than serve it: an expired entry is
            # indistinguishable from a miss to every caller, and leaving
            # it would make `delete` and expiry behave differently.
            del self._entries[key]
            return None
        return value

    async def set(self, key: str, value: bytes, *, ttl_seconds: int) -> None:
        self._entries[key] = (value, time.monotonic() + ttl_seconds)

    async def delete(self, key: str) -> None:
        # Absent keys are not an error: `delete` expresses "ensure this
        # is not cached", and a caller invalidating something that was
        # never cached has already got what it asked for.
        self._entries.pop(key, None)


class RedisCache:
    """The production `Cache`: a thin adapter over the real Redis client
    `build_redis_client` already returns.

    An adapter rather than relying on structural typing against `Redis`
    directly, for a concrete reason: `Redis.set` takes its expiry as
    ``ex`` and its key as ``name``, so a `Redis` does **not** satisfy
    this Protocol's own keyword names. Naming the translation here keeps
    the Protocol expressed in this codebase's vocabulary instead of
    redis-py's, and leaves exactly one place to change if the client
    ever does.
    """

    def __init__(self, client: Redis) -> None:
        self._client = client

    async def get(self, key: str) -> bytes | None:
        raw = await self._client.get(key)
        if raw is None:
            return None
        # redis-py returns `str` when the client was built with
        # `decode_responses=True` and `bytes` otherwise; normalise so
        # every `Cache` implementation genuinely agrees on its contract.
        return raw.encode() if isinstance(raw, str) else bytes(raw)

    async def set(self, key: str, value: bytes, *, ttl_seconds: int) -> None:
        await self._client.set(key, value, ex=ttl_seconds)

    async def delete(self, key: str) -> None:
        await self._client.delete(key)
