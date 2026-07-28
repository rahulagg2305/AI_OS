"""Deterministic tests for the Test Agent — no database, no LLM call
at all (this agent makes none — see its own module docstring), but a
genuine, non-mocked sandbox: every run in this file happens through a
real ``LocalSubprocessSandbox``/real OS subprocess, so a passing test
means a real process genuinely exited with a real code, not an
assertion about a mock's call arguments.
"""

from __future__ import annotations

import json
import sys
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
from ai_os_kernel.workflow_engine.models import StepType, WorkflowStep
from ai_os_kernel.workflow_engine.registry import InMemoryAgentRegistry
from ai_os_kernel.workflow_engine.step_executor import AgentStepExecutor
from ai_os_pack_software_engineering.agents.verification import (
    TestAgentEntrypoint,
    TestAgentInput,
    TestAgentOutput,
    TestInstructionError,
    _resolve_existing_file,
)

_AGENT_ID = "qa-test"
_PYTHON = sys.executable


class _FixedPayloadResolver:
    """A fake `ContextSourceResolver` (ADR-0004: a legitimate test
    substitute) that always returns one item carrying a fixed,
    JSON-encoded ``{workingDirectory, filePath, runCommand}`` payload —
    the real channel `TestAgentEntrypoint` reads from when invoked
    through a real `AgentStepExecutor` (see that module's own
    docstring for why)."""

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


def _step() -> WorkflowStep:
    return WorkflowStep(id="run_test", type=StepType.AGENT, agent_id=_AGENT_ID)


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_test_agent_entrypoint_constructs_with_zero_arguments() -> None:
    agent = TestAgentEntrypoint()

    assert agent.output_schema["required"] == ["passed", "exitCode", "output"]


@pytest.mark.asyncio
async def test_test_agent_reports_a_genuine_passing_case_via_direct_execute(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "ok.py", "print('all good')\n")
    agent = TestAgentEntrypoint()

    outputs = await agent.execute(
        {
            "workingDirectory": str(tmp_path),
            "filePath": "ok.py",
            "runCommand": [_PYTHON, "ok.py"],
        }
    )

    TestAgentOutput.model_validate(outputs)
    assert outputs["passed"] is True
    assert outputs["exitCode"] == 0
    assert "all good" in outputs["output"]


@pytest.mark.asyncio
async def test_test_agent_reports_a_genuine_failing_case_via_direct_execute(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "broken.py", "raise SystemExit(1)\n")
    agent = TestAgentEntrypoint()

    outputs = await agent.execute(
        {
            "workingDirectory": str(tmp_path),
            "filePath": "broken.py",
            "runCommand": [_PYTHON, "broken.py"],
        }
    )

    TestAgentOutput.model_validate(outputs)
    assert outputs["passed"] is False
    assert outputs["exitCode"] == 1


@pytest.mark.asyncio
async def test_test_agent_rejects_a_missing_file(tmp_path: Path) -> None:
    agent = TestAgentEntrypoint()

    with pytest.raises(TestInstructionError, match="does not exist"):
        await agent.execute(
            {
                "workingDirectory": str(tmp_path),
                "filePath": "does_not_exist.py",
                "runCommand": [_PYTHON, "does_not_exist.py"],
            }
        )


@pytest.mark.asyncio
async def test_test_agent_rejects_a_path_that_escapes_the_working_directory(
    tmp_path: Path,
) -> None:
    agent = TestAgentEntrypoint()

    with pytest.raises(TestInstructionError, match="resolves outside"):
        await agent.execute(
            {
                "workingDirectory": str(tmp_path),
                "filePath": "../outside.py",
                "runCommand": [_PYTHON, "../outside.py"],
            }
        )


@pytest.mark.asyncio
async def test_test_agent_rejects_missing_required_fields() -> None:
    agent = TestAgentEntrypoint()

    with pytest.raises(TestInstructionError, match="requires"):
        await agent.execute({"filePath": "ok.py"})


@pytest.mark.asyncio
async def test_test_agent_rejects_a_nonexistent_working_directory(tmp_path: Path) -> None:
    agent = TestAgentEntrypoint()
    missing = tmp_path / "does-not-exist"

    with pytest.raises(TestInstructionError, match="does not exist or is not a directory"):
        await agent.execute(
            {
                "workingDirectory": str(missing),
                "filePath": "ok.py",
                "runCommand": [_PYTHON, "ok.py"],
            }
        )


def test_resolve_existing_file_rejects_a_blank_path(tmp_path: Path) -> None:
    with pytest.raises(TestInstructionError, match="must not be blank"):
        _resolve_existing_file(tmp_path, "   ")


@pytest.mark.asyncio
async def test_test_agent_genuinely_dispatches_through_agent_step_executor_passing_case(
    tmp_path: Path,
) -> None:
    """The real end-to-end proof this step exists for (the passing
    half): a real WorkflowStep of type agent, dispatched through the
    real AgentStepExecutor with a real (fake-resolver-backed) Context
    Manager, genuinely runs a real file inside the sandbox and reports
    a genuinely correct pass outcome — derived only from the real exit
    code, never from any judgment about the output's content."""
    _write(tmp_path / "ok.py", "print('passing case')\n")
    payload = {
        "workingDirectory": str(tmp_path),
        "filePath": "ok.py",
        "runCommand": [_PYTHON, "ok.py"],
    }
    context_manager = DefaultContextManager([_FixedPayloadResolver(payload)])
    registry = InMemoryAgentRegistry({_AGENT_ID: TestAgentEntrypoint()})
    executor = AgentStepExecutor(registry, context_manager)

    outputs = await executor.execute(_step(), workflow_id="wf_test")

    TestAgentOutput.model_validate(outputs)
    assert outputs["passed"] is True
    assert outputs["exitCode"] == 0
    assert "passing case" in outputs["output"]


@pytest.mark.asyncio
async def test_test_agent_genuinely_dispatches_through_agent_step_executor_failing_case(
    tmp_path: Path,
) -> None:
    """The real end-to-end proof this step exists for (the failing
    half): the identical dispatch chain, against a file that genuinely
    fails, genuinely reports a correct fail outcome — proving `passed`
    tracks the real exit code both ways, not just when it happens to
    be zero."""
    _write(tmp_path / "broken.py", "raise SystemExit(7)\n")
    payload = {
        "workingDirectory": str(tmp_path),
        "filePath": "broken.py",
        "runCommand": [_PYTHON, "broken.py"],
    }
    context_manager = DefaultContextManager([_FixedPayloadResolver(payload)])
    registry = InMemoryAgentRegistry({_AGENT_ID: TestAgentEntrypoint()})
    executor = AgentStepExecutor(registry, context_manager)

    outputs = await executor.execute(_step(), workflow_id="wf_test")

    TestAgentOutput.model_validate(outputs)
    assert outputs["passed"] is False
    assert outputs["exitCode"] == 7


@pytest.mark.asyncio
async def test_test_agent_via_agent_step_executor_rejects_a_malformed_context_payload(
    tmp_path: Path,
) -> None:
    context_manager = DefaultContextManager([_FixedPayloadResolver({"filePath": "ok.py"})])
    registry = InMemoryAgentRegistry({_AGENT_ID: TestAgentEntrypoint()})
    executor = AgentStepExecutor(registry, context_manager)

    with pytest.raises(TestInstructionError, match="missing"):
        await executor.execute(_step(), workflow_id="wf_test")


def test_test_agent_input_documents_the_agent_contract() -> None:
    TestAgentInput.model_validate(
        {"workingDirectory": "workspace", "filePath": "a.py", "runCommand": ["python", "a.py"]}
    )
