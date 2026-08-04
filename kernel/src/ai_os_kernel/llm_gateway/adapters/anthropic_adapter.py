"""The first real :class:`~ai_os_kernel.llm_gateway.gateway.LLMGateway`
implementation — Anthropic, behind the same Protocol
:class:`~ai_os_kernel.llm_gateway.gateway.EchoLLMGateway` already
implements (llm_gateway.md §3: "Provider Adapters — the ONLY place a
provider SDK is imported"; the naming table in the Coding Standards
gives ``AnthropicAdapter`` as its own worked example of an
implementation name).

This is one adapter behind the Gateway's one seam, not a Gateway
redesign: no Request Validator, Capability Negotiator, Policy & Budget
Enforcer, Prompt Cache Planner, or Rate Limiter — those are the
Gateway's remaining documented internal subsystems (§3), still out of
scope. Alias
resolution is the real :class:`~ai_os_kernel.llm_gateway.router.Router`
(injected, not a flat dict this module owns itself). The SDK's own
``max_retries`` (default 2) is the only *SDK-level* retry behaviour
present; the Gateway's own Retry & Fallback Manager
(:class:`~ai_os_kernel.llm_gateway.gateway.DispatchingLLMGateway`) adds
a second, provider-agnostic retry/fallback/circuit-breaking layer on
top, driven by classifying every failure this adapter raises via
:mod:`~ai_os_kernel.llm_gateway.error_taxonomy` — every ``raise
LLMProviderError(...)`` below carries a real ``category``/
``error_code``/``retriable``/``retry_after_seconds``, not just a
message.

Every field :class:`~ai_os_kernel.llm_gateway.models.LLMRequest`
excluded when the request contract was reduced (tool-calling, structured
output, thinking/effort, streaming, cache hints, budgets, metadata) is
also absent from the request this adapter sends — there is nothing here
to translate them from. In particular, no ``thinking`` parameter is set:
enabling it by default would be inventing request behaviour the
documented, already-reduced ``LLMRequest`` contract gives no caller any
way to control.

**Real streaming (§4.3, ``P02-S02-M06-T08``) is a separate method,
``stream()``, not a ``stream: bool`` field on ``LLMRequest`` itself** —
the same, already-reduced request contract, per this ticket's own
Input, drives both; which method is called is the real selector.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Mapping
from decimal import Decimal
from typing import Any

import anthropic

from ai_os_kernel.llm_gateway.adapters.model_config import ModelPricing
from ai_os_kernel.llm_gateway.error_taxonomy import (
    CAPABILITY_UNSUPPORTED,
    MISROUTED,
    NETWORK_FAILURE,
    NO_PRICING,
    classify_http_status,
    parse_retry_after_seconds,
)
from ai_os_kernel.llm_gateway.errors import LLMProviderError, LLMRefusalError
from ai_os_kernel.llm_gateway.models import (
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    StopReason,
    StreamEventType,
    UsageRecord,
)
from ai_os_kernel.llm_gateway.router import Router
from ai_os_kernel.secrets_manager.provider import SecretProvider

# Public (unlike most module constants in this codebase) because the
# composition root now needs the identical name when it builds this
# adapter's own Router — see build_anthropic_adapter's own docstring —
# so there is exactly one place this string is written, not two.
PROVIDER_NAME = "anthropic"

# The two ``stop_reason`` values this reduced contract's own StopReason
# enum can honestly represent (see models.py's own docstring for why
# the other five documented values are excluded).
_STOP_REASON_MAP: dict[str, StopReason] = {
    "end_turn": StopReason.END_TURN,
    "max_tokens": StopReason.MAX_TOKENS,
}


class AnthropicAdapter:
    """Calls the real Anthropic API via ``anthropic.AsyncAnthropic``.

    Takes an already-constructed client, a :class:`~ai_os_kernel.
    llm_gateway.router.Router` (constructor-injected, not a flat dict
    this class owns itself — see that module's own docstring for why),
    and the pricing mapping :mod:`~ai_os_kernel.llm_gateway.adapters.
    model_config` loads — constructor injection, wired by whoever
    composes this adapter (:func:`build_anthropic_adapter` for the
    common case of resolving the API key through Secrets Management
    first).
    """

    def __init__(
        self,
        *,
        client: anthropic.AsyncAnthropic,
        router: Router,
        pricing: Mapping[str, ModelPricing],
    ) -> None:
        self._client = client
        self._router = router
        self._pricing = dict(pricing)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        decision = self._router.resolve(request.model_alias)
        if decision.provider != PROVIDER_NAME:
            # This adapter is the only Provider Adapter that exists —
            # see the module docstring — so a Router ever naming a
            # different provider for some alias is a real
            # misconfiguration to refuse clearly, not a case to
            # silently ignore or route around (that would be provider
            # selection heuristics, explicitly out of scope here).
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

        kwargs: dict[str, Any] = {
            "model": model_id,
            "max_tokens": request.max_output_tokens,
            "messages": [
                {"role": message.role.value, "content": message.content}
                for message in request.messages
            ],
        }
        if request.system is not None:
            kwargs["system"] = request.system

        started = time.monotonic()
        try:
            response = await self._client.messages.create(**kwargs)
        except anthropic.APIStatusError as exc:
            classification = classify_http_status(exc.status_code)
            retry_after_seconds = parse_retry_after_seconds(exc.response.headers.get("retry-after"))
            raise LLMProviderError(
                f"Anthropic returned HTTP {exc.status_code} for model_alias "
                f"{request.model_alias!r}: {exc.message}",
                category=classification.category,
                error_code=classification.error_code,
                retriable=classification.retriable,
                retry_after_seconds=retry_after_seconds,
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise LLMProviderError(
                f"could not reach Anthropic for model_alias {request.model_alias!r}: {exc}",
                category=NETWORK_FAILURE.category,
                error_code=NETWORK_FAILURE.error_code,
                retriable=NETWORK_FAILURE.retriable,
            ) from exc
        latency_ms = int((time.monotonic() - started) * 1000)

        return _map_response(response, latency_ms=latency_ms, pricing=pricing)

    async def count_tokens(self, request: LLMRequest) -> int:
        """llm_gateway.md §12: "Token counts come only from provider
        token-counting endpoints" — calls the real, documented
        ``POST /v1/messages/count_tokens`` Anthropic endpoint
        (``anthropic.AsyncAnthropic.messages.count_tokens``), never a
        third-party or approximated tokenizer. A separate real network
        call from :meth:`complete`, since Anthropic's own count-tokens
        endpoint is unpriced and independent of a real completion — no
        pricing lookup is needed here.

        Never walks a fallback chain: a token count is specific to
        *this* resolved model's own real tokenizer, so silently
        substituting a different provider's count would be a real,
        wrong answer for the model the caller actually asked about, not
        an honest approximation of it.
        (:class:`~ai_os_kernel.llm_gateway.gateway.DispatchingLLMGateway`'s
        own :meth:`~ai_os_kernel.llm_gateway.gateway.DispatchingLLMGateway.count_tokens`
        resolves ``model_alias`` once and calls this exactly once,
        never retrying against a fallback candidate.)
        """
        decision = self._router.resolve(request.model_alias)
        if decision.provider != PROVIDER_NAME:
            raise LLMProviderError(
                f"model_alias {request.model_alias!r} routes to provider "
                f"{decision.provider!r}, which this adapter does not serve "
                f"(it only calls {PROVIDER_NAME!r})",
                category=MISROUTED.category,
                error_code=MISROUTED.error_code,
                retriable=MISROUTED.retriable,
            )

        kwargs: dict[str, Any] = {
            "model": decision.model_id,
            "messages": [
                {"role": message.role.value, "content": message.content}
                for message in request.messages
            ],
        }
        if request.system is not None:
            kwargs["system"] = request.system

        try:
            result = await self._client.messages.count_tokens(**kwargs)
        except anthropic.APIStatusError as exc:
            classification = classify_http_status(exc.status_code)
            retry_after_seconds = parse_retry_after_seconds(exc.response.headers.get("retry-after"))
            raise LLMProviderError(
                f"Anthropic returned HTTP {exc.status_code} counting tokens for model_alias "
                f"{request.model_alias!r}: {exc.message}",
                category=classification.category,
                error_code=classification.error_code,
                retriable=classification.retriable,
                retry_after_seconds=retry_after_seconds,
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise LLMProviderError(
                f"could not reach Anthropic to count tokens for model_alias "
                f"{request.model_alias!r}: {exc}",
                category=NETWORK_FAILURE.category,
                error_code=NETWORK_FAILURE.error_code,
                retriable=NETWORK_FAILURE.retriable,
            ) from exc

        return result.input_tokens

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        """llm_gateway.md §4.3: real, incremental delivery — a genuine
        SSE round trip against Anthropic's own real streaming endpoint
        (``messages.create(..., stream=True)``), never a single
        blocking response dressed up as a stream.

        Never retried or fallen back by
        :class:`~ai_os_kernel.llm_gateway.gateway.DispatchingLLMGateway`
        (see that class's own :meth:`~ai_os_kernel.llm_gateway.gateway.
        DispatchingLLMGateway.stream` docstring for why) — this method
        itself makes exactly one real attempt too.

        §4.3's own event set is ``message_start | content_start |
        content_delta | content_stop | message_delta | message_stop |
        error``; ``error`` is deliberately not one of
        :class:`~ai_os_kernel.llm_gateway.models.StreamEventType`'s six
        values — a real provider failure raises
        :class:`LLMProviderError` out of this generator, the identical
        channel every other real failure in this Gateway already
        uses, rather than a second, parallel in-band error-delivery
        event type.
        """
        decision = self._router.resolve(request.model_alias)
        if decision.provider != PROVIDER_NAME:
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

        kwargs: dict[str, Any] = {
            "model": model_id,
            "max_tokens": request.max_output_tokens,
            "messages": [
                {"role": message.role.value, "content": message.content}
                for message in request.messages
            ],
        }
        if request.system is not None:
            kwargs["system"] = request.system

        started = time.monotonic()
        # Anthropic's own real `message_delta.usage.input_tokens` is
        # optional on the wire (the SDK's own `MessageDeltaUsage` type
        # marks it so) — remembered here from the one real place input
        # tokens are unambiguously reported, `message_start`, so a real
        # `message_delta` that omits it still gets an honest, real
        # total rather than a wrong `0`.
        input_tokens_from_start = 0
        try:
            raw_stream = await self._client.messages.create(**kwargs, stream=True)
            async for raw_event in raw_stream:
                if raw_event.type == "ping":
                    # A real Anthropic keep-alive, not part of §4.3's
                    # own event set at all — silently skipped, never
                    # reported as a fabricated event of some other
                    # type.
                    continue
                if raw_event.type == "message_start":
                    input_tokens_from_start = raw_event.message.usage.input_tokens
                yield _map_stream_event(
                    raw_event,
                    model_id=model_id,
                    latency_ms=int((time.monotonic() - started) * 1000),
                    pricing=pricing,
                    input_tokens_hint=input_tokens_from_start,
                )
        except anthropic.APIStatusError as exc:
            classification = classify_http_status(exc.status_code)
            retry_after_seconds = parse_retry_after_seconds(exc.response.headers.get("retry-after"))
            raise LLMProviderError(
                f"Anthropic returned HTTP {exc.status_code} streaming for model_alias "
                f"{request.model_alias!r}: {exc.message}",
                category=classification.category,
                error_code=classification.error_code,
                retriable=classification.retriable,
                retry_after_seconds=retry_after_seconds,
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise LLMProviderError(
                f"could not reach Anthropic to stream for model_alias "
                f"{request.model_alias!r}: {exc}",
                category=NETWORK_FAILURE.category,
                error_code=NETWORK_FAILURE.error_code,
                retriable=NETWORK_FAILURE.retriable,
            ) from exc


_STREAM_EVENT_TYPE_MAP: dict[str, StreamEventType] = {
    "message_start": StreamEventType.MESSAGE_START,
    "content_block_start": StreamEventType.CONTENT_START,
    "content_block_delta": StreamEventType.CONTENT_DELTA,
    "content_block_stop": StreamEventType.CONTENT_STOP,
    "message_delta": StreamEventType.MESSAGE_DELTA,
    "message_stop": StreamEventType.MESSAGE_STOP,
}


def _map_stream_event(
    event: Any,
    *,
    model_id: str,
    latency_ms: int,
    pricing: ModelPricing,
    input_tokens_hint: int,
) -> LLMStreamEvent:
    """Pure, synchronous mapping from one real Anthropic raw SSE event
    to §4.3's normalised :class:`LLMStreamEvent` — the identical "map
    the real wire shape, no I/O" role :func:`_map_response` already
    plays for a real, complete ``Message``.

    Anthropic's own real event ``type`` strings (``content_block_*``)
    are normalised to §4.3's shorter, platform-neutral names
    (``content_*``) here — "normalised across providers into this
    event set" is this doc section's own stated design, not something
    this function invents. Never called for a real ``ping`` event —
    :meth:`AnthropicAdapter.stream` filters that real keep-alive out
    before reaching here.
    """
    event_type = _STREAM_EVENT_TYPE_MAP.get(event.type)
    if event_type is None:
        raise LLMProviderError(
            f"Anthropic returned stream event type={event.type!r}, which this reduced "
            "contract does not represent",
            category=CAPABILITY_UNSUPPORTED.category,
            error_code=CAPABILITY_UNSUPPORTED.error_code,
            retriable=CAPABILITY_UNSUPPORTED.retriable,
        )

    if event_type is StreamEventType.CONTENT_START:
        if event.content_block.type != "text":
            raise LLMProviderError(
                f"Anthropic started a real content_block of type={event.content_block.type!r}, "
                "which this reduced contract does not represent (no tools or thinking are "
                "declared, so only 'text' should be reachable)",
                category=CAPABILITY_UNSUPPORTED.category,
                error_code=CAPABILITY_UNSUPPORTED.error_code,
                retriable=CAPABILITY_UNSUPPORTED.retriable,
            )
        return LLMStreamEvent(type=event_type, index=event.index)

    if event_type is StreamEventType.CONTENT_DELTA:
        if event.delta.type != "text_delta":
            raise LLMProviderError(
                f"Anthropic returned a real delta of type={event.delta.type!r}, which this "
                "reduced contract does not represent (no tools or thinking are declared, so "
                "only 'text_delta' should be reachable)",
                category=CAPABILITY_UNSUPPORTED.category,
                error_code=CAPABILITY_UNSUPPORTED.error_code,
                retriable=CAPABILITY_UNSUPPORTED.retriable,
            )
        return LLMStreamEvent(type=event_type, index=event.index, delta=event.delta.text)

    if event_type is StreamEventType.CONTENT_STOP:
        return LLMStreamEvent(type=event_type, index=event.index)

    if event_type is StreamEventType.MESSAGE_DELTA:
        usage = event.usage
        input_tokens = usage.input_tokens if usage.input_tokens is not None else input_tokens_hint
        cost_usd = (
            Decimal(input_tokens) * pricing.input_per_million_usd
            + Decimal(usage.output_tokens) * pricing.output_per_million_usd
        ) / Decimal(1_000_000)
        return LLMStreamEvent(
            type=event_type,
            usage=UsageRecord(
                input_tokens=input_tokens,
                output_tokens=usage.output_tokens,
                cache_read_tokens=usage.cache_read_input_tokens or 0,
                cache_write_tokens=usage.cache_creation_input_tokens or 0,
                cost_usd=cost_usd,
                latency_ms=latency_ms,
                provider=PROVIDER_NAME,
                model_id=model_id,
                retries=0,
                fallback_used=False,
            ),
        )

    # StreamEventType.MESSAGE_START / MESSAGE_STOP: real, honest "no
    # further real fact to attach" events per this module's own
    # docstring — see LLMStreamEvent's own docstring for why
    # message_start/message_stop never carry usage here.
    return LLMStreamEvent(type=event_type)


def _map_response(response: Any, *, latency_ms: int, pricing: ModelPricing) -> LLMResponse:
    """Pure, synchronous mapping from a real ``anthropic.types.Message``
    to this platform's reduced :class:`LLMResponse` — no I/O, so this is
    the part of :meth:`AnthropicAdapter.complete` that is unit tested
    directly against real SDK response objects, not the network call
    around it (see ``tests/unit/kernel/llm_gateway/adapters/
    test_anthropic_adapter.py``'s own docstring for why).

    ``response`` is typed ``Any`` rather than ``anthropic.types.Message``
    on purpose: this function only reads a handful of attributes off a
    real provider payload, and llm_gateway.md §5 already treats a raw
    provider response as boundary-typed data (``raw: object | None``),
    not something this platform's own code should couple tightly to.
    """

    if response.stop_reason == "refusal":
        raise LLMRefusalError(
            f"Anthropic declined the request (model={response.model!r}) — "
            "see llm_gateway.md §5's documented `refusal` outcome"
        )

    stop_reason = _STOP_REASON_MAP.get(response.stop_reason)
    if stop_reason is None:
        raise LLMProviderError(
            f"Anthropic returned stop_reason={response.stop_reason!r}, which this reduced "
            "contract does not represent (no tools, thinking, or stop sequences are declared, "
            "so 'tool_use'/'pause_turn'/'stop_sequence'/'model_context_window_exceeded' should "
            "not be reachable)",
            category=CAPABILITY_UNSUPPORTED.category,
            error_code=CAPABILITY_UNSUPPORTED.error_code,
            retriable=CAPABILITY_UNSUPPORTED.retriable,
        )

    content = "".join(block.text for block in response.content if block.type == "text")

    usage = response.usage
    cache_read_tokens = usage.cache_read_input_tokens or 0
    cache_write_tokens = usage.cache_creation_input_tokens or 0
    cost_usd = (
        Decimal(usage.input_tokens) * pricing.input_per_million_usd
        + Decimal(usage.output_tokens) * pricing.output_per_million_usd
    ) / Decimal(1_000_000)

    return LLMResponse(
        content=content,
        stop_reason=stop_reason,
        usage=UsageRecord(
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            provider=PROVIDER_NAME,
            model_id=response.model,
            retries=0,
            fallback_used=False,
        ),
        provider=PROVIDER_NAME,
        model_id=response.model,
        # Anthropic's public model ids (e.g. "claude-opus-5") carry no
        # separate version component the API exposes alongside them —
        # unlike a provider with dated snapshot ids, there is no second,
        # honestly-distinct value to put here.
        model_version=response.model,
    )


async def build_anthropic_adapter(
    *,
    secret_provider: SecretProvider,
    api_key_secret_reference: str,
    router: Router,
    pricing: Mapping[str, ModelPricing],
) -> AnthropicAdapter:
    """Resolves the Anthropic API key through Secrets Management
    (ADR-0024 — "Use existing Secrets Resolution for API key access
    where practical", this step's own approved framing) and constructs
    the real ``anthropic.AsyncAnthropic`` client, so
    :class:`AnthropicAdapter` itself never imports
    :mod:`~ai_os_kernel.secrets_manager` or knows a secret reference
    string exists — it only ever holds an already-authenticated client.

    ``api_key_secret_reference`` is a required parameter, not a default
    baked into this function, so the composition root — not this
    module — decides which secret backend and name resolves the key
    (Coding Standards: no hardcoded configuration). ``router`` is
    accepted the same way, not built here from a raw ``model_ids``
    mapping: the composition root decides which
    :class:`~ai_os_kernel.llm_gateway.router.Router` implementation
    backs this adapter, exactly the "routing decisions constructed
    through dependency injection" this step's own approved framing
    requires.
    """

    secret = await secret_provider.resolve(api_key_secret_reference)
    client = anthropic.AsyncAnthropic(api_key=secret.reveal())
    return AnthropicAdapter(client=client, router=router, pricing=pricing)
