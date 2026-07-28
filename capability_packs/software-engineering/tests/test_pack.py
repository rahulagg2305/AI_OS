"""Deterministic tests for this pack's own entry points — no database,
no live LLM call (ADR-0004: a fake/deterministic Protocol implementation
is a legitimate substitute; the same shape this Kernel's own test suite
uses throughout).

The end-to-end proof that this pack is genuinely registered, activated,
and resolved through the real ``SqlAgentRegistry`` and dispatches a
real (or, for CI, Echo-backed) command through the real
``AgentStepExecutor`` lives under the Kernel's own
``tests/integration/workflow_engine/test_architecture_agent_pack.py`` —
this file only proves this pack's own code in isolation.
"""

from __future__ import annotations

import asyncio

import pytest

from ai_os_kernel.capability_manager.pack_contract import PackContext
from ai_os_kernel.llm_gateway.gateway import EchoLLMGateway
from ai_os_kernel.prompt_engine.renderer import InMemoryPromptEngine
from ai_os_kernel.prompted_completion import PromptedCompletionService
from ai_os_kernel.workflow_engine.models import StepType, WorkflowStep
from ai_os_kernel.workflow_engine.registry import InMemoryAgentRegistry
from ai_os_kernel.workflow_engine.step_executor import AgentStepExecutor
from ai_os_pack_software_engineering.agents.architecture import (
    ArchitectureAgentEntrypoint,
    ArchitectureProposalInput,
    ArchitectureProposalOutput,
)
from ai_os_pack_software_engineering.pack import SoftwareEngineeringPack

_AGENT_ID = "architecture"
_PROMPT_ID = "architecture.propose_design"
_PROMPT_VERSION = "0.1.0"


async def _deterministic_service(template: str) -> PromptedCompletionService:
    return PromptedCompletionService(
        prompt_engine=InMemoryPromptEngine({(_PROMPT_ID, _PROMPT_VERSION): template}),
        llm_gateway=EchoLLMGateway(),
    )


@pytest.mark.asyncio
async def test_activate_registers_the_architecture_agent() -> None:
    pack = SoftwareEngineeringPack()

    registration = await pack.activate(PackContext(pack_id=pack.pack_id, pack_version=pack.version))

    assert set(registration.agents) == {"architecture"}
    assert isinstance(registration.agents["architecture"], ArchitectureAgentEntrypoint)


@pytest.mark.asyncio
async def test_deactivate_and_health_are_real_and_honest() -> None:
    pack = SoftwareEngineeringPack()

    await pack.deactivate()
    report = await pack.health()

    assert report.status == "healthy"


def test_architecture_agent_entrypoint_constructs_with_zero_arguments() -> None:
    """The exact call EntrypointLoader/SqlAgentRegistry make in
    production — must succeed instantly, with no I/O, proving the lazy
    design genuinely defers async composition rather than doing it
    eagerly in __init__."""
    agent = ArchitectureAgentEntrypoint()

    assert agent.output_schema == {
        "type": "object",
        "properties": {"content": {"type": "string"}},
        "required": ["content"],
        "additionalProperties": False,
    }


@pytest.mark.asyncio
async def test_execute_lazily_builds_exactly_one_service_even_under_concurrent_calls() -> None:
    build_count = 0

    async def counting_factory() -> PromptedCompletionService:
        nonlocal build_count
        build_count += 1
        return await _deterministic_service("Propose an architecture for: {{context}}")

    agent = ArchitectureAgentEntrypoint(service_factory=counting_factory)
    step_inputs = {
        "promptId": _PROMPT_ID,
        "promptVersion": _PROMPT_VERSION,
        "modelAlias": "coding-strong",
        "variables": {"context": "a URL shortener service"},
    }

    results = await asyncio.gather(*(agent.execute(step_inputs) for _ in range(5)))

    assert build_count == 1
    assert all(
        r["content"] == "Propose an architecture for: a URL shortener service" for r in results
    )


@pytest.mark.asyncio
async def test_architecture_agent_genuinely_dispatches_through_agent_step_executor() -> None:
    """The real dispatch chain this pack's own agent is meant to serve
    — WorkflowStep -> AgentStepExecutor -> this entrypoint -> a real
    PromptedAgent -> real prompt rendering -> a deterministic
    (EchoLLMGateway) completion — proving genuine end-to-end behaviour
    without a live network call or a database."""

    async def factory() -> PromptedCompletionService:
        return await _deterministic_service("Propose a concrete architecture.")

    agent = ArchitectureAgentEntrypoint(service_factory=factory)
    registry = InMemoryAgentRegistry({_AGENT_ID: agent})
    executor = AgentStepExecutor(registry)
    step = WorkflowStep(
        id="propose_architecture",
        type=StepType.AGENT,
        agent_id=_AGENT_ID,
        prompt_id=_PROMPT_ID,
        prompt_version=_PROMPT_VERSION,
        model_alias="coding-strong",
    )

    outputs = await executor.execute(step)

    ArchitectureProposalOutput.model_validate(outputs)
    assert outputs["content"] == "Propose a concrete architecture."


def test_input_and_output_models_document_the_agent_contract() -> None:
    ArchitectureProposalInput(requirement="Build a URL shortener service.")
    ArchitectureProposalOutput(content="A design proposal.")
