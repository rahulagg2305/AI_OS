"""Caching — Redis-backed config/secret/document/retrieval caching
(feature_inventory.md §2.18). Response caching is off by default and
unconditionally disabled for experiments (ADR-0025).

Implemented so far (``P02-S07-M23-T01``): a real Redis client
construction function and settings only (:func:`build_redis_client`,
:class:`RedisSettings`) — no cache read/write logic, no TTL policy, no
response-cache wiring yet (``P02-S07-M23-T02``).
"""

from ai_os_kernel.caching.client import build_redis_client
from ai_os_kernel.caching.settings import RedisSettings

__all__ = ["RedisSettings", "build_redis_client"]
