"""The Capability Negotiator (llm_gateway.md §3/§6): "matrix lookup,
emulate or fail." This step builds only the matrix and the lookup —
:class:`ProviderCapabilities`, the :class:`CapabilityNegotiator`
Protocol, and :class:`StaticCapabilityNegotiator`, its one
configuration-driven implementation.

**"Emulate or fail" is explicitly out of scope.** §6 also documents
four degradation rules (use it; emulate and record a ``Degradation``;
fail with ``llm.capability_unsupported``; never emulate a capability
the caller listed in ``require_capabilities``). None of that logic
exists here — there is nothing yet that *consumes* a
``ProviderCapabilities`` to make a use/emulate/fail decision (no
tool-calling, no structured-output emulation, no streaming, no
``require_capabilities`` field on ``LLMRequest``). This module answers
only "what does this alias's resolved model support," a real,
standalone fact-lookup with no dependency on any of that — the same
"prove the seam, defer the consumer" shape :mod:`~ai_os_kernel.
llm_gateway.router` used for the Router before the Retry & Fallback
Manager existed to walk a chain.

**Looked up by alias, keyed by model id — the identical shape
:mod:`~ai_os_kernel.llm_gateway.adapters.model_config`'s own
``pricing`` mapping already uses, for the identical reason.**
llm_gateway.md §6 says "the Gateway maintains a per-alias capability
matrix," and platform_sdk.md §5.1 documents the lookup itself as
``capabilities(alias: str) -> ProviderCapabilities`` — but a
capability is a fact about the *model* an alias currently resolves to,
not about the alias string itself (the same reasoning that already
keys ``ModelPricing`` by model id, not alias).
:class:`StaticCapabilityNegotiator` therefore takes a real
:class:`~ai_os_kernel.llm_gateway.router.Router` (to resolve alias ->
model id, exactly as every real provider adapter already does for
pricing) and a ``model id -> ProviderCapabilities`` mapping.

**Every field is a real, config-driven fact about a real model,
sourced from configuration, not hardcoded in this module** — the
identical "Model names ... shall always come from configuration"
principle :mod:`model_config` cites for pricing, applied to
capabilities. See ``config/llm.yaml``'s own ``capabilities:`` section
for the concrete per-model values and their sourcing caveats.

**Documentation discrepancy, flagged rather than silently resolved:**
platform_sdk.md §5.1's own ``ProviderCapabilities`` listing names ten
fields (omitting ``supports_strict_tools``, ``prompt_cache_min_tokens``,
and ``accepts_sampling_params``); llm_gateway.md §6 names thirteen.
Neither document states a precedence between the two for this specific
shape (platform_sdk.md is not in llm_gateway.md's own "Final Authority"
list, and vice versa). This module implements llm_gateway.md §6's
fuller thirteen-field shape, since that document is the Capability
Negotiator's own governing design (llm_gateway.md §3 names the
subsystem; platform_sdk.md only summarises the pack-facing surface) —
a reasoned choice, not a silent one, and worth reconciling in a future
documentation pass.

**Not yet part of the shared ``LLMGateway`` Protocol.** ``capabilities()``
is documented in platform_sdk.md §5.1 alongside ``complete()``/
``stream()``/``embed()``/``count_tokens()`` — and ``stream()``/``embed()``/
``count_tokens()`` are *also* still absent from this codebase's own
reduced ``LLMGateway`` Protocol (:mod:`~ai_os_kernel.llm_gateway.gateway`),
each deferred to its own not-yet-arrived step. ``capabilities()``
follows the identical precedent here: it is exposed as a new public
method on the one concrete class every real caller actually uses
(:class:`~ai_os_kernel.llm_gateway.gateway.DispatchingLLMGateway`), not
added to the shared Protocol — ADR-0004's "an interface is justified
when a second real use is imminent" does not yet apply, since no
second ``LLMGateway`` implementation needs to answer this question
polymorphically this step (``EchoLLMGateway`` has no real capability
matrix to report).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from pydantic import BaseModel, ConfigDict, model_validator

from ai_os_kernel.llm_gateway.error_taxonomy import NO_CAPABILITIES
from ai_os_kernel.llm_gateway.errors import LLMProviderError
from ai_os_kernel.llm_gateway.router import Router


class ProviderCapabilities(BaseModel):
    """One model's real, documented capability matrix — llm_gateway.md
    §6's full thirteen-field shape (see this module's own docstring for
    the platform_sdk.md discrepancy this implements past).

    ``max_input_tokens``/``max_output_tokens`` here are the *provider's*
    own ceilings — a fact about the model, unrelated to
    :attr:`~ai_os_kernel.llm_gateway.models.LLMRequest.max_output_tokens`,
    which is a caller's own per-request choice. Nothing here validates
    one against the other yet (that would be capability-dependent
    request validation — explicitly out of scope this step).
    """

    model_config = ConfigDict(frozen=True)

    supports_tools: bool
    supports_parallel_tool_calls: bool
    supports_strict_tools: bool
    supports_structured_output: bool
    supports_streaming: bool
    supports_thinking: bool
    supports_effort: bool
    supports_prompt_caching: bool
    prompt_cache_min_tokens: int | None
    supports_vision: bool
    max_input_tokens: int
    max_output_tokens: int
    accepts_sampling_params: bool

    @model_validator(mode="after")
    def _prompt_cache_min_tokens_matches_support(self) -> ProviderCapabilities:
        if self.supports_prompt_caching and self.prompt_cache_min_tokens is None:
            raise ValueError(
                "prompt_cache_min_tokens must be set when supports_prompt_caching is true"
            )
        if not self.supports_prompt_caching and self.prompt_cache_min_tokens is not None:
            raise ValueError(
                "prompt_cache_min_tokens must be omitted when supports_prompt_caching is false "
                "— a minimum for a capability this model does not have would be meaningless"
            )
        return self

    @model_validator(mode="after")
    def _token_ceilings_are_positive(self) -> ProviderCapabilities:
        if self.max_input_tokens <= 0 or self.max_output_tokens <= 0:
            raise ValueError("max_input_tokens and max_output_tokens must both be positive")
        return self


class CapabilityNegotiator(Protocol):
    """Resolves a ``model_alias`` to the real, current
    :class:`ProviderCapabilities` of whatever model it means right now
    — the seam a provider-health-aware or live-discovery implementation
    substitutes later (ADR-0004), mirroring
    :class:`~ai_os_kernel.llm_gateway.router.Router`'s own shape."""

    def capabilities(self, model_alias: str) -> ProviderCapabilities: ...


class StaticCapabilityNegotiator:
    """The one deterministic implementation for this step: resolves
    ``model_alias`` through a real :class:`Router` (identical to how
    every real adapter already resolves pricing), then looks up the
    resulting model id in a fixed, configuration-driven mapping.

    Raises clearly (:class:`LLMProviderError`, ``llm.no_capabilities``)
    for a model id with no configured entry — the identical "no
    pricing" shape :class:`~ai_os_kernel.llm_gateway.adapters.
    anthropic_adapter.AnthropicAdapter` already uses, not a fabricated
    default matrix.
    """

    def __init__(
        self, *, router: Router, capabilities_by_model_id: Mapping[str, ProviderCapabilities]
    ) -> None:
        self._router = router
        self._capabilities_by_model_id = dict(capabilities_by_model_id)

    def capabilities(self, model_alias: str) -> ProviderCapabilities:
        decision = self._router.resolve(model_alias)
        capabilities = self._capabilities_by_model_id.get(decision.model_id)
        if capabilities is None:
            raise LLMProviderError(
                f"model id {decision.model_id!r} (resolved from model_alias {model_alias!r}) "
                "has no configured capability matrix entry",
                category=NO_CAPABILITIES.category,
                error_code=NO_CAPABILITIES.error_code,
                retriable=NO_CAPABILITIES.retriable,
            )
        return capabilities
