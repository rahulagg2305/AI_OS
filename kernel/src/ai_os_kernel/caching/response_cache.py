"""The Response Cache (ADR-0025 §3, ``P02-S07-M23-T02``): identical
request → stored response, no model call. Off by default (nothing in
a real Kernel composition calls this yet — wiring it into
``llm_gateway.gateway``'s real call path is real, disclosed follow-up
work, mirroring this codebase's own repeated "proven, real, unwired"
precedent for the ``decision``/``parallel``/``sub_workflow`` step
types before they reached a real composition) and **unconditionally
disabled for any call belonging to an experiment**, enforced
structurally here — never left to configuration discipline, per
ADR-0025 §3's own explicit reasoning ("a silently cached response is
the single easiest way to produce benchmarking numbers that look
excellent and mean nothing").

Reuses the real Redis client just built (``P02-S07-M23-T01``) — no
parallel cache mechanism. ``LLMRequest.metadata.experiment_id`` and
``LLMResponse.served_from_cache`` were added in this same step (a real,
disclosed structural gap: ADR-0025's experiment rule had no field to
check) — see ``llm_gateway/models.py``'s own docstring for the full
reasoning.
"""

from __future__ import annotations

import hashlib
import json

from ai_os_kernel.caching.cache import Cache
from ai_os_kernel.llm_gateway.models import LLMRequest, LLMResponse
from ai_os_kernel.observability.logging import get_logger

_logger = get_logger(__name__)

_KEY_PREFIX = "aios:response_cache:"
# ADR-0025 §3 documents this cache as "available for local development
# and for retrying an interrupted run" -- unlike §1's platform caches,
# it names no specific TTL. One real day is long enough to survive a
# retried run without being effectively permanent; this codebase's own
# "named constant, disclosed as a first-cut default" convention
# (coding_standards.md), not a second policy decision.
RESPONSE_CACHE_TTL_SECONDS = 86_400


def _cache_key(request: LLMRequest) -> str:
    """Every input that affects the result, per ADR-0025 §1: "Cache
    keys include every input that affects the result... A key that
    omits an input is a correctness bug." Deliberately excludes
    ``metadata`` (``workflow_id``/``step_id``/``experiment_id``): none
    of those change what the model would return for an otherwise
    identical request — including them would make two calls that
    should hit the same cached response miss each other instead."""
    canonical = {
        "model_alias": request.model_alias,
        "messages": [
            {"role": message.role.value, "content": message.content} for message in request.messages
        ],
        "system": request.system,
        "max_output_tokens": request.max_output_tokens,
    }
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode("utf-8")).hexdigest()
    return f"{_KEY_PREFIX}{digest}"


def _is_experiment_call(request: LLMRequest) -> bool:
    return request.metadata is not None and request.metadata.experiment_id is not None


class ResponseCache:
    """Backend-agnostic cache over real ``LLMRequest`` → ``LLMResponse``
    calls. Adds no HTTP/model logic of its own — purely a real,
    structured-logging wrapper over the injected `Cache`, the identical
    "thin wrapper over an existing primitive" shape this codebase's own
    background-loop components already establish."""

    def __init__(self, cache: Cache) -> None:
        """Takes the `Cache` Protocol, not a `Redis` (`P02-S07-M23-T03`).

        This class was bound directly to a real Redis client, so every
        test touching it needed a real container — the reason nothing
        outside this package ever exercised caching. `RedisCache` is the
        production implementation; `InMemoryCache` is the real fake
        ADR-0004 asks for at this seam.
        """
        self._cache = cache

    async def get(self, request: LLMRequest) -> LLMResponse | None:
        """A real cache hit or miss, recorded via structured logging.

        Always a miss — without ever touching Redis — when ``request``
        belongs to an experiment (ADR-0025 §3's hard rule)."""
        if _is_experiment_call(request):
            _logger.debug(
                "response_cache.bypassed_for_experiment",
                experiment_id=request.metadata.experiment_id if request.metadata else None,
            )
            return None

        key = _cache_key(request)
        raw = await self._cache.get(key)
        if raw is None:
            _logger.info("response_cache.miss", key=key)
            return None

        _logger.info("response_cache.hit", key=key)
        response = LLMResponse.model_validate_json(raw)
        return response.model_copy(update={"served_from_cache": True})

    async def set(self, request: LLMRequest, response: LLMResponse) -> None:
        """Stores ``response`` under ``request``'s real cache key — a
        no-op, never touching Redis, when ``request`` belongs to an
        experiment (the identical structural gate :meth:`get` applies,
        so an experiment call can never even populate the cache for a
        later non-experiment call to accidentally hit)."""
        if _is_experiment_call(request):
            return

        key = _cache_key(request)
        await self._cache.set(
            key, response.model_dump_json().encode(), ttl_seconds=RESPONSE_CACHE_TTL_SECONDS
        )
