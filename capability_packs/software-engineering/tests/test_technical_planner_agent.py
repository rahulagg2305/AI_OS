"""Deterministic tests for the Technical Planner Agent — no database,
no live LLM call (ADR-0004: a deterministic Protocol implementation is
a legitimate substitute).

``EchoLLMGateway`` echoes the *rendered prompt* verbatim (see that
class's own docstring) — since this agent expects a real JSON task
array back, every test template here is a fixed JSON string, the
identical "the template itself is the expected completion" convention
``test_code_review_agent.py``'s own templates already establish.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from ai_os_kernel.llm_gateway.gateway import EchoLLMGateway
from ai_os_kernel.prompt_engine.renderer import InMemoryPromptEngine
from ai_os_kernel.sdk_adapters.pack_context import build_pack_context
from ai_os_kernel.workflow_engine.models import StepType, WorkflowStep
from ai_os_kernel.workflow_engine.registry import InMemoryAgentRegistry
from ai_os_kernel.workflow_engine.step_executor import AgentStepExecutor
from ai_os_pack_software_engineering.agents.technical_planner import (
    PlanTask,
    TechnicalPlanInput,
    TechnicalPlanInstructionError,
    TechnicalPlannerAgentEntrypoint,
    TechnicalPlanOutput,
    _parse_tasks,
)
from ai_os_sdk.contracts import Agent as SdkAgent
from ai_os_sdk.contracts import PackContextReceiver

_AGENT_ID = "technical-planner"
_PACK_ID = "software-engineering"
_PACK_VERSION = "0.1.0"
_PROMPT_ID = "technicalplanning.produce_plan"
_PROMPT_VERSION = "0.1.0"

_TWO_TASKS = json.dumps(
    [
        {"title": "Build the API layer", "description": "Implement the REST endpoints."},
        {"title": "Build the storage layer", "description": "Implement the persistence model."},
    ]
)
_NO_TASKS: str = json.dumps([])


def _agent_with_prompt(template: str) -> TechnicalPlannerAgentEntrypoint:
    """The real, zero-arg-constructed entrypoint, bound to a real
    ``PackContext`` granting exactly ``llm:invoke`` over a real,
    Echo-backed gateway — the identical construction sequence
    ``test_architecture_agent.py``'s own ``_agent_with_prompt``
    establishes."""
    agent = TechnicalPlannerAgentEntrypoint()
    agent.bind_pack_context(
        build_pack_context(
            pack_id=_PACK_ID,
            pack_version=_PACK_VERSION,
            permissions=["llm:invoke"],
            llm_gateway=EchoLLMGateway(),
            prompt_engine=InMemoryPromptEngine(templates={(_PROMPT_ID, _PROMPT_VERSION): template}),
        )
    )
    return agent


def _invocation() -> dict[str, object]:
    return {
        "promptId": _PROMPT_ID,
        "promptVersion": _PROMPT_VERSION,
        "modelAlias": "coding-strong",
        "variables": {"context": "a design for a URL shortener service"},
    }


def test_technical_planner_agent_entrypoint_constructs_with_zero_arguments() -> None:
    agent = TechnicalPlannerAgentEntrypoint()

    assert agent.output_schema["required"] == ["tasks"]


def test_the_entrypoint_satisfies_both_sdk_protocols() -> None:
    agent = TechnicalPlannerAgentEntrypoint()

    assert isinstance(agent, SdkAgent)
    assert isinstance(agent, PackContextReceiver)


@pytest.mark.asyncio
async def test_execute_before_bind_pack_context_raises_a_clear_error() -> None:
    agent = TechnicalPlannerAgentEntrypoint()

    with pytest.raises(TechnicalPlanInstructionError, match="bind_pack_context"):
        await agent.execute(_invocation())


@pytest.mark.asyncio
async def test_technical_planner_agent_returns_a_real_schema_validated_plan_artifact() -> None:
    """The real proof this agent exists for: the model's own real JSON
    completion becomes a real, validated plan artifact — each task
    carrying a real, deterministically-assigned ``taskId`` never
    trusted from the model."""
    agent = _agent_with_prompt(_TWO_TASKS)

    outputs = await agent.execute(_invocation())

    TechnicalPlanOutput.model_validate(outputs)
    assert len(outputs["tasks"]) == 2
    assert outputs["tasks"][0]["taskId"] == "task-1"
    assert outputs["tasks"][0]["title"] == "Build the API layer"
    assert outputs["tasks"][1]["taskId"] == "task-2"
    assert outputs["tasks"][1]["description"] == "Implement the persistence model."


@pytest.mark.asyncio
async def test_technical_planner_agent_returns_an_empty_plan_for_a_trivial_design() -> None:
    agent = _agent_with_prompt(_NO_TASKS)

    outputs = await agent.execute(_invocation())

    assert outputs["tasks"] == []


@pytest.mark.asyncio
async def test_technical_planner_agent_rejects_a_non_json_completion() -> None:
    agent = _agent_with_prompt("this is not json at all")

    with pytest.raises(TechnicalPlanInstructionError, match="not valid JSON"):
        await agent.execute(_invocation())


@pytest.mark.asyncio
async def test_technical_planner_agent_rejects_a_non_array_completion() -> None:
    agent = _agent_with_prompt(json.dumps({"title": "not an array"}))

    with pytest.raises(TechnicalPlanInstructionError, match="not a JSON array"):
        await agent.execute(_invocation())


@pytest.mark.asyncio
async def test_technical_planner_agent_rejects_a_task_missing_a_required_field() -> None:
    bad = json.dumps([{"title": "only a title"}])
    agent = _agent_with_prompt(bad)

    with pytest.raises(TechnicalPlanInstructionError, match="did not match the documented"):
        await agent.execute(_invocation())


@pytest.mark.asyncio
async def test_missing_required_invocation_fields_raise_a_clear_error() -> None:
    agent = _agent_with_prompt(_NO_TASKS)

    with pytest.raises(TechnicalPlanInstructionError, match="promptId"):
        await agent.execute({"modelAlias": "coding-strong"})


@pytest.mark.asyncio
async def test_concurrent_execute_calls_all_succeed_independently() -> None:
    agent = _agent_with_prompt(_TWO_TASKS)

    results = await asyncio.gather(*(agent.execute(_invocation()) for _ in range(5)))

    assert all(len(r["tasks"]) == 2 for r in results)


@pytest.mark.asyncio
async def test_technical_planner_agent_dispatches_through_agent_step_executor() -> None:
    """The real end-to-end proof this step exists for: a real
    WorkflowStep of type agent, dispatched through the real
    AgentStepExecutor — the identical dispatch chain every other agent
    in this pack's own test suite proves."""
    registry = InMemoryAgentRegistry({_AGENT_ID: _agent_with_prompt(_TWO_TASKS)})
    executor = AgentStepExecutor(registry)
    step = WorkflowStep(
        id="produce_plan",
        type=StepType.AGENT,
        agent_id=_AGENT_ID,
        prompt_id=_PROMPT_ID,
        prompt_version=_PROMPT_VERSION,
        model_alias="coding-strong",
    )

    outputs = await executor.execute(step)

    TechnicalPlanOutput.model_validate(outputs)
    assert len(outputs["tasks"]) == 2


def test_parse_tasks_assigns_deterministic_task_ids() -> None:
    tasks = _parse_tasks(_TWO_TASKS)

    assert tasks == [
        PlanTask(
            task_id="task-1",
            title="Build the API layer",
            description="Implement the REST endpoints.",
        ),
        PlanTask(
            task_id="task-2",
            title="Build the storage layer",
            description="Implement the persistence model.",
        ),
    ]


def test_technical_plan_input_documents_the_agent_contract() -> None:
    TechnicalPlanInput.model_validate({"design": "A design for a URL shortener service."})
