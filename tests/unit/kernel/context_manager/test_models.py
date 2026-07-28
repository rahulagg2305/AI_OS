"""Unit tests for the Context Manager's reduced request/response
contract (ai_os_kernel.context_manager.models): validation and shape
only — no resolvers, no I/O."""

import pytest
from pydantic import ValidationError

from ai_os_kernel.context_manager.models import (
    AssembledContext,
    ContextItem,
    ContextRequest,
    SourceRef,
    SourceType,
)


def _item(content: str = "hello") -> ContextItem:
    return ContextItem(
        content=content,
        provenance=SourceRef(source_type=SourceType.WORKFLOW_STATE, identifier="wf_1"),
        relevance_score=1.0,
        token_count=2,
        trust="untrusted",
    )


def test_context_request_requires_workflow_and_step_id() -> None:
    request = ContextRequest(workflow_id="wf_1", step_id="step_1")

    assert request.workflow_id == "wf_1"
    assert request.step_id == "step_1"
    assert request.agent_id is None


def test_context_request_accepts_an_optional_agent_id() -> None:
    request = ContextRequest(workflow_id="wf_1", step_id="step_1", agent_id="platform/agent")

    assert request.agent_id == "platform/agent"


def test_context_request_token_budget_defaults_to_none() -> None:
    request = ContextRequest(workflow_id="wf_1", step_id="step_1")

    assert request.token_budget is None


def test_context_request_accepts_a_positive_token_budget() -> None:
    request = ContextRequest(workflow_id="wf_1", step_id="step_1", token_budget=500)

    assert request.token_budget == 500


def test_context_request_rejects_a_zero_token_budget() -> None:
    with pytest.raises(ValidationError):
        ContextRequest(workflow_id="wf_1", step_id="step_1", token_budget=0)


def test_context_request_rejects_a_negative_token_budget() -> None:
    with pytest.raises(ValidationError):
        ContextRequest(workflow_id="wf_1", step_id="step_1", token_budget=-1)


def test_context_request_is_frozen() -> None:
    request = ContextRequest(workflow_id="wf_1", step_id="step_1")

    with pytest.raises(ValidationError):
        request.workflow_id = "wf_2"  # type: ignore[misc]


def test_context_item_carries_every_documented_field() -> None:
    item = _item()

    assert item.content == "hello"
    assert item.provenance.source_type == SourceType.WORKFLOW_STATE
    assert item.provenance.identifier == "wf_1"
    assert item.relevance_score == 1.0
    assert item.token_count == 2
    assert item.trust == "untrusted"


def test_context_item_rejects_an_invalid_trust_value() -> None:
    with pytest.raises(ValidationError):
        ContextItem(
            content="hello",
            provenance=SourceRef(source_type=SourceType.WORKFLOW_STATE, identifier="wf_1"),
            relevance_score=1.0,
            token_count=2,
            trust="maybe",
        )


def test_context_item_and_source_ref_are_frozen() -> None:
    item = _item()

    with pytest.raises(ValidationError):
        item.content = "changed"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        item.provenance.identifier = "wf_2"  # type: ignore[misc]


def test_assembled_context_carries_every_documented_field_except_index_generation() -> None:
    assembled = AssembledContext(
        items=[_item()],
        total_tokens=2,
        sources_queried=[SourceType.WORKFLOW_STATE],
        items_excluded_count=0,
        assembly_id="asm_test",
    )

    assert assembled.items == [_item()]
    assert assembled.total_tokens == 2
    assert assembled.sources_queried == [SourceType.WORKFLOW_STATE]
    assert assembled.items_excluded_count == 0
    assert assembled.assembly_id == "asm_test"
    assert not hasattr(assembled, "index_generation")


def test_assembled_context_is_frozen() -> None:
    assembled = AssembledContext(
        items=[], total_tokens=0, sources_queried=[], items_excluded_count=0, assembly_id="asm_1"
    )

    with pytest.raises(ValidationError):
        assembled.assembly_id = "asm_2"  # type: ignore[misc]
