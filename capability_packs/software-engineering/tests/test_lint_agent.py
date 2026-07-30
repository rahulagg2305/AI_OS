"""Deterministic tests for the Lint Agent — no database, no LLM call
at all (this agent makes none — see its own module docstring), but a
genuine, non-mocked sandbox and a genuine, real ``python -m py_compile``
invocation: every run in this file happens through a real
``LocalSubprocessSandbox``/real OS subprocess, so a passing test means
``py_compile`` genuinely found (or didn't find) a real syntax error,
not an assertion about a mock's call arguments.

**Proves this pack's sixth agent independently first, before it is
chained into `se.delivery_pipeline`** — the identical "prove each agent
alone first, chain later" sequencing every other agent in this pack's
own history has followed (see ``test_verification_agent.py``, this
file's own direct template — nearly every shape below is that file's,
substituting ``lintCommand``/``py_compile`` for ``runCommand``/direct
execution).
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
from ai_os_kernel.sandbox.executor import LocalSubprocessSandbox, SandboxExecutor
from ai_os_kernel.sdk_adapters.pack_context import build_pack_context
from ai_os_kernel.workflow_engine.models import StepType, WorkflowStep
from ai_os_kernel.workflow_engine.registry import InMemoryAgentRegistry
from ai_os_kernel.workflow_engine.step_executor import AgentStepExecutor
from ai_os_pack_software_engineering.agents.lint import (
    LintAgentEntrypoint,
    LintAgentInput,
    LintAgentOutput,
    LintInstructionError,
    _resolve_existing_file,
)
from ai_os_sdk.contracts import Agent as SdkAgent
from ai_os_sdk.contracts import PackContextReceiver

_AGENT_ID = "lint"
_PACK_ID = "software-engineering"
_PACK_VERSION = "0.1.0"
_PY_COMPILE_COMMAND = [sys.executable, "-m", "py_compile"]


def _agent_with_sandbox(sandbox: SandboxExecutor) -> LintAgentEntrypoint:
    """The real, zero-arg-constructed entrypoint, bound to a real
    ``PackContext`` granting exactly ``sandbox:execute`` over
    ``sandbox`` — the same construction+injection sequence a real
    ``SqlAgentRegistry``-backed caller would perform."""
    agent = LintAgentEntrypoint()
    agent.bind_pack_context(
        build_pack_context(
            pack_id=_PACK_ID,
            pack_version=_PACK_VERSION,
            permissions=["sandbox:execute"],
            sandbox=sandbox,
        )
    )
    return agent


class _FixedPayloadResolver:
    """A fake `ContextSourceResolver` (ADR-0004: a legitimate test
    substitute) that always returns one item carrying a fixed,
    JSON-encoded ``{workingDirectory, filePath, lintCommand}``
    payload — the real channel `LintAgentEntrypoint` reads from when
    invoked through a real `AgentStepExecutor`."""

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
    return WorkflowStep(id="run_lint", type=StepType.AGENT, agent_id=_AGENT_ID)


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_lint_agent_entrypoint_constructs_with_zero_arguments() -> None:
    """The exact call EntrypointLoader/SqlAgentRegistry make in
    production — must succeed instantly, with no I/O."""
    agent = LintAgentEntrypoint()

    assert agent.output_schema["required"] == ["passed", "exitCode", "output"]


@pytest.mark.asyncio
async def test_lint_agent_reports_a_genuine_clean_case_via_direct_execute(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "clean.py", "print('all good')\n")
    agent = _agent_with_sandbox(LocalSubprocessSandbox())

    outputs = await agent.execute(
        {
            "workingDirectory": str(tmp_path),
            "filePath": "clean.py",
            "lintCommand": [*_PY_COMPILE_COMMAND, "clean.py"],
        }
    )

    LintAgentOutput.model_validate(outputs)
    assert outputs["passed"] is True
    assert outputs["exitCode"] == 0


@pytest.mark.asyncio
async def test_lint_agent_reports_a_genuine_violating_case_via_direct_execute(
    tmp_path: Path,
) -> None:
    # A real, deterministic syntax error — py_compile's own real check.
    _write(tmp_path / "dirty.py", "def f(:\n    pass\n")
    agent = _agent_with_sandbox(LocalSubprocessSandbox())

    outputs = await agent.execute(
        {
            "workingDirectory": str(tmp_path),
            "filePath": "dirty.py",
            "lintCommand": [*_PY_COMPILE_COMMAND, "dirty.py"],
        }
    )

    LintAgentOutput.model_validate(outputs)
    assert outputs["passed"] is False
    assert outputs["exitCode"] == 1
    assert "SyntaxError" in outputs["output"]


@pytest.mark.asyncio
async def test_lint_agent_rejects_a_missing_file(tmp_path: Path) -> None:
    agent = _agent_with_sandbox(LocalSubprocessSandbox())

    with pytest.raises(LintInstructionError, match="does not exist"):
        await agent.execute(
            {
                "workingDirectory": str(tmp_path),
                "filePath": "does_not_exist.py",
                "lintCommand": [*_PY_COMPILE_COMMAND, "does_not_exist.py"],
            }
        )


@pytest.mark.asyncio
async def test_lint_agent_rejects_a_path_that_escapes_the_working_directory(
    tmp_path: Path,
) -> None:
    agent = _agent_with_sandbox(LocalSubprocessSandbox())

    with pytest.raises(LintInstructionError, match="resolves outside"):
        await agent.execute(
            {
                "workingDirectory": str(tmp_path),
                "filePath": "../outside.py",
                "lintCommand": [*_PY_COMPILE_COMMAND, "../outside.py"],
            }
        )


@pytest.mark.asyncio
async def test_lint_agent_rejects_missing_required_fields() -> None:
    agent = _agent_with_sandbox(LocalSubprocessSandbox())

    with pytest.raises(LintInstructionError, match="requires"):
        await agent.execute({"filePath": "clean.py"})


@pytest.mark.asyncio
async def test_lint_agent_rejects_a_nonexistent_working_directory(tmp_path: Path) -> None:
    agent = _agent_with_sandbox(LocalSubprocessSandbox())
    missing = tmp_path / "does-not-exist"

    with pytest.raises(LintInstructionError, match="does not exist or is not a directory"):
        await agent.execute(
            {
                "workingDirectory": str(missing),
                "filePath": "clean.py",
                "lintCommand": [*_PY_COMPILE_COMMAND, "clean.py"],
            }
        )


def test_resolve_existing_file_rejects_a_blank_path(tmp_path: Path) -> None:
    with pytest.raises(LintInstructionError, match="must not be blank"):
        _resolve_existing_file(tmp_path, "   ")


@pytest.mark.asyncio
async def test_lint_agent_genuinely_dispatches_through_agent_step_executor_passing_case(
    tmp_path: Path,
) -> None:
    """The real end-to-end proof this step exists for (the passing
    half): a real WorkflowStep of type agent, dispatched through the
    real AgentStepExecutor with a real (fake-resolver-backed) Context
    Manager, genuinely runs py_compile inside the sandbox and reports a
    genuinely correct pass outcome."""
    _write(tmp_path / "clean.py", "print('passing case')\n")
    payload = {
        "workingDirectory": str(tmp_path),
        "filePath": "clean.py",
        "lintCommand": [*_PY_COMPILE_COMMAND, "clean.py"],
    }
    context_manager = DefaultContextManager([_FixedPayloadResolver(payload)])
    registry = InMemoryAgentRegistry({_AGENT_ID: _agent_with_sandbox(LocalSubprocessSandbox())})
    executor = AgentStepExecutor(registry, context_manager)

    outputs = await executor.execute(_step(), workflow_id="wf_test")

    LintAgentOutput.model_validate(outputs)
    assert outputs["passed"] is True
    assert outputs["exitCode"] == 0


@pytest.mark.asyncio
async def test_lint_agent_genuinely_dispatches_through_agent_step_executor_violating_case(
    tmp_path: Path,
) -> None:
    """The real end-to-end proof this step exists for (the violating
    half): the identical dispatch chain, against a file with a genuine
    syntax error, genuinely reports a correct fail outcome — proving
    `passed` tracks the real exit code both ways."""
    _write(tmp_path / "dirty.py", "def f(:\n    pass\n")
    payload = {
        "workingDirectory": str(tmp_path),
        "filePath": "dirty.py",
        "lintCommand": [*_PY_COMPILE_COMMAND, "dirty.py"],
    }
    context_manager = DefaultContextManager([_FixedPayloadResolver(payload)])
    registry = InMemoryAgentRegistry({_AGENT_ID: _agent_with_sandbox(LocalSubprocessSandbox())})
    executor = AgentStepExecutor(registry, context_manager)

    outputs = await executor.execute(_step(), workflow_id="wf_test")

    LintAgentOutput.model_validate(outputs)
    assert outputs["passed"] is False
    assert outputs["exitCode"] == 1


@pytest.mark.asyncio
async def test_lint_agent_via_agent_step_executor_rejects_a_malformed_context_payload(
    tmp_path: Path,
) -> None:
    context_manager = DefaultContextManager([_FixedPayloadResolver({"filePath": "clean.py"})])
    registry = InMemoryAgentRegistry({_AGENT_ID: _agent_with_sandbox(LocalSubprocessSandbox())})
    executor = AgentStepExecutor(registry, context_manager)

    with pytest.raises(LintInstructionError, match="missing"):
        await executor.execute(_step(), workflow_id="wf_test")


def test_lint_agent_input_documents_the_agent_contract() -> None:
    LintAgentInput.model_validate(
        {
            "workingDirectory": "workspace",
            "filePath": "a.py",
            "lintCommand": ["python", "-m", "py_compile", "a.py"],
        }
    )


@pytest.mark.asyncio
async def test_execute_before_bind_pack_context_raises_a_clear_error(tmp_path: Path) -> None:
    """A caller that forgets to inject a PackContext gets a clear,
    named error, not a confusing AttributeError two frames into a
    None.tools.invoke() call — the identical guarantee
    `TestAgentEntrypoint` already establishes."""
    _write(tmp_path / "clean.py", "print('ok')\n")
    agent = LintAgentEntrypoint()

    with pytest.raises(LintInstructionError, match="bind_pack_context"):
        await agent.execute(
            {
                "workingDirectory": str(tmp_path),
                "filePath": "clean.py",
                "lintCommand": [*_PY_COMPILE_COMMAND, "clean.py"],
            }
        )


def test_the_entrypoint_satisfies_both_sdk_protocols() -> None:
    """This entrypoint is a real ai_os_sdk.contracts.Agent and
    PackContextReceiver from the start — no migration needed, since it
    is built after the Platform SDK already exists (unlike the other
    five agents, which each needed their own dedicated migration step)."""
    agent = LintAgentEntrypoint()

    assert isinstance(agent, SdkAgent)
    assert isinstance(agent, PackContextReceiver)
