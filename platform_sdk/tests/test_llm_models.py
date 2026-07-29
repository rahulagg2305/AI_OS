"""Step 4 of ``platform_sdk_v1_scope.md``: the ``LLMGateway`` boundary
models (``platform_sdk.md`` §5.1, narrowed and extended shapes).

Tests the validation actually enforced — field-for-field mirrors of the
real Kernel models where narrowed, and the real 13-field
``ProviderCapabilities`` shape where extended.
"""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from ai_os_sdk.models import (
    LLMRequest,
    LLMResponse,
    Message,
    MessageRole,
    ProviderCapabilities,
    StopReason,
    UsageRecord,
)


def _capabilities(**overrides: object) -> ProviderCapabilities:
    fields: dict[str, object] = {
        "supports_tools": False,
        "supports_parallel_tool_calls": False,
        "supports_strict_tools": False,
        "supports_structured_output": False,
        "supports_streaming": False,
        "supports_thinking": False,
        "supports_effort": False,
        "supports_prompt_caching": False,
        "prompt_cache_min_tokens": None,
        "supports_vision": False,
        "max_input_tokens": 100_000,
        "max_output_tokens": 8_192,
        "accepts_sampling_params": False,
    }
    fields.update(overrides)
    return ProviderCapabilities(**fields)


def _usage(**overrides: object) -> UsageRecord:
    fields: dict[str, object] = {
        "input_tokens": 10,
        "output_tokens": 5,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "cost_usd": Decimal("0.001"),
        "latency_ms": 250,
        "provider": "anthropic",
        "model_id": "claude-x",
        "retries": 0,
        "fallback_used": False,
    }
    fields.update(overrides)
    return UsageRecord(**fields)


class TestMessage:
    @pytest.mark.parametrize("role", ["user", "assistant"])
    def test_accepts_the_two_documented_roles(self, role: str) -> None:
        assert Message(role=role, content="hi").role == role

    def test_rejects_system_as_a_message_role(self) -> None:
        """The system prompt is a separate top-level field
        (LLMRequest.system), not part of the messages list — mirroring
        the real Kernel's identical exclusion."""
        with pytest.raises(ValidationError):
            Message(role="system", content="you are helpful")


class TestLLMRequest:
    def test_accepts_a_minimal_valid_request(self) -> None:
        request = LLMRequest(
            model_alias="reasoning",
            messages=[Message(role=MessageRole.USER, content="hi")],
            max_output_tokens=100,
        )
        assert request.system is None
        assert request.metadata is None

    def test_rejects_a_blank_model_alias(self) -> None:
        with pytest.raises(ValidationError, match="never a literal model id"):
            LLMRequest(
                model_alias="  ",
                messages=[Message(role=MessageRole.USER, content="hi")],
                max_output_tokens=100,
            )

    def test_rejects_an_empty_message_list(self) -> None:
        with pytest.raises(ValidationError, match="at least one message"):
            LLMRequest(model_alias="reasoning", messages=[], max_output_tokens=100)

    @pytest.mark.parametrize("bad_value", [0, -1])
    def test_rejects_a_non_positive_max_output_tokens(self, bad_value: int) -> None:
        with pytest.raises(ValidationError):
            LLMRequest(
                model_alias="reasoning",
                messages=[Message(role=MessageRole.USER, content="hi")],
                max_output_tokens=bad_value,
            )

    def test_is_frozen(self) -> None:
        request = LLMRequest(
            model_alias="reasoning",
            messages=[Message(role=MessageRole.USER, content="hi")],
            max_output_tokens=100,
        )
        with pytest.raises(ValidationError):
            request.model_alias = "other"  # type: ignore[misc]


class TestStopReason:
    def test_defines_exactly_the_two_reachable_values(self) -> None:
        """Narrowed from the documented 5 values to the 2 a tool-free,
        non-streaming completion can honestly produce — mirroring the
        real Kernel's identical reduction."""
        assert {r.value for r in StopReason} == {"end_turn", "max_tokens"}


class TestUsageRecord:
    def test_accepts_zero_for_every_counter(self) -> None:
        """Zero is a real value (an uncached call has zero cache
        tokens), not a degenerate one."""
        usage = _usage(input_tokens=0, output_tokens=0, cache_read_tokens=0, cache_write_tokens=0)
        assert usage.input_tokens == 0

    @pytest.mark.parametrize(
        "field",
        [
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
            "latency_ms",
            "retries",
        ],
    )
    def test_rejects_a_negative_count(self, field: str) -> None:
        with pytest.raises(ValidationError):
            _usage(**{field: -1})

    def test_rejects_negative_cost(self) -> None:
        with pytest.raises(ValidationError):
            _usage(cost_usd=Decimal("-0.01"))

    def test_cost_is_decimal_not_float(self) -> None:
        """data_model.md §2: "Never floating point" for USD."""
        assert isinstance(_usage().cost_usd, Decimal)


class TestLLMResponse:
    def test_accepts_a_well_formed_response(self) -> None:
        response = LLMResponse(
            content="hello",
            stop_reason=StopReason.END_TURN,
            usage=_usage(),
            provider="anthropic",
            model_id="claude-x",
            model_version="1.0",
        )
        assert response.stop_reason is StopReason.END_TURN

    def test_is_frozen(self) -> None:
        response = LLMResponse(
            content="hello",
            stop_reason=StopReason.END_TURN,
            usage=_usage(),
            provider="anthropic",
            model_id="claude-x",
            model_version="1.0",
        )
        with pytest.raises(ValidationError):
            response.content = "changed"  # type: ignore[misc]


class TestProviderCapabilities:
    def test_defines_all_thirteen_real_fields(self) -> None:
        """The extension direction: 10 documented -> 13 real. This list
        is the authority the real StaticCapabilityNegotiator's own
        docstring names platform_sdk.md as "implementing past"."""
        assert set(ProviderCapabilities.model_fields) == {
            "supports_tools",
            "supports_parallel_tool_calls",
            "supports_strict_tools",
            "supports_structured_output",
            "supports_streaming",
            "supports_thinking",
            "supports_effort",
            "supports_prompt_caching",
            "prompt_cache_min_tokens",
            "supports_vision",
            "max_input_tokens",
            "max_output_tokens",
            "accepts_sampling_params",
        }

    def test_accepts_prompt_caching_with_a_minimum(self) -> None:
        caps = _capabilities(supports_prompt_caching=True, prompt_cache_min_tokens=1024)
        assert caps.prompt_cache_min_tokens == 1024

    def test_rejects_prompt_caching_true_without_a_minimum(self) -> None:
        with pytest.raises(ValidationError, match="must be set when supports_prompt_caching"):
            _capabilities(supports_prompt_caching=True, prompt_cache_min_tokens=None)

    def test_rejects_a_minimum_when_caching_is_unsupported(self) -> None:
        """A minimum for a capability the model does not have would be
        meaningless."""
        with pytest.raises(ValidationError, match="must be omitted when supports_prompt_caching"):
            _capabilities(supports_prompt_caching=False, prompt_cache_min_tokens=1024)

    @pytest.mark.parametrize("field", ["max_input_tokens", "max_output_tokens"])
    @pytest.mark.parametrize("bad_value", [0, -1])
    def test_rejects_a_non_positive_token_ceiling(self, field: str, bad_value: int) -> None:
        with pytest.raises(ValidationError, match="must both be positive"):
            _capabilities(**{field: bad_value})

    def test_is_frozen(self) -> None:
        caps = _capabilities()
        with pytest.raises(ValidationError):
            caps.supports_tools = True  # type: ignore[misc]
