"""Wraps a real :class:`~ai_os_kernel.llm_gateway.gateway.DispatchingLLMGateway`
to satisfy :class:`ai_os_sdk.contracts.LLMGateway`
(``platform_sdk_v1_scope.md`` step 6a).

**Real and constructible, not merely ``isinstance``-true.** Step 4
proved ``DispatchingLLMGateway`` structurally satisfies the SDK
Protocol directly (it has both ``complete()`` and ``capabilities()``),
which is exactly why this adapter's own job is narrow: convert the
SDK's boundary models to and from the Kernel's own, and delegate
everything else unchanged. It adds no retry, routing, or budget logic
of its own — all of that already lives in the wrapped
``DispatchingLLMGateway``.

**Every field on both sides was checked, not assumed, before writing
this conversion:**

- ``LLMRequest``: ``model_alias``/``system``/``max_output_tokens`` are
  identical on both sides. ``messages`` differs only in which
  ``MessageRole``/``Message`` class each ``Message`` uses — mapped by
  wire value, matching the same "two independent enums, one JSON
  Schema" pattern already established for ``TrustTier``
  (``ai_os_sdk.models.tool``).
- ``metadata``: **a real, one-directional narrowing, not a bug.** The
  SDK's canonical ``TraceContext`` (``ai_os_sdk.models.common``) carries
  seven fields; the Kernel's own ``ai_os_kernel.llm_gateway.models.
  TraceContext`` — a deliberately reduced slice, by its own docstring —
  carries only ``workflow_id``/``step_id``. Converting a richer SDK
  context into the narrower Kernel one necessarily drops
  ``trace_id``/``span_id``/``agent_id``/``experiment_id``/``run_id``.
  This was flagged as a real discrepancy to watch for exactly here, in
  step 4's own record (``platform_sdk_v1_scope.md`` §6d) — this adapter
  is that flag being resolved, honestly, not silently.
- ``UsageRecord``: both sides declare the identical ten fields
  (``input_tokens``, ``output_tokens``, ``cache_read_tokens``,
  ``cache_write_tokens``, ``cost_usd: Decimal``, ``latency_ms``,
  ``provider``, ``model_id``, ``retries``, ``fallback_used``) — a
  direct, lossless 1:1 mapping.
- ``LLMResponse``: identical fields on both sides
  (``content``/``stop_reason``/``usage``/``provider``/``model_id``/
  ``model_version``) plus ``StopReason``, mapped by wire value like
  ``MessageRole`` above.
- ``ProviderCapabilities``: identical 13 fields on both sides — step 4
  extended the SDK's shape to match the Kernel's real one exactly for
  precisely this reason. A direct, lossless 1:1 mapping.
"""

from __future__ import annotations

from ai_os_kernel.llm_gateway import models as kernel_models
from ai_os_kernel.llm_gateway.capability_negotiator import (
    ProviderCapabilities as KernelProviderCapabilities,
)
from ai_os_kernel.llm_gateway.gateway import LLMGateway as KernelLLMGatewayProtocol
from ai_os_sdk.models.llm import LLMRequest as SdkLLMRequest
from ai_os_sdk.models.llm import LLMResponse as SdkLLMResponse
from ai_os_sdk.models.llm import ProviderCapabilities as SdkProviderCapabilities
from ai_os_sdk.models.llm import StopReason as SdkStopReason
from ai_os_sdk.models.llm import UsageRecord as SdkUsageRecord


def _to_kernel_request(request: SdkLLMRequest) -> kernel_models.LLMRequest:
    metadata: kernel_models.TraceContext | None = None
    if request.metadata is not None:
        metadata = kernel_models.TraceContext(
            workflow_id=request.metadata.workflow_id,
            step_id=request.metadata.step_id,
        )
    return kernel_models.LLMRequest(
        model_alias=request.model_alias,
        messages=[
            kernel_models.Message(
                role=kernel_models.MessageRole(message.role.value), content=message.content
            )
            for message in request.messages
        ],
        system=request.system,
        max_output_tokens=request.max_output_tokens,
        metadata=metadata,
    )


def _to_sdk_response(response: kernel_models.LLMResponse) -> SdkLLMResponse:
    return SdkLLMResponse(
        content=response.content,
        stop_reason=SdkStopReason(response.stop_reason.value),
        usage=SdkUsageRecord(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cache_read_tokens=response.usage.cache_read_tokens,
            cache_write_tokens=response.usage.cache_write_tokens,
            cost_usd=response.usage.cost_usd,
            latency_ms=response.usage.latency_ms,
            provider=response.usage.provider,
            model_id=response.usage.model_id,
            retries=response.usage.retries,
            fallback_used=response.usage.fallback_used,
        ),
        provider=response.provider,
        model_id=response.model_id,
        model_version=response.model_version,
    )


def _to_sdk_capabilities(capabilities: KernelProviderCapabilities) -> SdkProviderCapabilities:
    return SdkProviderCapabilities(
        supports_tools=capabilities.supports_tools,
        supports_parallel_tool_calls=capabilities.supports_parallel_tool_calls,
        supports_strict_tools=capabilities.supports_strict_tools,
        supports_structured_output=capabilities.supports_structured_output,
        supports_streaming=capabilities.supports_streaming,
        supports_thinking=capabilities.supports_thinking,
        supports_effort=capabilities.supports_effort,
        supports_prompt_caching=capabilities.supports_prompt_caching,
        prompt_cache_min_tokens=capabilities.prompt_cache_min_tokens,
        supports_vision=capabilities.supports_vision,
        max_input_tokens=capabilities.max_input_tokens,
        max_output_tokens=capabilities.max_output_tokens,
        accepts_sampling_params=capabilities.accepts_sampling_params,
    )


class LLMGatewayAdapter:
    """Satisfies :class:`ai_os_sdk.contracts.LLMGateway` by delegating
    to a real, injected Kernel gateway.

    Accepts any object satisfying the Kernel's own internal
    ``LLMGateway`` Protocol (``complete()`` only) for :meth:`complete`,
    but :meth:`capabilities` requires the wrapped object to also expose
    a ``capabilities`` method — true of
    :class:`~ai_os_kernel.llm_gateway.gateway.DispatchingLLMGateway`,
    the only real implementation with one. Calling :meth:`capabilities`
    against a gateway without one raises :class:`AttributeError`
    immediately rather than a confusing failure deeper in the call, the
    same "fail fast and fail clearly" convention this codebase already
    follows elsewhere.
    """

    def __init__(self, gateway: KernelLLMGatewayProtocol) -> None:
        self._gateway = gateway

    async def complete(self, request: SdkLLMRequest) -> SdkLLMResponse:
        kernel_request = _to_kernel_request(request)
        kernel_response = await self._gateway.complete(kernel_request)
        return _to_sdk_response(kernel_response)

    def capabilities(self, model_alias: str) -> SdkProviderCapabilities:
        capabilities_method = getattr(self._gateway, "capabilities", None)
        if capabilities_method is None:
            raise AttributeError(
                f"{type(self._gateway).__name__} exposes no capabilities() method — "
                "LLMGatewayAdapter.capabilities() requires the wrapped gateway to "
                "implement platform_sdk.md §5.1's full signature, not only complete()"
            )
        kernel_capabilities = capabilities_method(model_alias)
        return _to_sdk_capabilities(kernel_capabilities)
