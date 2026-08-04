"""Redis client construction (``P02-S07-M23-T01``).

Real ``redis.asyncio`` client, mirroring
:func:`~ai_os_kernel.persistence.engine.build_engine`'s own "one
function, build the real client from a URL" shape. The smallest real,
working connection layer this ticket's own Goal/Output calls for
("Actually use the Redis that Compose already provisions" /
"A working client") — cache read/write policy, TTLs, and ADR-0025's
"disabled for experiments" rule are ``P02-S07-M23-T02``'s own scope,
not this one's.
"""

from __future__ import annotations

import redis.asyncio as redis


def build_redis_client(redis_url: str) -> redis.Redis:
    """Build the single Redis client for one Kernel process.

    ``decode_responses=True`` so callers get ``str``, not ``bytes`` —
    every documented use case (feature_inventory.md §2.18:
    config/secret/document/retrieval caching, response caching) is
    text/JSON, not raw binary.
    """
    # redis-py ships `py.typed`, but `Redis.from_url`'s own real
    # signature has no return annotation and untyped `**kwargs` -- a
    # genuine, narrow gap in an otherwise-typed library, not a
    # missing-stub problem `ignore_missing_imports` (this codebase's
    # own `docker.*` precedent) would address.
    client: redis.Redis = redis.from_url(  # type: ignore[no-untyped-call]
        redis_url, decode_responses=True
    )
    return client
