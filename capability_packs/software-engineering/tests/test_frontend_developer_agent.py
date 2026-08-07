"""Deterministic tests for the Frontend Developer Agent — no live LLM
call (ADR-0004: a deterministic Protocol implementation is a legitimate
substitute), but a genuine, non-mocked sandbox: every write in this
file happens through a real ``LocalSubprocessSandbox``/real OS
subprocess, so a passing test means a real file genuinely exists on
disk afterward.

Mirrors ``test_database_agent.py``'s own real substitute exactly.

The real, FR-035-specific proof this file adds beyond ``build.py``'s
own shape: a non-frontend file extension is refused before any sandbox
call, never silently written.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from ai_os_kernel.llm_gateway.gateway import EchoLLMGateway
from ai_os_kernel.prompt_engine.renderer import InMemoryPromptEngine
from ai_os_kernel.sandbox.executor import LocalSubprocessSandbox
from ai_os_kernel.sdk_adapters.pack_context import build_pack_context
from ai_os_kernel.workflow_engine.models import StepType, WorkflowStep
from ai_os_kernel.workflow_engine.registry import InMemoryAgentRegistry
from ai_os_kernel.workflow_engine.step_executor import AgentStepExecutor
from ai_os_pack_software_engineering.agents.frontend_developer import (
    FrontendComponentInput,
    FrontendDeveloperAgentEntrypoint,
    FrontendDeveloperAgentOutput,
    FrontendDeveloperInstructionError,
    _parse_frontend_instruction,
    _resolve_safe_relative_path,
)
from ai_os_sdk.contracts import Agent as SdkAgent
from ai_os_sdk.contracts import PackContextReceiver

_AGENT_ID = "frontend-developer"
_PACK_ID = "software-engineering"
_PACK_VERSION = "0.1.0"
_PROMPT_ID = "frontenddeveloper.write_component"
_PROMPT_VERSION = "0.1.0"


def _agent_with_prompt(
    template: str, *, working_directory: Path | None = None
) -> FrontendDeveloperAgentEntrypoint:
    """The real, zero-arg-constructed (aside from ``working_directory``)
    entrypoint, bound to a real ``PackContext`` — identical construction
    sequence to ``test_database_agent.py``'s own ``_agent_with_prompt``."""
    agent = FrontendDeveloperAgentEntrypoint(working_directory=working_directory)
    agent.bind_pack_context(
        build_pack_context(
            pack_id=_PACK_ID,
            pack_version=_PACK_VERSION,
            permissions=["llm:invoke", "sandbox:execute"],
            llm_gateway=EchoLLMGateway(),
            prompt_engine=InMemoryPromptEngine(templates={(_PROMPT_ID, _PROMPT_VERSION): template}),
            sandbox=LocalSubprocessSandbox(),
        )
    )
    return agent


def _step() -> WorkflowStep:
    return WorkflowStep(
        id="write_component",
        type=StepType.AGENT,
        agent_id=_AGENT_ID,
        prompt_id=_PROMPT_ID,
        prompt_version=_PROMPT_VERSION,
        model_alias="coding-strong",
    )


_COMPONENT_TEMPLATE = (
    "FILE_PATH: src/components/Widget.tsx\n"
    "FILE_CONTENT_BEGIN\n"
    "export function Widget() {\n"
    "  return <div>widget</div>;\n"
    "}\n"
    "FILE_CONTENT_END"
)


def test_frontend_developer_agent_entrypoint_constructs_with_zero_arguments() -> None:
    """The exact call EntrypointLoader/SqlAgentRegistry make in
    production — must succeed instantly, with no I/O."""
    agent = FrontendDeveloperAgentEntrypoint()

    assert agent.output_schema["required"] == [
        "workingDirectory",
        "filePath",
        "written",
        "exitCode",
        "stdout",
        "stderr",
        "instruction",
    ]


def test_the_entrypoint_satisfies_both_sdk_protocols() -> None:
    agent = FrontendDeveloperAgentEntrypoint()

    assert isinstance(agent, SdkAgent)
    assert isinstance(agent, PackContextReceiver)


@pytest.mark.asyncio
async def test_execute_before_bind_pack_context_raises_a_clear_error() -> None:
    agent = FrontendDeveloperAgentEntrypoint()

    with pytest.raises(FrontendDeveloperInstructionError, match="bind_pack_context"):
        await agent.execute(
            {
                "promptId": _PROMPT_ID,
                "promptVersion": _PROMPT_VERSION,
                "modelAlias": "coding-strong",
            }
        )


@pytest.mark.asyncio
async def test_frontend_developer_agent_genuinely_writes_a_real_component_through_the_sandbox(
    tmp_path: Path,
) -> None:
    """A WorkflowStep of type agent, dispatched through the real
    AgentStepExecutor, genuinely results in a real component file
    existing in the sandbox working directory."""
    agent = _agent_with_prompt(_COMPONENT_TEMPLATE, working_directory=tmp_path)
    registry = InMemoryAgentRegistry({_AGENT_ID: agent})
    executor = AgentStepExecutor(registry)

    outputs = await executor.execute(_step())

    FrontendDeveloperAgentOutput.model_validate(outputs)
    assert outputs["written"] is True
    assert outputs["exitCode"] == 0
    written_file = tmp_path / "src" / "components" / "Widget.tsx"
    assert written_file.is_file()
    assert "export function Widget" in written_file.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_frontend_developer_agent_rejects_a_non_frontend_file_extension(
    tmp_path: Path,
) -> None:
    """FR-035's own agent-name scope enforced as a real precondition:
    a completion declaring a non-frontend extension is refused before
    any sandbox call, never silently written."""
    template = (
        "FILE_PATH: src/server.py\nFILE_CONTENT_BEGIN\nprint('not frontend')\nFILE_CONTENT_END"
    )
    agent = _agent_with_prompt(template, working_directory=tmp_path)
    registry = InMemoryAgentRegistry({_AGENT_ID: agent})
    executor = AgentStepExecutor(registry)

    with pytest.raises(FrontendDeveloperInstructionError, match="not a real frontend file"):
        await executor.execute(_step())

    assert await asyncio.to_thread(lambda: list(tmp_path.rglob("*"))) == []


@pytest.mark.asyncio
async def test_frontend_developer_agent_rejects_a_malformed_completion(tmp_path: Path) -> None:
    agent = _agent_with_prompt(
        "this completion follows no documented format at all", working_directory=tmp_path
    )
    registry = InMemoryAgentRegistry({_AGENT_ID: agent})
    executor = AgentStepExecutor(registry)

    with pytest.raises(FrontendDeveloperInstructionError, match="did not follow the documented"):
        await executor.execute(_step())


@pytest.mark.asyncio
async def test_missing_required_invocation_fields_raise_a_clear_error() -> None:
    agent = _agent_with_prompt("unused")

    with pytest.raises(FrontendDeveloperInstructionError, match="promptId"):
        await agent.execute({"modelAlias": "coding-strong"})


def test_parse_frontend_instruction_extracts_path_and_content() -> None:
    completion = "FILE_PATH: a/b.tsx\nFILE_CONTENT_BEGIN\nexport const x = 1;\nFILE_CONTENT_END"

    path, content = _parse_frontend_instruction(completion)

    assert path == "a/b.tsx"
    assert content == "export const x = 1;"


@pytest.mark.parametrize("malicious_path", ["../../outside.tsx", "/etc/passwd"])
def test_resolve_safe_relative_path_rejects_paths_that_escape_the_working_directory(
    tmp_path: Path, malicious_path: str
) -> None:
    with pytest.raises(FrontendDeveloperInstructionError, match="resolves outside"):
        _resolve_safe_relative_path(tmp_path, malicious_path)


def test_frontend_component_input_documents_the_agent_contract() -> None:
    FrontendComponentInput(plan="Implement a Widget component that renders a label.")
