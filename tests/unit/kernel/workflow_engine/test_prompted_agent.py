"""Unit tests for PromptedAgent: its own logic only (reading
promptId/promptVersion/modelAlias from inputs, delegating, mapping the
result) — using InMemoryPromptEngine/EchoLLMGateway plus a fake
recorder, mirroring tests/unit/kernel/test_prompted_completion.py. No
real database, no real provider."""

from typing import Any

import pytest

from ai_os_kernel.context_manager.models import AssembledContext, ContextItem, SourceRef, SourceType
from ai_os_kernel.llm_gateway.gateway import EchoLLMGateway
from ai_os_kernel.llm_gateway.models import LLMRequest, LLMResponse
from ai_os_kernel.prompt_engine.renderer import InMemoryPromptEngine
from ai_os_kernel.prompted_completion import PromptedCompletionService
from ai_os_kernel.workflow_engine.errors import PromptedAgentInputError
from ai_os_kernel.workflow_engine.prompted_agent import PromptedAgent


class _FakeCallRecorder:
    """Records every call made to it; never touches a database."""

    def __init__(self) -> None:
        self.record_calls: list[dict[str, Any]] = []

    async def record(
        self,
        *,
        request: LLMRequest,
        response: LLMResponse,
        workflow_id: str,
        step_id: str,
        agent_id: str | None = None,
        prompt_id: str | None = None,
        prompt_version: str | None = None,
    ) -> None:
        self.record_calls.append(
            {
                "workflow_id": workflow_id,
                "step_id": step_id,
                "agent_id": agent_id,
                "prompt_id": prompt_id,
                "prompt_version": prompt_version,
            }
        )


def _agent(call_recorder: _FakeCallRecorder | None = None) -> PromptedAgent:
    engine = InMemoryPromptEngine({("prompt_greeting", "1.0.0"): "Hello, {{name}}!"})
    service = PromptedCompletionService(
        prompt_engine=engine,
        llm_gateway=EchoLLMGateway(),
        call_recorder=call_recorder,
    )
    return PromptedAgent(service=service, max_output_tokens=100)


@pytest.mark.asyncio
async def test_execute_renders_and_completes_using_the_declared_invocation_fields() -> None:
    agent = _agent()

    outputs = await agent.execute(
        {
            "promptId": "prompt_greeting",
            "promptVersion": "1.0.0",
            "modelAlias": "fast-cheap",
            "variables": {"name": "Ada"},
        }
    )

    assert outputs == {"content": "Hello, Ada!"}


@pytest.mark.asyncio
async def test_execute_works_without_variables_when_the_template_needs_none() -> None:
    engine = InMemoryPromptEngine({("prompt_static", "1.0.0"): "You are a helpful assistant."})
    agent = PromptedAgent(
        service=PromptedCompletionService(prompt_engine=engine, llm_gateway=EchoLLMGateway()),
        max_output_tokens=100,
    )

    outputs = await agent.execute(
        {"promptId": "prompt_static", "promptVersion": "1.0.0", "modelAlias": "fast-cheap"}
    )

    assert outputs == {"content": "You are a helpful assistant."}


@pytest.mark.asyncio
async def test_execute_raises_when_prompt_id_is_missing() -> None:
    agent = _agent()

    with pytest.raises(PromptedAgentInputError, match="promptId"):
        await agent.execute({"promptVersion": "1.0.0", "modelAlias": "fast-cheap"})


@pytest.mark.asyncio
async def test_execute_raises_when_prompt_version_is_missing() -> None:
    agent = _agent()

    with pytest.raises(PromptedAgentInputError, match="promptVersion"):
        await agent.execute({"promptId": "prompt_greeting", "modelAlias": "fast-cheap"})


@pytest.mark.asyncio
async def test_execute_raises_when_model_alias_is_missing() -> None:
    agent = _agent()

    with pytest.raises(PromptedAgentInputError, match="modelAlias"):
        await agent.execute({"promptId": "prompt_greeting", "promptVersion": "1.0.0"})


@pytest.mark.asyncio
async def test_execute_raises_when_all_three_are_missing() -> None:
    agent = _agent()

    with pytest.raises(PromptedAgentInputError, match="promptId, promptVersion, modelAlias"):
        await agent.execute({})


@pytest.mark.asyncio
async def test_execute_records_the_call_when_workflow_and_step_context_are_provided() -> None:
    recorder = _FakeCallRecorder()
    agent = _agent(recorder)

    await agent.execute(
        {
            "promptId": "prompt_greeting",
            "promptVersion": "1.0.0",
            "modelAlias": "fast-cheap",
            "variables": {"name": "Ada"},
            "workflowId": "wf_1",
            "stepId": "step_1",
            "agentId": "se.software_engineering/prompted-agent",
        }
    )

    assert len(recorder.record_calls) == 1
    call = recorder.record_calls[0]
    assert call["workflow_id"] == "wf_1"
    assert call["step_id"] == "step_1"
    assert call["agent_id"] == "se.software_engineering/prompted-agent"
    assert call["prompt_id"] == "prompt_greeting"
    assert call["prompt_version"] == "1.0.0"


@pytest.mark.asyncio
async def test_execute_does_not_record_without_workflow_and_step_context() -> None:
    recorder = _FakeCallRecorder()
    agent = _agent(recorder)

    await agent.execute(
        {
            "promptId": "prompt_greeting",
            "promptVersion": "1.0.0",
            "modelAlias": "fast-cheap",
            "variables": {"name": "Ada"},
        }
    )

    assert recorder.record_calls == []


def _context_item(content: str) -> ContextItem:
    return ContextItem(
        content=content,
        provenance=SourceRef(source_type=SourceType.WORKFLOW_STATE, identifier="wf_1"),
        relevance_score=1.0,
        token_count=1,
        trust="untrusted",
    )


def _assembled_context(*contents: str) -> AssembledContext:
    return AssembledContext(
        items=[_context_item(c) for c in contents],
        total_tokens=len(contents),
        sources_queried=[SourceType.WORKFLOW_STATE] if contents else [],
        items_excluded_count=0,
        assembly_id="asm_test",
    )


@pytest.mark.asyncio
async def test_execute_flattens_assembled_context_into_the_context_variable() -> None:
    engine = InMemoryPromptEngine({("prompt_ctx", "1.0.0"): "Context: {{context}}"})
    agent = PromptedAgent(
        service=PromptedCompletionService(prompt_engine=engine, llm_gateway=EchoLLMGateway()),
        max_output_tokens=100,
    )

    outputs = await agent.execute(
        {
            "promptId": "prompt_ctx",
            "promptVersion": "1.0.0",
            "modelAlias": "fast-cheap",
            "context": _assembled_context("first", "second"),
        }
    )

    assert outputs == {"content": "Context: first\n\nsecond"}


@pytest.mark.asyncio
async def test_an_explicit_context_variable_wins_over_assembled_context() -> None:
    engine = InMemoryPromptEngine({("prompt_ctx", "1.0.0"): "Context: {{context}}"})
    agent = PromptedAgent(
        service=PromptedCompletionService(prompt_engine=engine, llm_gateway=EchoLLMGateway()),
        max_output_tokens=100,
    )

    outputs = await agent.execute(
        {
            "promptId": "prompt_ctx",
            "promptVersion": "1.0.0",
            "modelAlias": "fast-cheap",
            "variables": {"context": "explicit"},
            "context": _assembled_context("assembled"),
        }
    )

    assert outputs == {"content": "Context: explicit"}


@pytest.mark.asyncio
async def test_an_assembled_context_with_no_items_adds_no_context_variable() -> None:
    agent = _agent()

    outputs = await agent.execute(
        {
            "promptId": "prompt_greeting",
            "promptVersion": "1.0.0",
            "modelAlias": "fast-cheap",
            "variables": {"name": "Ada"},
            "context": _assembled_context(),
        }
    )

    assert outputs == {"content": "Hello, Ada!"}


@pytest.mark.asyncio
async def test_no_context_key_at_all_behaves_exactly_as_before() -> None:
    agent = _agent()

    outputs = await agent.execute(
        {
            "promptId": "prompt_greeting",
            "promptVersion": "1.0.0",
            "modelAlias": "fast-cheap",
            "variables": {"name": "Ada"},
        }
    )

    assert outputs == {"content": "Hello, Ada!"}


def test_output_schema_accepts_only_a_content_string() -> None:
    agent = _agent()

    assert agent.output_schema == {
        "type": "object",
        "properties": {"content": {"type": "string"}},
        "required": ["content"],
        "additionalProperties": False,
    }
