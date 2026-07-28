"""SandboxedCommandTool against the real LocalSubprocessSandbox — a
genuine OS subprocess, no mocking, no Docker/Postgres dependency
(mirrors the previous step's own `tests/unit/kernel/sandbox` suite).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from ai_os_kernel.sandbox.executor import LocalSubprocessSandbox
from ai_os_kernel.workflow_engine.sandboxed_tool import SandboxedCommandTool
from ai_os_kernel.workflow_engine.tool import SandboxBackedTool, TrustTier

_PYTHON = sys.executable


@pytest.mark.asyncio
async def test_sandboxed_command_tool_declares_tier1_sandboxed(tmp_path: Path) -> None:
    tool = SandboxedCommandTool(
        LocalSubprocessSandbox(),
        command=[_PYTHON, "-c", "pass"],
        working_directory=tmp_path,
        timeout_seconds=5.0,
        max_output_bytes=1000,
    )

    assert tool.trust_tier is TrustTier.TIER1_SANDBOXED


@pytest.mark.asyncio
async def test_sandboxed_command_tool_satisfies_the_sandbox_backed_protocol(
    tmp_path: Path,
) -> None:
    sandbox = LocalSubprocessSandbox()
    tool = SandboxedCommandTool(
        sandbox,
        command=[_PYTHON, "-c", "pass"],
        working_directory=tmp_path,
        timeout_seconds=5.0,
        max_output_bytes=1000,
    )

    assert isinstance(tool, SandboxBackedTool)
    assert tool.sandbox is sandbox


@pytest.mark.asyncio
async def test_sandboxed_command_tool_executes_a_real_command_and_maps_the_result(
    tmp_path: Path,
) -> None:
    tool = SandboxedCommandTool(
        LocalSubprocessSandbox(),
        command=[_PYTHON, "-c", "print('hello from a real tool')"],
        working_directory=tmp_path,
        timeout_seconds=5.0,
        max_output_bytes=1000,
    )

    outputs = await tool.execute({})

    # .strip() only to absorb the platform's own newline convention for
    # a child's `print()` (CRLF on Windows, LF elsewhere) — not a
    # sandbox behaviour this tool is responsible for normalizing.
    assert outputs["stdout"].strip() == "hello from a real tool"
    assert outputs["exitCode"] == 0
    assert outputs["stderr"] == ""
    assert outputs["timedOut"] is False
    assert outputs["truncated"] is False
    assert outputs["durationSeconds"] >= 0.0


@pytest.mark.asyncio
async def test_sandboxed_command_tool_reports_a_nonzero_exit_code(tmp_path: Path) -> None:
    tool = SandboxedCommandTool(
        LocalSubprocessSandbox(),
        command=[_PYTHON, "-c", "import sys; sys.exit(3)"],
        working_directory=tmp_path,
        timeout_seconds=5.0,
        max_output_bytes=1000,
    )

    outputs = await tool.execute({})

    assert outputs["exitCode"] == 3


@pytest.mark.asyncio
async def test_sandboxed_command_tool_reports_a_timeout(tmp_path: Path) -> None:
    tool = SandboxedCommandTool(
        LocalSubprocessSandbox(),
        command=[_PYTHON, "-c", "import time; time.sleep(30)"],
        working_directory=tmp_path,
        timeout_seconds=0.5,
        max_output_bytes=1000,
    )

    outputs = await tool.execute({})

    assert outputs["timedOut"] is True
    assert outputs["exitCode"] is None


@pytest.mark.asyncio
async def test_sandboxed_command_tool_ignores_whatever_inputs_it_is_called_with(
    tmp_path: Path,
) -> None:
    tool = SandboxedCommandTool(
        LocalSubprocessSandbox(),
        command=[_PYTHON, "-c", "print('fixed at construction')"],
        working_directory=tmp_path,
        timeout_seconds=5.0,
        max_output_bytes=1000,
    )

    outputs = await tool.execute({"ignored": "value", "toolId": "something-else"})

    assert outputs["stdout"].strip() == "fixed at construction"


@pytest.mark.asyncio
async def test_sandboxed_command_tool_forwards_stdin_to_the_sandbox(tmp_path: Path) -> None:
    tool = SandboxedCommandTool(
        LocalSubprocessSandbox(),
        command=[_PYTHON, "-c", "import sys; sys.stdout.write(sys.stdin.read())"],
        working_directory=tmp_path,
        timeout_seconds=5.0,
        max_output_bytes=1000,
        stdin=b"delivered via stdin",
    )

    outputs = await tool.execute({})

    assert outputs["stdout"] == "delivered via stdin"


@pytest.mark.asyncio
async def test_sandboxed_command_tool_output_matches_its_own_declared_schema(
    tmp_path: Path,
) -> None:
    tool = SandboxedCommandTool(
        LocalSubprocessSandbox(),
        command=[_PYTHON, "-c", "print('schema check')"],
        working_directory=tmp_path,
        timeout_seconds=5.0,
        max_output_bytes=1000,
    )

    outputs = await tool.execute({})

    validator = Draft202012Validator(tool.output_schema)
    assert list(validator.iter_errors(outputs)) == []
