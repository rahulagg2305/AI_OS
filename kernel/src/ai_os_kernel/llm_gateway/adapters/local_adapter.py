"""The second real :class:`~ai_os_kernel.llm_gateway.gateway.LLMGateway`
implementation — a self-hosted/local model server, behind the same
Protocol :class:`~ai_os_kernel.llm_gateway.adapters.anthropic_adapter.
AnthropicAdapter` already implements (llm_gateway.md §3's own internal
component diagram names this module ``local_adapter`` explicitly,
alongside ``anthropic_adapter`` and an unspecified ``<other provider
adapters>`` placeholder — the only two *named* adapters in that
diagram).

No official first-party SDK exists for a self-hosted model server the
way ``anthropic`` does for Anthropic, so this adapter speaks the
OpenAI-compatible ``/v1/chat/completions`` HTTP contract that
self-hosted servers (Ollama, vLLM, llama.cpp's server, LM Studio, ...)
already converge on — a real, already-standard wire protocol, not one
invented for this step. ``httpx`` (already a transitive dependency via
``anthropic``, not a new one) is used directly rather than a "provider
SDK", since llm_gateway.md §3's "the ONLY place a provider SDK is
imported" rule is about vendor SDKs, and a local server has none.

This is one more adapter behind the Gateway's one seam, not a Gateway
redesign — the identical scope fence :mod:`anthropic_adapter` already
documents applies here unchanged: no Request Validator, Capability
Negotiator, Policy & Budget Enforcer, Prompt Cache Planner, or Rate
Limiter. Alias resolution is the same injected
:class:`~ai_os_kernel.llm_gateway.router.Router` every other adapter
uses. ``httpx.AsyncClient`` performs no retries of its own (unlike the
``anthropic`` SDK's ``max_retries`` default) — that is an honest
difference in what "no additional retry logic" means for this
provider, not a gap this step fills; the Gateway's own Retry &
Fallback Manager (:class:`~ai_os_kernel.llm_gateway.gateway.
DispatchingLLMGateway`) is a second, provider-agnostic layer on top,
driven by classifying every failure this adapter raises via
:mod:`~ai_os_kernel.llm_gateway.error_taxonomy` exactly as
``anthropic_adapter`` does.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

import httpx

from ai_os_kernel.llm_gateway.adapters.model_config import ModelPricing
from ai_os_kernel.llm_gateway.error_taxonomy import (
    CAPABILITY_UNSUPPORTED,
    MISROUTED,
    NETWORK_FAILURE,
    NO_PRICING,
    UNPARSEABLE_RESPONSE,
    classify_http_status,
    parse_retry_after_seconds,
)
from ai_os_kernel.llm_gateway.errors import LLMProviderError
from ai_os_kernel.llm_gateway.models import LLMRequest, LLMResponse, StopReason, UsageRecord
from ai_os_kernel.llm_gateway.router import Router

# Public for the identical reason anthropic_adapter.PROVIDER_NAME is:
# the composition root needs this exact string once, not a second copy
# of it, when it decides which alias routes to this adapter.
PROVIDER_NAME = "local"

# The OpenAI-compatible ``finish_reason`` values every self-hosted
# server in this protocol family returns, mapped onto this reduced
# contract's own two-value StopReason — the identical reduction
# anthropic_adapter._STOP_REASON_MAP already applies to Anthropic's own
# richer set.
_FINISH_REASON_MAP: dict[str, StopReason] = {
    "stop": StopReason.END_TURN,
    "length": StopReason.MAX_TOKENS,
}


class LocalAdapter:
    """Calls a self-hosted, OpenAI-compatible chat completions endpoint
    via an already-constructed ``httpx.AsyncClient`` (its ``base_url``
    already pointed at the local server — see :func:`build_local_adapter`).

    Constructor-injected ``router``/``pricing``, the identical shape
    :class:`~ai_os_kernel.llm_gateway.adapters.anthropic_adapter.AnthropicAdapter`
    already uses, for the same reason: the composition root decides
    which :class:`~ai_os_kernel.llm_gateway.router.Router` and which
    pricing table back this adapter, not this class itself.
    """

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        router: Router,
        pricing: Mapping[str, ModelPricing],
    ) -> None:
        self._client = client
        self._router = router
        self._pricing = dict(pricing)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        decision = self._router.resolve(request.model_alias)
        if decision.provider != PROVIDER_NAME:
            # The identical "refuse clearly, do not route around it"
            # rule anthropic_adapter.AnthropicAdapter.complete already
            # applies for its own provider name.
            raise LLMProviderError(
                f"model_alias {request.model_alias!r} routes to provider "
                f"{decision.provider!r}, which this adapter does not serve "
                f"(it only calls {PROVIDER_NAME!r})",
                category=MISROUTED.category,
                error_code=MISROUTED.error_code,
                retriable=MISROUTED.retriable,
            )
        model_id = decision.model_id

        pricing = self._pricing.get(model_id)
        if pricing is None:
            raise LLMProviderError(
                f"model id {model_id!r} (alias {request.model_alias!r}) has no configured "
                "pricing — cost_usd cannot be honestly computed for a real call",
                category=NO_PRICING.category,
                error_code=NO_PRICING.error_code,
                retriable=NO_PRICING.retriable,
            )

        messages: list[dict[str, str]] = []
        if request.system is not None:
            messages.append({"role": "system", "content": request.system})
        messages.extend(
            {"role": message.role.value, "content": message.content} for message in request.messages
        )
        payload = {
            "model": model_id,
            "messages": messages,
            "max_tokens": request.max_output_tokens,
        }

        started = time.monotonic()
        try:
            http_response = await self._client.post("/chat/completions", json=payload)
            http_response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            classification = classify_http_status(exc.response.status_code)
            retry_after_seconds = parse_retry_after_seconds(exc.response.headers.get("retry-after"))
            raise LLMProviderError(
                f"local model server returned HTTP {exc.response.status_code} for "
                f"model_alias {request.model_alias!r}: {exc.response.text}",
                category=classification.category,
                error_code=classification.error_code,
                retriable=classification.retriable,
                retry_after_seconds=retry_after_seconds,
            ) from exc
        except httpx.TransportError as exc:
            raise LLMProviderError(
                f"could not reach local model server for model_alias "
                f"{request.model_alias!r}: {exc}",
                category=NETWORK_FAILURE.category,
                error_code=NETWORK_FAILURE.error_code,
                retriable=NETWORK_FAILURE.retriable,
            ) from exc
        latency_ms = int((time.monotonic() - started) * 1000)

        return _map_response(http_response.json(), latency_ms=latency_ms, pricing=pricing)


def _map_response(payload: Any, *, latency_ms: int, pricing: ModelPricing) -> LLMResponse:
    """Pure, synchronous mapping from a real OpenAI-compatible chat
    completion JSON body to this platform's reduced :class:`LLMResponse`
    — the identical "map the real wire shape, no I/O" role
    ``anthropic_adapter._map_response`` already plays for Anthropic's
    own SDK response objects.

    ``payload`` is untyped ``Any``: there is no SDK class to type it
    against (see this module's docstring for why), so it is treated as
    boundary data exactly the way llm_gateway.md §5's own ``raw: object
    | None`` already treats a raw provider response — read defensively,
    never trusted structurally.
    """

    try:
        choice = payload["choices"][0]
        finish_reason = choice["finish_reason"]
        content = choice["message"]["content"] or ""
        model_id = payload["model"]
        usage = payload.get("usage") or {}
        input_tokens = int(usage.get("prompt_tokens", 0))
        output_tokens = int(usage.get("completion_tokens", 0))
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMProviderError(
            f"local model server returned a response this adapter could not parse: {exc}",
            category=UNPARSEABLE_RESPONSE.category,
            error_code=UNPARSEABLE_RESPONSE.error_code,
            retriable=UNPARSEABLE_RESPONSE.retriable,
        ) from exc

    stop_reason = _FINISH_REASON_MAP.get(finish_reason)
    if stop_reason is None:
        raise LLMProviderError(
            f"local model server returned finish_reason={finish_reason!r}, which this "
            "reduced contract does not represent (no tools, thinking, or stop sequences "
            "are declared, so anything but 'stop'/'length' should not be reachable)",
            category=CAPABILITY_UNSUPPORTED.category,
            error_code=CAPABILITY_UNSUPPORTED.error_code,
            retriable=CAPABILITY_UNSUPPORTED.retriable,
        )

    cost_usd = (
        Decimal(input_tokens) * pricing.input_per_million_usd
        + Decimal(output_tokens) * pricing.output_per_million_usd
    ) / Decimal(1_000_000)

    return LLMResponse(
        content=content,
        stop_reason=stop_reason,
        usage=UsageRecord(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=0,
            cache_write_tokens=0,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            provider=PROVIDER_NAME,
            model_id=model_id,
            retries=0,
            fallback_used=False,
        ),
        provider=PROVIDER_NAME,
        model_id=model_id,
        # OpenAI-compatible servers echo back the model id they actually
        # served in the same "model" field — there is no further,
        # honestly-distinct version component this protocol exposes,
        # the identical situation anthropic_adapter._map_response's own
        # model_version comment already describes for Anthropic's ids.
        model_version=model_id,
    )


def build_local_adapter(
    *,
    base_url: str,
    router: Router,
    pricing: Mapping[str, ModelPricing],
) -> LocalAdapter:
    """Constructs the ``httpx.AsyncClient`` pointed at ``base_url`` (the
    local server's OpenAI-compatible root, e.g.
    ``http://127.0.0.1:11434/v1``) and the real :class:`LocalAdapter`.

    Deliberately synchronous, unlike
    :func:`~ai_os_kernel.llm_gateway.adapters.anthropic_adapter.build_anthropic_adapter`:
    that function ``await``s a real Secrets Resolution call before it
    can construct its client; this one has no secret to resolve (a
    self-hosted server the composition root already trusts by
    ``base_url`` alone) and performs no I/O of its own, so an ``async``
    signature here would only pretend a real await exists.
    ``base_url`` is a plain configuration value, not a
    :mod:`~ai_os_kernel.secrets_manager` reference — it identifies a
    network location, not a credential.
    """

    client = httpx.AsyncClient(base_url=base_url)
    return LocalAdapter(client=client, router=router, pricing=pricing)
