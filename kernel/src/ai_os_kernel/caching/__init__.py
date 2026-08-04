"""Caching — Redis-backed config/secret/document/retrieval caching
(feature_inventory.md §2.18). Response caching is off by default and
unconditionally disabled for experiments (ADR-0025).

Implemented so far: a real Redis client construction function and
settings (:func:`build_redis_client`, :class:`RedisSettings`,
``P02-S07-M23-T01``), and the Response Cache
(:class:`ResponseCache`, ``P02-S07-M23-T02``) — real ``LLMRequest`` →
``LLMResponse`` caching, ADR-0025 §3's experiment-exclusion rule
enforced structurally. Not yet wired into ``llm_gateway.gateway``'s
real call path; no config/secret/document/retrieval caching exists.
"""

from ai_os_kernel.caching.client import build_redis_client
from ai_os_kernel.caching.response_cache import RESPONSE_CACHE_TTL_SECONDS, ResponseCache
from ai_os_kernel.caching.settings import RedisSettings

__all__ = [
    "RESPONSE_CACHE_TTL_SECONDS",
    "RedisSettings",
    "ResponseCache",
    "build_redis_client",
]
