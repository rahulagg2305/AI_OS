"""Unit tests for AgentStepExecutor — no database, no real agent work
(ADR-0004: interface-driven, so fake Protocol implementations are
legitimate substitutes)."""

from typing import Any

import pytest

from ai_os_kernel.context_manager.models import AssembledContext, ContextRequest
from ai_os_kernel.workflow_engine.agent import Agent, EchoAgent
from ai_os_kernel.workflow_engine.errors import AgentNotRegisteredError, AgentOutputValidationError
from ai_os_kernel.workflow_engine.models import StepType, WorkflowStep
from ai_os_kernel.workflow_engine.registry import InMemoryAgentRegistry
from ai_os_kernel.workflow_engine.step_executor import AgentStepExecutor

_AGENT_ID = "se.software_engineering/analyst"
_AGENT_STEP = WorkflowStep(id="analyze_requirements", type=StepType.AGENT, agent_id=_AGENT_ID)
_TOOL_STEP = WorkflowStep(id="run_build", type=StepType.TOOL, tool_id="se.build")


def _registry_with(agent: Agent) -> InMemoryAgentRegistry:
    return InMemoryAgentRegistry({_AGENT_ID: agent})


class _MisbehavingAgent:
    """Declares one output_schema but returns something that violates it."""

    output_schema: dict[str, Any] = {
        "type": "object",
        "properties": {"status": {"const": "ok"}},
        "required": ["status"],
        "additionalProperties": False,
    }

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"status": "not-ok", "extra": "field"}


class _NamedAgent:
    """Returns its own name in the output, so a test can prove which
    registered agent actually ran without relying on two indistinguishable
    EchoAgent instances."""

    output_schema: dict[str, Any] = {
        "type": "object",
        "properties": {"ranAs": {"type": "string"}},
        "required": ["ranAs"],
        "additionalProperties": False,
    }

    def __init__(self, name: str) -> None:
        self._name = name

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"ranAs": self._name}


class _InputCapturingAgent:
    """Records whatever ``inputs`` it was actually called with, so a
    test can prove exactly what AgentStepExecutor forwards from a
    step's declared invocation fields — real, non-echoed evidence,
    not an assumption about the executor's internals."""

    output_schema: dict[str, Any] = {"type": "object"}

    def __init__(self) -> None:
        self.received_inputs: dict[str, Any] | None = None

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        self.received_inputs = inputs
        return {}


@pytest.mark.asyncio
async def test_agent_step_executor_calls_the_agent_and_returns_its_output() -> None:
    executor = AgentStepExecutor(_registry_with(EchoAgent()))

    outputs = await executor.execute(_AGENT_STEP)

    assert outputs == {"status": "ok"}


@pytest.mark.asyncio
async def test_agent_step_executor_rejects_output_violating_the_declared_schema() -> None:
    executor = AgentStepExecutor(_registry_with(_MisbehavingAgent()))

    with pytest.raises(AgentOutputValidationError, match="output_schema"):
        await executor.execute(_AGENT_STEP)


@pytest.mark.asyncio
async def test_agent_step_executor_refuses_a_non_agent_step() -> None:
    executor = AgentStepExecutor(_registry_with(EchoAgent()))

    with pytest.raises(ValueError, match="tool"):
        await executor.execute(_TOOL_STEP)


@pytest.mark.asyncio
async def test_agent_step_executor_raises_for_an_unregistered_agent_id() -> None:
    executor = AgentStepExecutor(InMemoryAgentRegistry({}))

    with pytest.raises(AgentNotRegisteredError, match=_AGENT_ID):
        await executor.execute(_AGENT_STEP)


@pytest.mark.asyncio
async def test_agent_step_executor_resolves_different_agents_for_different_steps() -> None:
    other_agent_id = "se.software_engineering/backend-developer"
    other_step = WorkflowStep(id="implement", type=StepType.AGENT, agent_id=other_agent_id)
    registry = InMemoryAgentRegistry(
        {_AGENT_ID: _NamedAgent("analyst"), other_agent_id: _NamedAgent("backend-developer")}
    )
    executor = AgentStepExecutor(registry)

    first = await executor.execute(_AGENT_STEP)
    second = await executor.execute(other_step)

    assert first == {"ranAs": "analyst"}
    assert second == {"ranAs": "backend-developer"}


@pytest.mark.asyncio
async def test_agent_step_executor_passes_no_inputs_when_the_step_declares_none() -> None:
    agent = _InputCapturingAgent()
    executor = AgentStepExecutor(_registry_with(agent))

    await executor.execute(_AGENT_STEP)

    assert agent.received_inputs == {"stepId": _AGENT_STEP.id, "agentId": _AGENT_ID}


@pytest.mark.asyncio
async def test_agent_step_executor_forwards_the_declared_invocation_fields_as_inputs() -> None:
    step = WorkflowStep(
        id="analyze_with_prompt",
        type=StepType.AGENT,
        agent_id=_AGENT_ID,
        prompt_id="prompt_greeting",
        prompt_version="1.0.0",
        model_alias="fast-cheap",
    )
    agent = _InputCapturingAgent()
    executor = AgentStepExecutor(_registry_with(agent))

    await executor.execute(step)

    assert agent.received_inputs == {
        "stepId": "analyze_with_prompt",
        "agentId": _AGENT_ID,
        "promptId": "prompt_greeting",
        "promptVersion": "1.0.0",
        "modelAlias": "fast-cheap",
    }


@pytest.mark.asyncio
async def test_agent_step_executor_forwards_only_the_fields_a_step_actually_declares() -> None:
    step = WorkflowStep(
        id="analyze_with_alias_only",
        type=StepType.AGENT,
        agent_id=_AGENT_ID,
        model_alias="fast-cheap",
    )
    agent = _InputCapturingAgent()
    executor = AgentStepExecutor(_registry_with(agent))

    await executor.execute(step)

    assert agent.received_inputs == {
        "stepId": "analyze_with_alias_only",
        "agentId": _AGENT_ID,
        "modelAlias": "fast-cheap",
    }


@pytest.mark.asyncio
async def test_agent_step_executor_forwards_workflow_id_only_when_the_caller_supplies_one() -> None:
    agent = _InputCapturingAgent()
    executor = AgentStepExecutor(_registry_with(agent))

    await executor.execute(_AGENT_STEP, workflow_id="wf_real")

    assert agent.received_inputs == {
        "stepId": _AGENT_STEP.id,
        "agentId": _AGENT_ID,
        "workflowId": "wf_real",
    }


class _FakeContextManager:
    """Records every request it was asked to assemble; always returns
    the same fixed AssembledContext."""

    def __init__(self, result: AssembledContext) -> None:
        self._result = result
        self.requests: list[ContextRequest] = []

    async def assemble(self, request: ContextRequest) -> AssembledContext:
        self.requests.append(request)
        return self._result


def _empty_context(assembly_id: str = "asm_test") -> AssembledContext:
    return AssembledContext(
        items=[],
        total_tokens=0,
        sources_queried=[],
        items_excluded_count=0,
        assembly_id=assembly_id,
    )


@pytest.mark.asyncio
async def test_no_context_manager_configured_never_adds_a_context_key() -> None:
    agent = _InputCapturingAgent()
    executor = AgentStepExecutor(_registry_with(agent))

    await executor.execute(_AGENT_STEP, workflow_id="wf_1")

    assert agent.received_inputs is not None
    assert "context" not in agent.received_inputs


@pytest.mark.asyncio
async def test_a_context_manager_with_no_workflow_id_never_adds_a_context_key() -> None:
    # Mirrors the "no metadata = skipped, not an error" shape already
    # established for the LLM Gateway's TraceContext-driven checks.
    agent = _InputCapturingAgent()
    context_manager = _FakeContextManager(_empty_context())
    executor = AgentStepExecutor(_registry_with(agent), context_manager=context_manager)

    await executor.execute(_AGENT_STEP)

    assert "context" not in (agent.received_inputs or {})
    assert context_manager.requests == []


@pytest.mark.asyncio
async def test_a_configured_context_manager_with_a_workflow_id_assembles_real_context() -> None:
    agent = _InputCapturingAgent()
    assembled = _empty_context()
    context_manager = _FakeContextManager(assembled)
    executor = AgentStepExecutor(_registry_with(agent), context_manager=context_manager)

    await executor.execute(_AGENT_STEP, workflow_id="wf_1")

    assert agent.received_inputs is not None
    assert agent.received_inputs["context"] is assembled
    assert context_manager.requests == [
        ContextRequest(workflow_id="wf_1", step_id=_AGENT_STEP.id, agent_id=_AGENT_ID)
    ]


@pytest.mark.asyncio
async def test_context_is_assembled_alongside_the_declared_invocation_fields() -> None:
    step = WorkflowStep(
        id="analyze_with_prompt",
        type=StepType.AGENT,
        agent_id=_AGENT_ID,
        prompt_id="prompt_greeting",
        prompt_version="1.0.0",
        model_alias="fast-cheap",
    )
    agent = _InputCapturingAgent()
    assembled = _empty_context()
    context_manager = _FakeContextManager(assembled)
    executor = AgentStepExecutor(_registry_with(agent), context_manager=context_manager)

    await executor.execute(step, workflow_id="wf_1")

    assert agent.received_inputs == {
        "stepId": "analyze_with_prompt",
        "agentId": _AGENT_ID,
        "workflowId": "wf_1",
        "promptId": "prompt_greeting",
        "promptVersion": "1.0.0",
        "modelAlias": "fast-cheap",
        "context": assembled,
    }
