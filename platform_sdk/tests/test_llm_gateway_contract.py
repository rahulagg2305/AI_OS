"""Step 4 of ``platform_sdk_v1_scope.md``: the ``LLMGateway`` Protocol
itself (``platform_sdk.md`` §5.1, narrowed to ``complete``/
``capabilities``).

Proof against the *real* ``DispatchingLLMGateway`` lives in
``tests/unit/platform_sdk/test_kernel_satisfies_sdk_contracts.py`` (see
that file's own docstring for why cross-boundary proofs live in the
root suite, not here). This file covers the Protocol's own semantics
with SDK-only, dependency-floor-respecting fixtures.
"""

from ai_os_sdk.contracts import LLMGateway
from ai_os_sdk.models import (
    LLMRequest,
    LLMResponse,
    Message,
    ProviderCapabilities,
    StopReason,
    UsageRecord,
)


def _capabilities() -> ProviderCapabilities:
    return ProviderCapabilities(
        supports_tools=False,
        supports_parallel_tool_calls=False,
        supports_strict_tools=False,
        supports_structured_output=False,
        supports_streaming=False,
        supports_thinking=False,
        supports_effort=False,
        supports_prompt_caching=False,
        prompt_cache_min_tokens=None,
        supports_vision=False,
        max_input_tokens=100_000,
        max_output_tokens=8_192,
        accepts_sampling_params=False,
    )


class _MinimalGateway:
    """Exactly the two members the narrowed Protocol requires."""

    async def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            content="ok",
            stop_reason=StopReason.END_TURN,
            usage=UsageRecord(
                input_tokens=1,
                output_tokens=1,
                cache_read_tokens=0,
                cache_write_tokens=0,
                cost_usd=0,
                latency_ms=1,
                provider="test",
                model_id="test-1",
                retries=0,
                fallback_used=False,
            ),
            provider="test",
            model_id="test-1",
            model_version="1.0",
        )

    def capabilities(self, model_alias: str) -> ProviderCapabilities:
        return _capabilities()


class TestLLMGatewayProtocol:
    def test_a_conforming_object_satisfies_it(self) -> None:
        assert isinstance(_MinimalGateway(), LLMGateway)

    def test_an_object_with_only_complete_does_not_satisfy_it(self) -> None:
        """The narrowed Protocol requires BOTH methods — this is exactly
        why the Kernel's own internal, complete()-only LLMGateway
        Protocol is not the same shape as this SDK Protocol, even though
        DispatchingLLMGateway satisfies both."""

        class CompleteOnly:
            async def complete(self, request: LLMRequest) -> LLMResponse:
                raise NotImplementedError

        assert not isinstance(CompleteOnly(), LLMGateway)

    def test_an_object_with_only_capabilities_does_not_satisfy_it(self) -> None:
        class CapabilitiesOnly:
            def capabilities(self, model_alias: str) -> ProviderCapabilities:
                return _capabilities()

        assert not isinstance(CapabilitiesOnly(), LLMGateway)

    async def test_complete_returns_the_declared_response_shape(self) -> None:
        gateway = _MinimalGateway()
        response = await gateway.complete(
            LLMRequest(
                model_alias="reasoning",
                messages=[Message(role="user", content="hi")],
                max_output_tokens=10,
            )
        )
        assert response.stop_reason is StopReason.END_TURN

    def test_capabilities_is_synchronous(self) -> None:
        """A fact lookup, unlike complete() — no await needed."""
        gateway = _MinimalGateway()
        result = gateway.capabilities("reasoning")
        assert isinstance(result, ProviderCapabilities)
