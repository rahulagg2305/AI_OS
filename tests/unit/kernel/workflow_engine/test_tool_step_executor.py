"""Unit tests for ToolStepExecutor — no database. Most cases use fake
Protocol implementations (ADR-0004: interface-driven, so fakes are
legitimate substitutes), but the ``tier1_sandboxed`` dispatch tests use
the real ``LocalSubprocessSandbox``/``SandboxedCommandTool`` — a genuine
OS subprocess, no mocking, no Docker/Postgres dependency — since the
whole point of this suite's newest cases is proving a real sandboxed
command genuinely executes through this executor end to end.
"""

import sys
from pathlib import Path
from typing import Any

import pytest

from ai_os_kernel.sandbox.executor import LocalSubprocessSandbox, SandboxExecutor
from ai_os_kernel.workflow_engine.errors import (
    ToolNotRegisteredError,
    ToolOutputValidationError,
    ToolSandboxRequiredError,
)
from ai_os_kernel.workflow_engine.models import StepType, WorkflowStep
from ai_os_kernel.workflow_engine.registry import InMemoryToolRegistry
from ai_os_kernel.workflow_engine.sandboxed_tool import SandboxedCommandTool
from ai_os_kernel.workflow_engine.step_executor import ToolStepExecutor
from ai_os_kernel.workflow_engine.tool import EchoTool, Tool, TrustTier

_PYTHON = sys.executable

_TOOL_ID = "se.build"
_TOOL_STEP = WorkflowStep(id="run_build", type=StepType.TOOL, tool_id=_TOOL_ID)
_AGENT_STEP = WorkflowStep(
    id="analyze_requirements", type=StepType.AGENT, agent_id="se.software_engineering/analyst"
)


def _registry_with(tool: Tool) -> InMemoryToolRegistry:
    return InMemoryToolRegistry({_TOOL_ID: tool})


class _MisbehavingTool:
    """Declares one output_schema but returns something that violates it."""

    trust_tier: TrustTier = TrustTier.TIER2_TRUSTED
    output_schema: dict[str, Any] = {
        "type": "object",
        "properties": {"result": {"const": "ok"}},
        "required": ["result"],
        "additionalProperties": False,
    }

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"result": "not-ok"}


class _UntrustedTool:
    """A tool that declares tier1_sandboxed but has no ``sandbox``
    attribute at all — must still be refused."""

    trust_tier: TrustTier = TrustTier.TIER1_SANDBOXED
    output_schema: dict[str, Any] = {"type": "object"}

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return {}


class _FalselySandboxBackedTool:
    """Structurally satisfies SandboxBackedTool (has a ``sandbox``
    attribute) but that attribute is ``None`` — not genuinely backed,
    and must still be refused. Proves the executor's guard checks the
    attribute's value, not merely its presence."""

    trust_tier: TrustTier = TrustTier.TIER1_SANDBOXED
    output_schema: dict[str, Any] = {"type": "object"}
    sandbox: SandboxExecutor | None = None

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return {}


class _NamedTool:
    """Returns its own name in the output, so a test can prove which
    registered tool actually ran without relying on two indistinguishable
    EchoTool instances."""

    trust_tier: TrustTier = TrustTier.TIER2_TRUSTED
    output_schema: dict[str, Any] = {
        "type": "object",
        "properties": {"ranAs": {"type": "string"}},
        "required": ["ranAs"],
        "additionalProperties": False,
    }

    def __init__(self, name: str) -> None:
        self._name = name

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"ranAs": self._name}


@pytest.mark.asyncio
async def test_tool_step_executor_calls_the_tool_and_returns_its_output() -> None:
    executor = ToolStepExecutor(_registry_with(EchoTool()))

    outputs = await executor.execute(_TOOL_STEP)

    assert outputs == {"result": "ok"}


@pytest.mark.asyncio
async def test_tool_step_executor_rejects_output_violating_the_declared_schema() -> None:
    executor = ToolStepExecutor(_registry_with(_MisbehavingTool()))

    with pytest.raises(ToolOutputValidationError, match="output_schema"):
        await executor.execute(_TOOL_STEP)


@pytest.mark.asyncio
async def test_tool_step_executor_refuses_a_non_tool_step() -> None:
    executor = ToolStepExecutor(_registry_with(EchoTool()))

    with pytest.raises(ValueError, match="agent"):
        await executor.execute(_AGENT_STEP)


@pytest.mark.asyncio
async def test_tool_step_executor_refuses_a_tier1_sandboxed_tool() -> None:
    executor = ToolStepExecutor(_registry_with(_UntrustedTool()))

    with pytest.raises(ToolSandboxRequiredError, match="tier1_sandboxed"):
        await executor.execute(_TOOL_STEP)


@pytest.mark.asyncio
async def test_tool_step_executor_raises_for_an_unregistered_tool_id() -> None:
    executor = ToolStepExecutor(InMemoryToolRegistry({}))

    with pytest.raises(ToolNotRegisteredError, match=_TOOL_ID):
        await executor.execute(_TOOL_STEP)


@pytest.mark.asyncio
async def test_tool_step_executor_resolves_different_tools_for_different_steps() -> None:
    other_tool_id = "se.lint"
    other_step = WorkflowStep(id="run_lint", type=StepType.TOOL, tool_id=other_tool_id)
    registry = InMemoryToolRegistry(
        {_TOOL_ID: _NamedTool("build"), other_tool_id: _NamedTool("lint")}
    )
    executor = ToolStepExecutor(registry)

    first = await executor.execute(_TOOL_STEP)
    second = await executor.execute(other_step)

    assert first == {"ranAs": "build"}
    assert second == {"ranAs": "lint"}


@pytest.mark.asyncio
async def test_tool_step_executor_refuses_a_tier1_sandboxed_tool_whose_sandbox_is_none() -> None:
    """Structural presence of a ``sandbox`` attribute is not enough —
    it must also genuinely be a working sandbox, not ``None``."""
    executor = ToolStepExecutor(_registry_with(_FalselySandboxBackedTool()))

    with pytest.raises(ToolSandboxRequiredError, match="tier1_sandboxed"):
        await executor.execute(_TOOL_STEP)


@pytest.mark.asyncio
async def test_tool_step_executor_dispatches_a_genuinely_sandbox_backed_tool_end_to_end(
    tmp_path: Path,
) -> None:
    """The real end-to-end proof this step exists for: a WorkflowStep
    of type tool, resolved through ToolStepExecutor, genuinely executes
    a real command through a real SandboxExecutor — no mocking
    anywhere in this chain."""
    tool = SandboxedCommandTool(
        LocalSubprocessSandbox(),
        command=[_PYTHON, "-c", "print('real sandboxed execution')"],
        working_directory=tmp_path,
        timeout_seconds=5.0,
        max_output_bytes=10_000,
    )
    executor = ToolStepExecutor(_registry_with(tool))

    outputs = await executor.execute(_TOOL_STEP)

    assert outputs["exitCode"] == 0
    assert outputs["stdout"].strip() == "real sandboxed execution"
    assert outputs["timedOut"] is False


@pytest.mark.asyncio
async def test_tool_step_executor_still_validates_a_sandboxed_tools_output(
    tmp_path: Path,
) -> None:
    """A genuinely sandbox-backed tool is not exempt from output_schema
    validation — it is dispatched, not trusted blindly."""

    class _BadlyDeclaredSandboxTool(SandboxedCommandTool):
        output_schema: dict[str, Any] = {
            "type": "object",
            "properties": {"exitCode": {"const": "not-a-real-schema-match"}},
            "required": ["exitCode"],
        }

    tool = _BadlyDeclaredSandboxTool(
        LocalSubprocessSandbox(),
        command=[_PYTHON, "-c", "pass"],
        working_directory=tmp_path,
        timeout_seconds=5.0,
        max_output_bytes=1000,
    )
    executor = ToolStepExecutor(_registry_with(tool))

    with pytest.raises(ToolOutputValidationError, match="output_schema"):
        await executor.execute(_TOOL_STEP)
