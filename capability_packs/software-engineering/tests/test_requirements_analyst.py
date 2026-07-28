"""Deterministic tests for the Requirements Analyst Agent — no
database, no live LLM call (ADR-0004: a deterministic Protocol
implementation is a legitimate substitute), no sandbox (this agent
writes nothing to disk — see its own module docstring).

The opt-in live proof (a real LLM producing a real requirements
analysis) lives under the Kernel's own
``tests/integration/workflow_engine/test_requirements_analyst_agent_pack.py``.
"""

from __future__ import annotations

import asyncio

import pytest

from ai_os_kernel.llm_gateway.gateway import EchoLLMGateway
from ai_os_kernel.prompt_engine.renderer import InMemoryPromptEngine
from ai_os_kernel.prompted_completion import PromptedCompletionService
from ai_os_kernel.workflow_engine.models import StepType, WorkflowStep
from ai_os_kernel.workflow_engine.registry import InMemoryAgentRegistry
from ai_os_kernel.workflow_engine.step_executor import AgentStepExecutor
from ai_os_pack_software_engineering.agents.requirements_analyst import (
    RequirementsAnalysisInput,
    RequirementsAnalysisOutput,
    RequirementsAnalystAgentEntrypoint,
)

_AGENT_ID = "requirements-analyst"
_PROMPT_ID = "requirements.analyze"
_PROMPT_VERSION = "0.1.0"


async def _deterministic_service(template: str) -> PromptedCompletionService:
    return PromptedCompletionService(
        prompt_engine=InMemoryPromptEngine({(_PROMPT_ID, _PROMPT_VERSION): template}),
        llm_gateway=EchoLLMGateway(),
    )


def test_requirements_analyst_entrypoint_constructs_with_zero_arguments() -> None:
    """The exact call EntrypointLoader/SqlAgentRegistry make in
    production — must succeed instantly, with no I/O, proving the lazy
    design genuinely defers async composition rather than doing it
    eagerly in __init__."""
    agent = RequirementsAnalystAgentEntrypoint()

    assert agent.output_schema == {
        "type": "object",
        "properties": {"analysis": {"type": "string"}},
        "required": ["analysis"],
        "additionalProperties": False,
    }


@pytest.mark.asyncio
async def test_execute_lazily_builds_exactly_one_service_even_under_concurrent_calls() -> None:
    build_count = 0

    async def counting_factory() -> PromptedCompletionService:
        nonlocal build_count
        build_count += 1
        return await _deterministic_service("Analyze this requirement: {{context}}")

    agent = RequirementsAnalystAgentEntrypoint(service_factory=counting_factory)
    step_inputs = {
        "promptId": _PROMPT_ID,
        "promptVersion": _PROMPT_VERSION,
        "modelAlias": "coding-strong",
        "variables": {"context": "a URL shortener service"},
    }

    results = await asyncio.gather(*(agent.execute(step_inputs) for _ in range(5)))

    assert build_count == 1
    assert all(
        r["analysis"] == "Analyze this requirement: a URL shortener service" for r in results
    )


@pytest.mark.asyncio
async def test_requirements_analyst_genuinely_dispatches_through_agent_step_executor() -> None:
    """The real dispatch chain this pack's own agent is meant to serve
    — WorkflowStep -> AgentStepExecutor -> this entrypoint -> a real
    PromptedAgent -> real prompt rendering -> a deterministic
    (EchoLLMGateway) completion — proving genuine end-to-end behaviour
    without a live network call or a database."""

    async def factory() -> PromptedCompletionService:
        return await _deterministic_service("Produce a requirements analysis.")

    agent = RequirementsAnalystAgentEntrypoint(service_factory=factory)
    registry = InMemoryAgentRegistry({_AGENT_ID: agent})
    executor = AgentStepExecutor(registry)
    step = WorkflowStep(
        id="analyze_requirements",
        type=StepType.AGENT,
        agent_id=_AGENT_ID,
        prompt_id=_PROMPT_ID,
        prompt_version=_PROMPT_VERSION,
        model_alias="coding-strong",
    )

    outputs = await executor.execute(step)

    RequirementsAnalysisOutput.model_validate(outputs)
    assert outputs["analysis"] == "Produce a requirements analysis."


def test_input_and_output_models_document_the_agent_contract() -> None:
    RequirementsAnalysisInput(requirement="Build a URL shortener service.")
    RequirementsAnalysisOutput(analysis="A requirements analysis.")
