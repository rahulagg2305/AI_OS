"""Unit tests for DispatchingStepExecutor's three-way routing — fake
executors throughout, isolating the dispatch logic itself from what
any real executor does (ADR-0004: interface-driven)."""

from typing import Any

import pytest

from ai_os_kernel.workflow_engine.models import StepType, WorkflowStep
from ai_os_kernel.workflow_engine.step_executor import DispatchingStepExecutor

_AGENT_STEP = WorkflowStep(
    id="analyze_requirements", type=StepType.AGENT, agent_id="se.software_engineering/analyst"
)
_TOOL_STEP = WorkflowStep(id="run_build", type=StepType.TOOL, tool_id="se.build")
_OTHER_STEP = WorkflowStep(id="approve_release", type=StepType.HUMAN_APPROVAL)


class _FakeStepExecutor:
    def __init__(self, label: str) -> None:
        self._label = label
        self.executed_steps: list[WorkflowStep] = []
        self.received_workflow_ids: list[str | None] = []

    async def execute(
        self, step: WorkflowStep, *, workflow_id: str | None = None
    ) -> dict[str, Any]:
        self.executed_steps.append(step)
        self.received_workflow_ids.append(workflow_id)
        return {"handled_by": self._label}


def _dispatcher() -> tuple[
    DispatchingStepExecutor, _FakeStepExecutor, _FakeStepExecutor, _FakeStepExecutor
]:
    agent_executor = _FakeStepExecutor("agent")
    tool_executor = _FakeStepExecutor("tool")
    default_executor = _FakeStepExecutor("default")
    dispatcher = DispatchingStepExecutor(agent_executor, tool_executor, default_executor)
    return dispatcher, agent_executor, tool_executor, default_executor


@pytest.mark.asyncio
async def test_agent_steps_are_routed_to_the_agent_executor_only() -> None:
    dispatcher, agent_executor, tool_executor, default_executor = _dispatcher()

    outputs = await dispatcher.execute(_AGENT_STEP)

    assert outputs == {"handled_by": "agent"}
    assert agent_executor.executed_steps == [_AGENT_STEP]
    assert tool_executor.executed_steps == []
    assert default_executor.executed_steps == []


@pytest.mark.asyncio
async def test_tool_steps_are_routed_to_the_tool_executor_only() -> None:
    dispatcher, agent_executor, tool_executor, default_executor = _dispatcher()

    outputs = await dispatcher.execute(_TOOL_STEP)

    assert outputs == {"handled_by": "tool"}
    assert tool_executor.executed_steps == [_TOOL_STEP]
    assert agent_executor.executed_steps == []
    assert default_executor.executed_steps == []


@pytest.mark.asyncio
async def test_every_other_step_type_is_routed_to_the_default_executor_only() -> None:
    dispatcher, agent_executor, tool_executor, default_executor = _dispatcher()

    outputs = await dispatcher.execute(_OTHER_STEP)

    assert outputs == {"handled_by": "default"}
    assert default_executor.executed_steps == [_OTHER_STEP]
    assert agent_executor.executed_steps == []
    assert tool_executor.executed_steps == []


@pytest.mark.asyncio
async def test_workflow_id_is_forwarded_to_whichever_executor_handles_the_step() -> None:
    dispatcher, agent_executor, _, _ = _dispatcher()

    await dispatcher.execute(_AGENT_STEP, workflow_id="wf_123")

    assert agent_executor.received_workflow_ids == ["wf_123"]


@pytest.mark.asyncio
async def test_a_missing_workflow_id_forwards_none_not_an_error() -> None:
    dispatcher, agent_executor, _, _ = _dispatcher()

    await dispatcher.execute(_AGENT_STEP)

    assert agent_executor.received_workflow_ids == [None]
