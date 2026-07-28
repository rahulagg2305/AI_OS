"""Unit tests for EchoLLMGateway: the one trivial in-process
implementation of LLMGateway — no I/O, no provider, nothing to mock."""

from decimal import Decimal

import pytest

from ai_os_kernel.llm_gateway.gateway import EchoLLMGateway
from ai_os_kernel.llm_gateway.models import LLMRequest, Message, MessageRole, StopReason


def _request(content: str, max_output_tokens: int = 100) -> LLMRequest:
    return LLMRequest(
        model_alias="fast-cheap",
        messages=[Message(role=MessageRole.USER, content=content)],
        max_output_tokens=max_output_tokens,
    )


@pytest.mark.asyncio
async def test_completion_echoes_the_last_message_content() -> None:
    gateway = EchoLLMGateway()

    response = await gateway.complete(_request("hello there", max_output_tokens=100))

    assert response.content == "hello there"
    assert response.stop_reason == StopReason.END_TURN


@pytest.mark.asyncio
async def test_completion_uses_the_conversation_s_last_message() -> None:
    gateway = EchoLLMGateway()
    request = LLMRequest(
        model_alias="fast-cheap",
        messages=[
            Message(role=MessageRole.USER, content="first"),
            Message(role=MessageRole.ASSISTANT, content="second"),
            Message(role=MessageRole.USER, content="third"),
        ],
        max_output_tokens=100,
    )

    response = await gateway.complete(request)

    assert response.content == "third"


@pytest.mark.asyncio
async def test_content_is_truncated_to_max_output_tokens_and_reports_max_tokens() -> None:
    gateway = EchoLLMGateway()

    response = await gateway.complete(
        _request("a much longer message than allowed", max_output_tokens=5)
    )

    assert response.content == "a muc"
    assert len(response.content) == 5
    assert response.stop_reason == StopReason.MAX_TOKENS


@pytest.mark.asyncio
async def test_content_exactly_at_the_bound_is_not_truncated() -> None:
    gateway = EchoLLMGateway()

    response = await gateway.complete(_request("exact", max_output_tokens=5))

    assert response.content == "exact"
    assert response.stop_reason == StopReason.END_TURN


@pytest.mark.asyncio
async def test_usage_is_honestly_zeroed_for_everything_this_step_does_not_do() -> None:
    gateway = EchoLLMGateway()

    response = await gateway.complete(_request("hello"))

    assert response.usage.input_tokens == 0
    assert response.usage.output_tokens == 0
    assert response.usage.cache_read_tokens == 0
    assert response.usage.cache_write_tokens == 0
    assert response.usage.cost_usd == Decimal("0")
    assert response.usage.retries == 0
    assert response.usage.fallback_used is False
    assert response.usage.latency_ms >= 0


@pytest.mark.asyncio
async def test_provider_and_model_fields_are_honestly_labelled_as_the_echo_stand_in() -> None:
    gateway = EchoLLMGateway()

    response = await gateway.complete(_request("hello"))

    assert response.provider == "echo"
    assert response.model_id == "echo-1"
    assert response.usage.provider == "echo"
    assert response.usage.model_id == "echo-1"
