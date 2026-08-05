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

**Real call recording (``P04-S01-M12-T10``) — reusing
:class:`~ai_os_kernel.llm_gateway.call_recorder.SqlLLMCallRecorder`
unchanged, the identical Protocol
:class:`~ai_os_kernel.prompted_completion.PromptedCompletionService`
already records through, not a parallel mechanism.** Every SDK-native
agent already builds a real ``TraceContext`` with ``workflow_id``/
``step_id``/``agent_id`` (see this class's own ``metadata`` note above)
and, since ``P04-S01-M12-T10`` added the two new optional fields
(``ai_os_sdk.models.common.TraceContext``'s own docstring), now also
``prompt_id``/``prompt_version`` — the two fields ``evaluation.
llm_calls`` requires alongside ``agent_id``, real foreign keys, never
optional at the storage layer. ``agent_id`` itself cannot travel this
same route: it is dropped by the narrowing above (this class has no
way to recover it from the Kernel-side request after the fact), so it
is instead supplied once, at construction time, by whichever caller
already resolved *which* agent this adapter instance backs
(:func:`~ai_os_kernel.sdk_adapters.pack_context.build_pack_context`,
threaded from :class:`~ai_os_kernel.workflow_engine.registry.
SqlAgentRegistry`'s own already-resolved ``agent_id`` — see that
module's own docstring). Recording fires only when every one of
``call_recorder``/``agent_id``/``metadata``/``workflow_id``/
``step_id``/``prompt_id``/``prompt_version`` is present — the identical
all-or-nothing guard
:meth:`~ai_os_kernel.prompted_completion.PromptedCompletionService.
complete_from_prompt` already applies, so a call missing any one of
them (e.g. a raw, non-prompt-driven completion) is silently never
recorded, never a partial or malformed row.

**A real, billed completion's own response is never lost to a
downstream recording failure.** The real Kernel ``complete()`` call
happens first and its response is always returned; recording is
attempted only after, inside its own ``try``/``except`` — a genuinely
unreachable database at that moment (or any other recorder failure)
is logged as a warning and never propagates, the identical "catch,
warn, don't crash a real, already-succeeded operation" shape
``bootstrap._seed_prompted_agent_catalog_rows``'s own caller already
established for the analogous risk in the ``PromptedAgent`` path
(``P04-S01-M12-T09``).
"""

from __future__ import annotations

from ai_os_kernel.llm_gateway import models as kernel_models
from ai_os_kernel.llm_gateway.call_recorder import LLMCallRecorder
from ai_os_kernel.llm_gateway.capability_negotiator import (
    ProviderCapabilities as KernelProviderCapabilities,
)
from ai_os_kernel.llm_gateway.gateway import LLMGateway as KernelLLMGatewayProtocol
from ai_os_kernel.observability.logging import get_logger
from ai_os_sdk.models.llm import LLMRequest as SdkLLMRequest
from ai_os_sdk.models.llm import LLMResponse as SdkLLMResponse
from ai_os_sdk.models.llm import ProviderCapabilities as SdkProviderCapabilities
from ai_os_sdk.models.llm import StopReason as SdkStopReason
from ai_os_sdk.models.llm import UsageRecord as SdkUsageRecord

logger = get_logger("ai_os_kernel.sdk_adapters.llm_gateway_adapter")


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

    def __init__(
        self,
        gateway: KernelLLMGatewayProtocol,
        *,
        agent_id: str | None = None,
        call_recorder: LLMCallRecorder | None = None,
    ) -> None:
        self._gateway = gateway
        self._agent_id = agent_id
        self._call_recorder = call_recorder

    async def complete(self, request: SdkLLMRequest) -> SdkLLMResponse:
        kernel_request = _to_kernel_request(request)
        kernel_response = await self._gateway.complete(kernel_request)
        await self._maybe_record(request, kernel_request, kernel_response)
        return _to_sdk_response(kernel_response)

    async def _maybe_record(
        self,
        request: SdkLLMRequest,
        kernel_request: kernel_models.LLMRequest,
        kernel_response: kernel_models.LLMResponse,
    ) -> None:
        if self._call_recorder is None or self._agent_id is None:
            return
        metadata = request.metadata
        if (
            metadata is None
            or metadata.workflow_id is None
            or metadata.step_id is None
            or metadata.prompt_id is None
            or metadata.prompt_version is None
        ):
            return
        try:
            await self._call_recorder.record(
                request=kernel_request,
                response=kernel_response,
                workflow_id=metadata.workflow_id,
                step_id=metadata.step_id,
                agent_id=self._agent_id,
                prompt_id=metadata.prompt_id,
                prompt_version=metadata.prompt_version,
            )
        except Exception as exc:
            logger.warning(
                "sdk_adapters.llm_gateway_adapter.call_recording_failed",
                agent_id=self._agent_id,
                workflow_id=metadata.workflow_id,
                step_id=metadata.step_id,
                error=str(exc),
            )

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
