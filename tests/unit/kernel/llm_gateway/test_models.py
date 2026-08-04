"""Unit tests for the minimal LLMRequest/LLMResponse shapes: validation
only — no gateway, no I/O."""

import pytest
from pydantic import ValidationError

from ai_os_kernel.llm_gateway.models import (
    EmbeddingRequest,
    EmbeddingResponse,
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    Message,
    MessageRole,
    StopReason,
    StreamEventType,
    TraceContext,
    UsageRecord,
)


def _message(content: str = "hello") -> Message:
    return Message(role=MessageRole.USER, content=content)


def test_a_well_formed_request_is_accepted() -> None:
    request = LLMRequest(
        model_alias="fast-cheap",
        messages=[_message()],
        max_output_tokens=100,
    )

    assert request.model_alias == "fast-cheap"
    assert request.messages == [_message()]
    assert request.system is None


def test_system_prompt_is_optional_but_settable() -> None:
    request = LLMRequest(
        model_alias="fast-cheap",
        messages=[_message()],
        system="You are a helpful assistant.",
        max_output_tokens=100,
    )

    assert request.system == "You are a helpful assistant."


def test_blank_model_alias_is_rejected() -> None:
    with pytest.raises(ValidationError, match="model_alias must not be blank"):
        LLMRequest(model_alias="   ", messages=[_message()], max_output_tokens=100)


def test_empty_messages_is_rejected() -> None:
    with pytest.raises(ValidationError, match="at least one message"):
        LLMRequest(model_alias="fast-cheap", messages=[], max_output_tokens=100)


def test_non_positive_max_output_tokens_is_rejected() -> None:
    with pytest.raises(ValidationError):
        LLMRequest(model_alias="fast-cheap", messages=[_message()], max_output_tokens=0)


def test_request_is_frozen() -> None:
    request = LLMRequest(model_alias="fast-cheap", messages=[_message()], max_output_tokens=100)

    with pytest.raises(ValidationError):
        request.model_alias = "different-alias"  # type: ignore[misc]


def test_metadata_defaults_to_none() -> None:
    request = LLMRequest(model_alias="fast-cheap", messages=[_message()], max_output_tokens=100)

    assert request.metadata is None


def test_metadata_can_be_set_to_a_trace_context() -> None:
    metadata = TraceContext(workflow_id="workflow-1", step_id="step-1")

    request = LLMRequest(
        model_alias="fast-cheap",
        messages=[_message()],
        max_output_tokens=100,
        metadata=metadata,
    )

    assert request.metadata is metadata


def test_trace_context_fields_default_to_none() -> None:
    context = TraceContext()

    assert context.workflow_id is None
    assert context.step_id is None


def test_trace_context_accepts_workflow_and_step_ids() -> None:
    context = TraceContext(workflow_id="workflow-1", step_id="step-1")

    assert context.workflow_id == "workflow-1"
    assert context.step_id == "step-1"


def test_trace_context_is_frozen() -> None:
    context = TraceContext(workflow_id="workflow-1")

    with pytest.raises(ValidationError):
        context.workflow_id = "different-workflow"  # type: ignore[misc]


def test_trace_context_experiment_id_defaults_to_none() -> None:
    assert TraceContext().experiment_id is None


def test_trace_context_accepts_an_experiment_id() -> None:
    context = TraceContext(experiment_id="exp-1")

    assert context.experiment_id == "exp-1"


def _response(**overrides: object) -> LLMResponse:
    defaults: dict[str, object] = {
        "content": "hello",
        "stop_reason": StopReason.END_TURN,
        "usage": UsageRecord(
            input_tokens=1,
            output_tokens=1,
            cache_read_tokens=0,
            cache_write_tokens=0,
            cost_usd=0,
            latency_ms=1,
            provider="anthropic",
            model_id="claude-x",
            retries=0,
            fallback_used=False,
        ),
        "provider": "anthropic",
        "model_id": "claude-x",
        "model_version": "1",
    }
    defaults.update(overrides)
    return LLMResponse.model_validate(defaults)


def test_llm_response_served_from_cache_defaults_to_false() -> None:
    assert _response().served_from_cache is False


def test_llm_response_served_from_cache_can_be_set_true() -> None:
    assert _response(served_from_cache=True).served_from_cache is True


def test_embedding_request_accepts_a_batch_of_inputs() -> None:
    request = EmbeddingRequest(model_alias="embedding-fast", inputs=["a", "b"])

    assert request.inputs == ["a", "b"]
    assert request.metadata is None


def test_embedding_request_rejects_a_blank_model_alias() -> None:
    with pytest.raises(ValidationError, match="model_alias must not be blank"):
        EmbeddingRequest(model_alias="   ", inputs=["a"])


def test_embedding_request_rejects_empty_inputs() -> None:
    with pytest.raises(ValidationError, match="at least one text"):
        EmbeddingRequest(model_alias="embedding-fast", inputs=[])


def test_embedding_request_is_frozen() -> None:
    request = EmbeddingRequest(model_alias="embedding-fast", inputs=["a"])

    with pytest.raises(ValidationError):
        request.inputs = ["b"]  # type: ignore[misc]


def test_embedding_response_carries_real_vectors_and_dimensions() -> None:
    response = EmbeddingResponse(
        vectors=[[0.1, 0.2, 0.3]],
        model_id="nomic-embed-text",
        model_version="nomic-embed-text",
        dimensions=3,
        usage=UsageRecord(
            input_tokens=5,
            output_tokens=0,
            cache_read_tokens=0,
            cache_write_tokens=0,
            cost_usd=0,
            latency_ms=1,
            provider="local",
            model_id="nomic-embed-text",
            retries=0,
            fallback_used=False,
        ),
    )

    assert response.vectors == [[0.1, 0.2, 0.3]]
    assert response.dimensions == 3


def test_llm_stream_event_defaults_index_delta_and_usage_to_none() -> None:
    event = LLMStreamEvent(type=StreamEventType.MESSAGE_START)

    assert event.index is None
    assert event.delta is None
    assert event.usage is None


def test_llm_stream_event_carries_a_real_text_delta() -> None:
    event = LLMStreamEvent(type=StreamEventType.CONTENT_DELTA, index=0, delta="hi")

    assert event.type == StreamEventType.CONTENT_DELTA
    assert event.index == 0
    assert event.delta == "hi"


def test_llm_stream_event_is_frozen() -> None:
    event = LLMStreamEvent(type=StreamEventType.MESSAGE_START)

    with pytest.raises(ValidationError):
        event.delta = "x"  # type: ignore[misc]
