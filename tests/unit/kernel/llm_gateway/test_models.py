"""Unit tests for the minimal LLMRequest/LLMResponse shapes: validation
only — no gateway, no I/O."""

import pytest
from pydantic import ValidationError

from ai_os_kernel.llm_gateway.models import LLMRequest, Message, MessageRole, TraceContext


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
