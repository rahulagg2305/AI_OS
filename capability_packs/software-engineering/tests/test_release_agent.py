"""Deterministic tests for the Release Agent — no database, no live
LLM call (ADR-0004: a deterministic Protocol implementation is a
legitimate substitute), but a genuine, non-mocked sandbox: every write
in this file happens through a real ``LocalSubprocessSandbox``/real OS
subprocess, so a passing test means a real changelog file genuinely
exists on disk afterward.

Mirrors ``test_documentation_agent.py``'s own real substitute exactly
— same six-field payload shape, same `_agent_with_prompt`/
`_FixedPayloadResolver` construction. The real, FR-042-specific proof
this file adds: ``ready`` tracks the caller-supplied ``passed`` exactly
both ways (a genuine pass and a genuine fail), never any judgment about
the LLM's own generated changelog content.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ai_os_kernel.context_manager.manager import DefaultContextManager
from ai_os_kernel.context_manager.models import (
    ContextItem,
    ContextRequest,
    SourceRef,
    SourceType,
)
from ai_os_kernel.llm_gateway.gateway import EchoLLMGateway
from ai_os_kernel.prompt_engine.renderer import InMemoryPromptEngine
from ai_os_kernel.sandbox.executor import LocalSubprocessSandbox
from ai_os_kernel.sdk_adapters.pack_context import build_pack_context
from ai_os_kernel.workflow_engine.models import StepType, WorkflowStep
from ai_os_kernel.workflow_engine.registry import InMemoryAgentRegistry
from ai_os_kernel.workflow_engine.step_executor import AgentStepExecutor
from ai_os_pack_software_engineering.agents.release import (
    ReleaseAgentEntrypoint,
    ReleaseAgentInput,
    ReleaseAgentOutput,
    ReleaseInstructionError,
    _resolve_existing_file,
    _resolve_safe_relative_path,
)
from ai_os_sdk.contracts import Agent as SdkAgent
from ai_os_sdk.contracts import PackContextReceiver

_AGENT_ID = "release"
_PACK_ID = "software-engineering"
_PACK_VERSION = "0.1.0"
_PROMPT_ID = "release.record_changelog"
_PROMPT_VERSION = "0.1.0"
_TEMPLATE = (
    "# Changelog for {{filePath}}\n\n"
    "Instruction: {{instruction}}\n"
    "Passed: {{passed}} (exit {{exitCode}})\n"
    "Output: {{output}}"
)


class _FixedPayloadResolver:
    """A fake `ContextSourceResolver` (ADR-0004: a legitimate test
    substitute) that always returns one item carrying a fixed,
    JSON-encoded build+test payload — the real channel
    `ReleaseAgentEntrypoint` reads from when invoked through a real
    `AgentStepExecutor`."""

    source_type = SourceType.WORKFLOW_STATE

    def __init__(self, payload: dict[str, Any]) -> None:
        self._content = json.dumps(payload)

    async def resolve(self, request: ContextRequest) -> list[ContextItem]:
        return [
            ContextItem(
                content=self._content,
                provenance=SourceRef(source_type=SourceType.WORKFLOW_STATE, identifier="test"),
                relevance_score=1.0,
                token_count=len(self._content),
                trust="trusted",
            )
        ]


def _agent_with_prompt(template: str) -> ReleaseAgentEntrypoint:
    """The real, zero-arg-constructed entrypoint, bound to a real
    ``PackContext`` — identical construction sequence to
    ``test_documentation_agent.py``'s own ``_agent_with_prompt``."""
    agent = ReleaseAgentEntrypoint()
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
        id="record_release",
        type=StepType.AGENT,
        agent_id=_AGENT_ID,
        prompt_id=_PROMPT_ID,
        prompt_version=_PROMPT_VERSION,
        model_alias="coding-strong",
    )


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_release_agent_entrypoint_constructs_with_zero_arguments() -> None:
    agent = ReleaseAgentEntrypoint()

    assert agent.output_schema["required"] == [
        "workingDirectory",
        "changelogPath",
        "written",
        "exitCode",
        "content",
        "ready",
    ]


def test_the_entrypoint_satisfies_both_sdk_protocols() -> None:
    agent = ReleaseAgentEntrypoint()

    assert isinstance(agent, SdkAgent)
    assert isinstance(agent, PackContextReceiver)


@pytest.mark.asyncio
async def test_execute_before_bind_pack_context_raises_a_clear_error() -> None:
    agent = ReleaseAgentEntrypoint()

    with pytest.raises(ReleaseInstructionError, match="bind_pack_context"):
        await agent.execute(
            {
                "promptId": _PROMPT_ID,
                "promptVersion": _PROMPT_VERSION,
                "modelAlias": "coding-strong",
            }
        )


@pytest.mark.asyncio
async def test_release_agent_reports_ready_true_for_a_genuine_passing_build(
    tmp_path: Path,
) -> None:
    """The real proof this agent exists for: `ready` tracks the QA/Test
    Agent's own real `passed` outcome exactly — a genuine pass yields
    a genuine `ready: true`, not an LLM's opinion."""
    _write(tmp_path / "ok.py", "print('all good')\n")
    payload = {
        "workingDirectory": str(tmp_path),
        "filePath": "ok.py",
        "instruction": "Write a script that prints 'all good'.",
        "passed": True,
        "exitCode": 0,
        "output": "all good\n",
    }

    agent = _agent_with_prompt(_TEMPLATE)
    context_manager = DefaultContextManager([_FixedPayloadResolver(payload)])
    registry = InMemoryAgentRegistry({_AGENT_ID: agent})
    executor = AgentStepExecutor(registry, context_manager)

    outputs = await executor.execute(_step(), workflow_id="wf_test")

    ReleaseAgentOutput.model_validate(outputs)
    assert outputs["ready"] is True
    assert outputs["written"] is True
    assert outputs["changelogPath"] == "ok.py.changelog.md"
    written_file = tmp_path / "ok.py.changelog.md"
    assert written_file.is_file()
    changelog_text = written_file.read_text(encoding="utf-8")
    assert changelog_text == outputs["content"]
    assert "ok.py" in changelog_text


@pytest.mark.asyncio
async def test_release_agent_reports_ready_false_for_a_genuine_failing_build(
    tmp_path: Path,
) -> None:
    """The identical dispatch chain, describing a genuinely *failed*
    Test Agent outcome — `ready` must be `false`, not silently `true`,
    and the changelog is still genuinely written (a release decision
    still gets recorded, even a negative one)."""
    _write(tmp_path / "broken.py", "raise SystemExit(1)\n")
    payload = {
        "workingDirectory": str(tmp_path),
        "filePath": "broken.py",
        "instruction": "Write a script that always succeeds.",
        "passed": False,
        "exitCode": 1,
        "output": "Traceback (most recent call last):\nSystemExit: 1\n",
    }

    agent = _agent_with_prompt(_TEMPLATE)
    context_manager = DefaultContextManager([_FixedPayloadResolver(payload)])
    registry = InMemoryAgentRegistry({_AGENT_ID: agent})
    executor = AgentStepExecutor(registry, context_manager)

    outputs = await executor.execute(_step(), workflow_id="wf_test")

    assert outputs["ready"] is False
    assert outputs["written"] is True
    changelog_text = (tmp_path / "broken.py.changelog.md").read_text(encoding="utf-8")
    assert "Passed: false" in changelog_text


@pytest.mark.asyncio
async def test_release_agent_via_direct_execute_with_inputs_supplied_directly(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "ok.py", "print('direct call')\n")

    agent = _agent_with_prompt(_TEMPLATE)

    outputs = await agent.execute(
        {
            "promptId": _PROMPT_ID,
            "promptVersion": _PROMPT_VERSION,
            "modelAlias": "coding-strong",
            "workingDirectory": str(tmp_path),
            "filePath": "ok.py",
            "instruction": "Write a script that prints 'direct call'.",
            "passed": True,
            "exitCode": 0,
            "output": "direct call\n",
        }
    )

    ReleaseAgentOutput.model_validate(outputs)
    assert outputs["written"] is True
    assert outputs["ready"] is True
    assert (tmp_path / "ok.py.changelog.md").is_file()


@pytest.mark.asyncio
async def test_release_agent_rejects_a_missing_file(tmp_path: Path) -> None:
    agent = _agent_with_prompt(_TEMPLATE)

    with pytest.raises(ReleaseInstructionError, match="does not exist"):
        await agent.execute(
            {
                "promptId": _PROMPT_ID,
                "promptVersion": _PROMPT_VERSION,
                "modelAlias": "coding-strong",
                "workingDirectory": str(tmp_path),
                "filePath": "does_not_exist.py",
                "instruction": "irrelevant",
                "passed": True,
                "exitCode": 0,
                "output": "",
            }
        )


@pytest.mark.asyncio
async def test_release_agent_rejects_a_nonexistent_working_directory(tmp_path: Path) -> None:
    agent = _agent_with_prompt(_TEMPLATE)
    missing = tmp_path / "does-not-exist"

    with pytest.raises(ReleaseInstructionError, match="does not exist or is not a"):
        await agent.execute(
            {
                "promptId": _PROMPT_ID,
                "promptVersion": _PROMPT_VERSION,
                "modelAlias": "coding-strong",
                "workingDirectory": str(missing),
                "filePath": "ok.py",
                "instruction": "irrelevant",
                "passed": True,
                "exitCode": 0,
                "output": "",
            }
        )


@pytest.mark.asyncio
async def test_release_agent_rejects_missing_required_fields() -> None:
    agent = _agent_with_prompt(_TEMPLATE)

    with pytest.raises(ReleaseInstructionError, match="requires"):
        await agent.execute({"filePath": "ok.py"})


@pytest.mark.asyncio
async def test_missing_required_invocation_fields_raise_a_clear_error(tmp_path: Path) -> None:
    _write(tmp_path / "ok.py", "print('ok')\n")
    agent = _agent_with_prompt(_TEMPLATE)

    with pytest.raises(ReleaseInstructionError, match="promptId"):
        await agent.execute(
            {
                "modelAlias": "coding-strong",
                "workingDirectory": str(tmp_path),
                "filePath": "ok.py",
                "instruction": "irrelevant",
                "passed": True,
                "exitCode": 0,
                "output": "",
            }
        )


@pytest.mark.asyncio
async def test_release_agent_via_agent_step_executor_rejects_a_malformed_context_payload(
    tmp_path: Path,
) -> None:
    context_manager = DefaultContextManager([_FixedPayloadResolver({"filePath": "ok.py"})])
    registry = InMemoryAgentRegistry({_AGENT_ID: _agent_with_prompt(_TEMPLATE)})
    executor = AgentStepExecutor(registry, context_manager)

    with pytest.raises(ReleaseInstructionError, match="missing"):
        await executor.execute(_step(), workflow_id="wf_test")


def test_resolve_existing_file_rejects_a_blank_path(tmp_path: Path) -> None:
    with pytest.raises(ReleaseInstructionError, match="must not be blank"):
        _resolve_existing_file(tmp_path, "   ")


@pytest.mark.parametrize("malicious_path", ["../../outside.txt.changelog.md", "/etc/passwd"])
def test_resolve_safe_relative_path_rejects_paths_that_escape_the_working_directory(
    tmp_path: Path, malicious_path: str
) -> None:
    with pytest.raises(ReleaseInstructionError, match="resolves outside"):
        _resolve_safe_relative_path(tmp_path, malicious_path)


def test_release_agent_input_documents_the_agent_contract() -> None:
    ReleaseAgentInput.model_validate(
        {
            "workingDirectory": "workspace",
            "filePath": "a.py",
            "instruction": "Write a hello-world script.",
            "passed": True,
            "exitCode": 0,
            "output": "hello\n",
        }
    )
