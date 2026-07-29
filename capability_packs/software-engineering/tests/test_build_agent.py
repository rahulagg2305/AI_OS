"""Deterministic tests for the Build Agent — no database, no live LLM
call (ADR-0004: a deterministic Protocol implementation is a legitimate
substitute), but a genuine, non-mocked sandbox: every write in this
file happens through a real ``LocalSubprocessSandbox``/real OS
subprocess, so a passing test means a real file genuinely exists on
disk afterward, not an assertion about a mock's call arguments.

**Migrated onto the Platform SDK (step 12) — this agent no longer takes
``service_factory``/``sandbox`` constructor overrides, and there is no
more LLM-service lazy build to race against.** ``_agent_with_prompt``
below is this file's own real substitute: construct the agent with zero
arguments (exactly as ``EntrypointLoader`` does, aside from
``working_directory``, still a legitimate constructor override — see
this agent's own module docstring for why), then bind it a real
``PackContext`` built over whichever ``LLMGateway``/``PromptEngine``/
sandbox a test wants, via the exact ``build_pack_context``/
``bind_pack_context`` mechanism a real caller uses — the identical
pattern steps 9-11 already established. ``LocalSubprocessSandbox()`` is
still passed explicitly, now to ``build_pack_context``'s own ``sandbox``
parameter rather than to this entrypoint's own constructor, deliberately
opting back into the fast, Docker-independent backend rather than
requiring a real daemon for tests whose whole point is speed and
determinism. The real, Docker-gated proof of this agent running through
`DockerSandbox` lives in
``tests/integration/sandbox/test_delivery_pipeline_docker.py``.

The lock this agent still keeps (unlike ``requirements-analyst``/
``architecture``, which dropped theirs entirely) guards only lazy
working-directory creation, not any LLM composition — see this agent's
own module docstring for the full reasoning, and
``test_concurrent_execute_calls_share_one_working_directory`` below for
the proof.

The opt-in live proof (a real LLM producing a real, novel file-write
instruction) lives under the Kernel's own
``tests/integration/workflow_engine/test_build_agent_pack.py``.
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
from ai_os_pack_software_engineering.agents.build import (
    BuildAgentEntrypoint,
    BuildAgentOutput,
    BuildInstructionError,
    BuildInstructionInput,
    _parse_build_instruction,
    _resolve_safe_relative_path,
)
from ai_os_sdk.contracts import Agent as SdkAgent
from ai_os_sdk.contracts import PackContextReceiver

_AGENT_ID = "build"
_PACK_ID = "software-engineering"
_PACK_VERSION = "0.1.0"
_PROMPT_ID = "build.write_file"
_PROMPT_VERSION = "0.1.0"


def _agent_with_prompt(
    template: str, *, working_directory: Path | None = None
) -> BuildAgentEntrypoint:
    """The real, zero-arg-constructed (aside from ``working_directory``)
    entrypoint, bound to a real ``PackContext`` granting exactly
    ``llm:invoke`` + ``sandbox:execute`` over a real, Echo-backed
    gateway, an in-memory prompt engine seeded with ``template``, and a
    real ``LocalSubprocessSandbox`` — the same construction+injection
    sequence a real ``SqlAgentRegistry``-backed caller would perform.
    No ``python_command`` to supply any more (step 12a) — the real,
    genuinely portable interpreter invocation is now resolved by
    ``ToolInvokerAdapter`` itself, from the same ``LocalSubprocessSandbox``
    instance this test hands to ``build_pack_context``, automatically."""
    agent = BuildAgentEntrypoint(working_directory=working_directory)
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
        id="write_file",
        type=StepType.AGENT,
        agent_id=_AGENT_ID,
        prompt_id=_PROMPT_ID,
        prompt_version=_PROMPT_VERSION,
        model_alias="coding-strong",
    )


def test_build_agent_entrypoint_constructs_with_zero_arguments() -> None:
    """The exact call EntrypointLoader/SqlAgentRegistry make in
    production — must succeed instantly, with no I/O: no sandbox
    working directory is created until the first `execute()` call."""
    agent = BuildAgentEntrypoint()

    assert agent.output_schema["required"] == [
        "workingDirectory",
        "filePath",
        "written",
        "exitCode",
        "stdout",
        "stderr",
        "instruction",
    ]


def test_the_migrated_entrypoint_satisfies_both_sdk_protocols() -> None:
    """Step 12's own real proof: this entrypoint is a real
    ai_os_sdk.contracts.Agent and PackContextReceiver, not merely an
    object that happens to still work."""
    agent = BuildAgentEntrypoint()

    assert isinstance(agent, SdkAgent)
    assert isinstance(agent, PackContextReceiver)


@pytest.mark.asyncio
async def test_execute_before_bind_pack_context_raises_a_clear_error() -> None:
    """The one real, new behavior this migration adds: a caller that
    forgets to inject a PackContext gets a clear, named error."""
    agent = BuildAgentEntrypoint()

    with pytest.raises(BuildInstructionError, match="bind_pack_context"):
        await agent.execute(
            {
                "promptId": _PROMPT_ID,
                "promptVersion": _PROMPT_VERSION,
                "modelAlias": "coding-strong",
            }
        )


@pytest.mark.asyncio
async def test_build_agent_genuinely_writes_a_real_file_through_the_sandbox(
    tmp_path: Path,
) -> None:
    """The real end-to-end proof this step exists for: a WorkflowStep
    of type agent, dispatched through the real AgentStepExecutor,
    genuinely results in a real file existing in the sandbox working
    directory afterward, with content traceable to the model's own
    completion (here, EchoLLMGateway's real echo of a real rendered
    prompt — not asserted by inspection), written through the new
    ToolInvoker sandbox path (context.tools.invoke), not a directly
    constructed SandboxedCommandTool."""
    template = (
        "FILE_PATH: hello.txt\n"
        "FILE_CONTENT_BEGIN\n"
        "print('hello from the build agent')\n"
        "FILE_CONTENT_END"
    )
    agent = _agent_with_prompt(template, working_directory=tmp_path)
    registry = InMemoryAgentRegistry({_AGENT_ID: agent})
    executor = AgentStepExecutor(registry)

    outputs = await executor.execute(_step())

    BuildAgentOutput.model_validate(outputs)
    assert outputs["workingDirectory"] == str(tmp_path)
    assert outputs["filePath"] == "hello.txt"
    assert outputs["written"] is True
    assert outputs["exitCode"] == 0
    written_file = tmp_path / "hello.txt"
    assert written_file.is_file()
    assert written_file.read_text(encoding="utf-8") == "print('hello from the build agent')"
    assert "print('hello from the build agent')" in outputs["instruction"]


@pytest.mark.asyncio
async def test_build_agent_creates_a_nested_path_relative_to_the_working_directory(
    tmp_path: Path,
) -> None:
    template = "FILE_PATH: src/app.py\nFILE_CONTENT_BEGIN\ndef main():\n    pass\nFILE_CONTENT_END"
    agent = _agent_with_prompt(template, working_directory=tmp_path)
    registry = InMemoryAgentRegistry({_AGENT_ID: agent})
    executor = AgentStepExecutor(registry)

    outputs = await executor.execute(_step())

    assert outputs["written"] is True
    written_file = tmp_path / "src" / "app.py"
    assert written_file.is_file()
    assert written_file.read_text(encoding="utf-8") == "def main():\n    pass"


@pytest.mark.asyncio
async def test_build_agent_lazily_creates_its_own_working_directory_when_none_supplied() -> None:
    """No per-workflow workspace exists yet — see this agent's own
    module docstring. Without an explicit working_directory, the agent
    creates a real, private one of its own on first use."""
    template = "FILE_PATH: note.txt\nFILE_CONTENT_BEGIN\nhello\nFILE_CONTENT_END"
    agent = _agent_with_prompt(template)
    registry = InMemoryAgentRegistry({_AGENT_ID: agent})
    executor = AgentStepExecutor(registry)

    outputs = await executor.execute(_step())

    assert outputs["written"] is True
    written_file = Path(outputs["workingDirectory"]) / "note.txt"
    assert written_file.is_file()
    assert written_file.read_text(encoding="utf-8") == "hello"


@pytest.mark.asyncio
async def test_concurrent_execute_calls_share_one_working_directory() -> None:
    """The real proof behind this agent's own module docstring claim:
    the lock is not fully obsolete here — it still guards concurrent
    first-execute() calls from each independently creating their own,
    unrelated working directory. Five concurrent calls, no explicit
    working_directory, must all land in the identical directory."""
    template = "FILE_PATH: {{context}}.txt\nFILE_CONTENT_BEGIN\nx\nFILE_CONTENT_END"
    agent = _agent_with_prompt(template)
    step_inputs = {
        "promptId": _PROMPT_ID,
        "promptVersion": _PROMPT_VERSION,
        "modelAlias": "coding-strong",
        "variables": {},
    }

    async def _run(index: int) -> dict[str, object]:
        return await agent.execute({**step_inputs, "variables": {"context": f"file{index}"}})

    results = await asyncio.gather(*(_run(i) for i in range(5)))

    working_directories = {r["workingDirectory"] for r in results}
    assert len(working_directories) == 1
    assert all(r["written"] is True for r in results)


@pytest.mark.asyncio
async def test_build_agent_rejects_a_malformed_completion(tmp_path: Path) -> None:
    agent = _agent_with_prompt(
        "this completion follows no documented format at all", working_directory=tmp_path
    )
    registry = InMemoryAgentRegistry({_AGENT_ID: agent})
    executor = AgentStepExecutor(registry)

    with pytest.raises(BuildInstructionError, match="did not follow the documented"):
        await executor.execute(_step())

    assert await asyncio.to_thread(lambda: list(tmp_path.iterdir())) == []


@pytest.mark.asyncio
async def test_missing_required_invocation_fields_raise_a_clear_error() -> None:
    agent = _agent_with_prompt("unused")

    with pytest.raises(BuildInstructionError, match="promptId"):
        await agent.execute({"modelAlias": "coding-strong"})


@pytest.mark.parametrize("malicious_path", ["../../outside.txt", "/etc/passwd"])
def test_resolve_safe_relative_path_rejects_paths_that_escape_the_working_directory(
    tmp_path: Path, malicious_path: str
) -> None:
    with pytest.raises(BuildInstructionError, match="resolves outside"):
        _resolve_safe_relative_path(tmp_path, malicious_path)


def test_resolve_safe_relative_path_rejects_a_blank_path(tmp_path: Path) -> None:
    with pytest.raises(BuildInstructionError, match="must not be blank"):
        _resolve_safe_relative_path(tmp_path, "   ")


def test_resolve_safe_relative_path_accepts_a_genuinely_nested_relative_path(
    tmp_path: Path,
) -> None:
    result = _resolve_safe_relative_path(tmp_path, "src/app.py")

    assert result == Path("src/app.py")


def test_parse_build_instruction_extracts_path_and_content() -> None:
    completion = "FILE_PATH: a/b.txt\nFILE_CONTENT_BEGIN\nline one\nline two\nFILE_CONTENT_END"

    path, content = _parse_build_instruction(completion)

    assert path == "a/b.txt"
    assert content == "line one\nline two"


def test_parse_build_instruction_raises_a_clear_error_for_an_unparseable_completion() -> None:
    with pytest.raises(BuildInstructionError, match="did not follow the documented"):
        _parse_build_instruction("no markers here at all")


def test_build_instruction_input_documents_the_agent_contract() -> None:
    BuildInstructionInput(instruction="Write a hello-world script.")
