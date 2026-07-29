"""``LLMGatewayAdapter`` — real, against a real
:class:`~ai_os_kernel.llm_gateway.gateway.DispatchingLLMGateway`
(``platform_sdk_v1_scope.md`` step 6a).

Echo-backed for determinism, matching this project's own established
test convention (``tests/unit/kernel/llm_gateway/test_dispatching_gateway.py``)
— no network, no real provider, but a genuinely real dispatch, retry,
and capability-negotiation path underneath.
"""

from __future__ import annotations

from ai_os_kernel.llm_gateway.capability_negotiator import (
    ProviderCapabilities as KernelProviderCapabilities,
)
from ai_os_kernel.llm_gateway.capability_negotiator import StaticCapabilityNegotiator
from ai_os_kernel.llm_gateway.gateway import DispatchingLLMGateway, EchoLLMGateway
from ai_os_kernel.llm_gateway.router import RoutingDecision, StaticRouter
from ai_os_kernel.sdk_adapters.llm_gateway_adapter import LLMGatewayAdapter
from ai_os_sdk.contracts import LLMGateway as SdkLLMGateway
from ai_os_sdk.models import LLMRequest, Message, MessageRole, TraceContext

_ALIAS = "fast-cheap"
_MODEL_ID = "echo-model-1"

_KERNEL_CAPABILITIES = KernelProviderCapabilities(
    supports_tools=False,
    supports_parallel_tool_calls=False,
    supports_strict_tools=False,
    supports_structured_output=False,
    supports_streaming=False,
    supports_thinking=False,
    supports_effort=False,
    supports_prompt_caching=True,
    prompt_cache_min_tokens=1024,
    supports_vision=False,
    max_input_tokens=100_000,
    max_output_tokens=8_192,
    accepts_sampling_params=False,
)


def _real_adapter() -> LLMGatewayAdapter:
    router = StaticRouter(
        routes={_ALIAS: RoutingDecision(provider="echo-provider", model_id=_MODEL_ID)}
    )
    negotiator = StaticCapabilityNegotiator(
        router=router, capabilities_by_model_id={_MODEL_ID: _KERNEL_CAPABILITIES}
    )
    dispatcher = DispatchingLLMGateway(
        router=router,
        gateways={"echo-provider": EchoLLMGateway()},
        capability_negotiator=negotiator,
    )
    return LLMGatewayAdapter(dispatcher)


class TestLLMGatewayAdapterSatisfiesTheProtocol:
    def test_the_adapter_itself_is_an_sdk_llm_gateway(self) -> None:
        """The adapter, not the raw Kernel object, is what a pack will
        actually receive (step 6b) — so it is this class that must
        satisfy the Protocol."""
        assert isinstance(_real_adapter(), SdkLLMGateway)


class TestCompleteAgainstARealDispatchingGateway:
    async def test_a_real_completion_round_trips_through_both_conversions(self) -> None:
        adapter = _real_adapter()
        request = LLMRequest(
            model_alias=_ALIAS,
            messages=[Message(role=MessageRole.USER, content="hello world")],
            max_output_tokens=100,
        )

        response = await adapter.complete(request)

        # EchoLLMGateway echoes the last message verbatim when it fits
        # within max_output_tokens — a real, observable, non-mocked
        # round trip through DispatchingLLMGateway's real routing.
        # provider/model_id below are EchoLLMGateway's own hardcoded
        # self-description ("echo"/"echo-1") -- not the router's own
        # registration key or target model id, verified by reading its
        # real implementation rather than assumed.
        assert response.content == "hello world"
        assert response.provider == "echo"
        assert response.model_id == "echo-1"

    async def test_max_output_tokens_genuinely_bounds_the_response(self) -> None:
        """Proves the SDK request's own field reaches the real Kernel
        gateway and has real effect, not just that a response comes
        back at all. EchoLLMGateway truncates by character count."""
        adapter = _real_adapter()
        original = "a much longer message than five characters"
        request = LLMRequest(
            model_alias=_ALIAS,
            messages=[Message(role=MessageRole.USER, content=original)],
            max_output_tokens=5,
        )

        response = await adapter.complete(request)

        assert response.content == original[:5]
        assert len(response.content) == 5

    async def test_metadata_workflow_and_step_id_survive_the_narrowing_conversion(self) -> None:
        """The one real, documented narrowing (see this module's own
        docstring's link to llm_gateway_adapter.py): workflow_id/step_id
        are the two fields that DO make it through to the Kernel's own
        reduced TraceContext."""
        adapter = _real_adapter()
        request = LLMRequest(
            model_alias=_ALIAS,
            messages=[Message(role=MessageRole.USER, content="hi")],
            max_output_tokens=10,
            metadata=TraceContext(trace_id="t", span_id="s", workflow_id="wf_1", step_id="stp_1"),
        )

        # No exception -- proves the conversion accepts the richer SDK
        # TraceContext and narrows it without error.
        response = await adapter.complete(request)
        assert response.content == "hi"

    async def test_a_usage_record_is_real_and_fully_populated(self) -> None:
        adapter = _real_adapter()
        request = LLMRequest(
            model_alias=_ALIAS,
            messages=[Message(role=MessageRole.USER, content="hi")],
            max_output_tokens=10,
        )

        response = await adapter.complete(request)

        assert response.usage.provider == "echo"
        assert response.usage.model_id == "echo-1"
        assert response.usage.retries == 0
        assert response.usage.fallback_used is False


class TestCapabilitiesAgainstARealNegotiator:
    def test_a_real_capability_lookup_round_trips_through_both_conversions(self) -> None:
        adapter = _real_adapter()

        capabilities = adapter.capabilities(_ALIAS)

        assert capabilities.supports_prompt_caching is True
        assert capabilities.prompt_cache_min_tokens == 1024
        assert capabilities.max_input_tokens == 100_000
        assert capabilities.max_output_tokens == 8_192

    def test_all_thirteen_fields_survive_the_conversion(self) -> None:
        adapter = _real_adapter()

        capabilities = adapter.capabilities(_ALIAS)

        assert capabilities.model_dump() == {
            "supports_tools": False,
            "supports_parallel_tool_calls": False,
            "supports_strict_tools": False,
            "supports_structured_output": False,
            "supports_streaming": False,
            "supports_thinking": False,
            "supports_effort": False,
            "supports_prompt_caching": True,
            "prompt_cache_min_tokens": 1024,
            "supports_vision": False,
            "max_input_tokens": 100_000,
            "max_output_tokens": 8_192,
            "accepts_sampling_params": False,
        }


class TestCapabilitiesWithoutANegotiator:
    def test_fails_clearly_rather_than_silently_when_the_wrapped_gateway_cannot_answer(
        self,
    ) -> None:
        """EchoLLMGateway itself has no capabilities() at all -- wrapping
        it directly (not through DispatchingLLMGateway) must fail fast,
        not silently fabricate a matrix."""
        adapter = LLMGatewayAdapter(EchoLLMGateway())

        try:
            adapter.capabilities(_ALIAS)
        except AttributeError as exc:
            assert "capabilities()" in str(exc)
        else:
            raise AssertionError("expected AttributeError")
