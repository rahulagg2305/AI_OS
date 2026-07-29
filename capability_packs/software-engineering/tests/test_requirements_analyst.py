"""Deterministic tests for the Requirements Analyst Agent — no
database, no live LLM call (ADR-0004: a deterministic Protocol
implementation is a legitimate substitute), no sandbox (this agent
writes nothing to disk — see its own module docstring).

**Migrated onto the Platform SDK (step 10) — this agent no longer takes
a ``service_factory`` constructor override, and there is no more lazy
build to race against.** ``_agent_with_llm`` below is this file's own
real substitute: construct the agent with zero arguments (exactly as
``EntrypointLoader`` does), then bind it a real ``PackContext`` built
over whichever ``LLMGateway``/``PromptEngine`` a test wants, via the
exact ``build_pack_context``/``bind_pack_context`` mechanism a real
caller uses — the identical pattern step 9's own
``test_verification_agent.py`` migration established for ``qa-test``.

The opt-in live proof (a real LLM producing a real requirements
analysis) lives under the Kernel's own
``tests/integration/workflow_engine/test_requirements_analyst_agent_pack.py``.
"""

from __future__ import annotations

import asyncio

import pytest

from ai_os_kernel.llm_gateway.gateway import EchoLLMGateway
from ai_os_kernel.prompt_engine.renderer import InMemoryPromptEngine
from ai_os_kernel.sdk_adapters.pack_context import build_pack_context
from ai_os_kernel.workflow_engine.models import StepType, WorkflowStep
from ai_os_kernel.workflow_engine.registry import InMemoryAgentRegistry
from ai_os_kernel.workflow_engine.step_executor import AgentStepExecutor
from ai_os_pack_software_engineering.agents.requirements_analyst import (
    RequirementsAnalysisInput,
    RequirementsAnalysisOutput,
    RequirementsAnalystAgentEntrypoint,
    RequirementsAnalystInputError,
)
from ai_os_sdk.contracts import Agent as SdkAgent
from ai_os_sdk.contracts import PackContextReceiver

_AGENT_ID = "requirements-analyst"
_PACK_ID = "software-engineering"
_PACK_VERSION = "0.1.0"
_PROMPT_ID = "requirements.analyze"
_PROMPT_VERSION = "0.1.0"


def _agent_with_prompt(template: str) -> RequirementsAnalystAgentEntrypoint:
    """The real, zero-arg-constructed entrypoint, bound to a real
    ``PackContext`` granting exactly ``llm:invoke`` over a real,
    Echo-backed gateway and an in-memory prompt engine seeded with
    ``template`` — the same construction+injection sequence a real
    ``SqlAgentRegistry``-backed caller would perform."""
    agent = RequirementsAnalystAgentEntrypoint()
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


def test_requirements_analyst_entrypoint_constructs_with_zero_arguments() -> None:
    """The exact call EntrypointLoader/SqlAgentRegistry make in
    production — must succeed instantly, with no I/O."""
    agent = RequirementsAnalystAgentEntrypoint()

    assert agent.output_schema == {
        "type": "object",
        "properties": {"analysis": {"type": "string"}},
        "required": ["analysis"],
        "additionalProperties": False,
    }


def test_the_migrated_entrypoint_satisfies_both_sdk_protocols() -> None:
    """Step 10's own real proof: this entrypoint is a real
    ai_os_sdk.contracts.Agent and PackContextReceiver, not merely an
    object that happens to still work."""
    agent = RequirementsAnalystAgentEntrypoint()

    assert isinstance(agent, SdkAgent)
    assert isinstance(agent, PackContextReceiver)


@pytest.mark.asyncio
async def test_execute_before_bind_pack_context_raises_a_clear_error() -> None:
    """The one real, new behavior this migration adds: a caller that
    forgets to inject a PackContext gets a clear, named error."""
    agent = RequirementsAnalystAgentEntrypoint()

    with pytest.raises(RequirementsAnalystInputError, match="bind_pack_context"):
        await agent.execute(
            {
                "promptId": _PROMPT_ID,
                "promptVersion": _PROMPT_VERSION,
                "modelAlias": "coding-strong",
            }
        )


@pytest.mark.asyncio
async def test_concurrent_execute_calls_all_succeed_independently() -> None:
    """The lazy-build lock this agent used to need is gone entirely —
    see this module's own docstring. This test proves concurrent
    execute() calls still all genuinely succeed with correct,
    independent results, now that there is no shared build state to
    race over at all."""
    agent = _agent_with_prompt("Analyze this requirement: {{context}}")
    step_inputs = {
        "promptId": _PROMPT_ID,
        "promptVersion": _PROMPT_VERSION,
        "modelAlias": "coding-strong",
        "variables": {"context": "a URL shortener service"},
    }

    results = await asyncio.gather(*(agent.execute(step_inputs) for _ in range(5)))

    assert all(
        r["analysis"] == "Analyze this requirement: a URL shortener service" for r in results
    )


@pytest.mark.asyncio
async def test_requirements_analyst_genuinely_dispatches_through_agent_step_executor() -> None:
    """The real dispatch chain this pack's own agent is meant to serve
    — WorkflowStep -> AgentStepExecutor -> this entrypoint -> real
    prompt rendering -> a deterministic (EchoLLMGateway) completion —
    proving genuine end-to-end behaviour without a live network call or
    a database."""
    agent = _agent_with_prompt("Produce a requirements analysis.")
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


@pytest.mark.asyncio
async def test_missing_required_invocation_fields_raise_a_clear_error() -> None:
    agent = _agent_with_prompt("unused")

    with pytest.raises(RequirementsAnalystInputError, match="promptId"):
        await agent.execute({"modelAlias": "coding-strong"})


def test_input_and_output_models_document_the_agent_contract() -> None:
    RequirementsAnalysisInput(requirement="Build a URL shortener service.")
    RequirementsAnalysisOutput(analysis="A requirements analysis.")
