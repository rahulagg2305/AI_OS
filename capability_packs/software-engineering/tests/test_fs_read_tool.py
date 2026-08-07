"""Deterministic, fake-sandbox unit tests for the `fs.read` Tool — no
database, no real subprocess (ADR-0004: a scripted fake Protocol
substitute is a legitimate stand-in for pure, deterministic logic).

The real, live proof (a genuine `SqlToolRegistry` resolution + a real
`LocalSubprocessSandbox` reading a real file) lives in
`tests/integration/workflow_engine/test_registry.py`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ai_os_kernel.sandbox.models import SandboxResult
from ai_os_pack_software_engineering.tools.fs_read import (
    _READ_FILE_SCRIPT,
    FsReadInput,
    FsReadOutput,
    FsReadToolEntrypoint,
    FsReadToolInputError,
)


class _FakeSandbox:
    """Scripted by (command tuple) -> :class:`SandboxResult`; also
    exposes the real, duck-typed `python_command` property this Tool
    reads."""

    python_command: tuple[str, ...] = ("python3",)

    def __init__(self, scripted: dict[tuple[str, ...], SandboxResult]) -> None:
        self._scripted = scripted
        self.calls: list[dict[str, Any]] = []

    async def execute(
        self,
        *,
        command: list[str],
        working_directory: Path,
        timeout_seconds: float,
        max_output_bytes: int,
        env: dict[str, str] | None = None,
        stdin: bytes | None = None,
    ) -> SandboxResult:
        self.calls.append({"command": tuple(command), "working_directory": working_directory})
        key = tuple(command)
        if key not in self._scripted:
            raise AssertionError(f"unscripted command: {command!r}")
        return self._scripted[key]


def test_entrypoint_constructs_with_zero_arguments_and_starts_with_no_sandbox() -> None:
    tool = FsReadToolEntrypoint()

    assert tool.sandbox is None
    assert tool.output_schema == {
        "type": "object",
        "properties": {"content": {"type": "string"}},
        "required": ["content"],
        "additionalProperties": False,
    }


@pytest.mark.asyncio
async def test_execute_before_a_sandbox_is_injected_raises_a_clear_error() -> None:
    tool = FsReadToolEntrypoint()

    with pytest.raises(FsReadToolInputError, match="before a real sandbox was injected"):
        await tool.execute({"filePath": "solution.py", "workingDirectory": "/work"})


@pytest.mark.asyncio
async def test_missing_required_fields_raise_a_clear_error() -> None:
    tool = FsReadToolEntrypoint()
    tool.sandbox = _FakeSandbox({})

    with pytest.raises(FsReadToolInputError, match="filePath"):
        await tool.execute({"workingDirectory": "/work"})


@pytest.mark.asyncio
async def test_a_real_read_returns_the_files_content() -> None:
    tool = FsReadToolEntrypoint()
    sandbox = _FakeSandbox(
        {
            ("python3", "-c", _READ_FILE_SCRIPT, "solution.py"): SandboxResult(
                exit_code=0,
                stdout='print("hello")',
                stderr="",
                timed_out=False,
                truncated=False,
                duration_seconds=0.01,
            )
        }
    )
    tool.sandbox = sandbox

    outputs = await tool.execute({"filePath": "solution.py", "workingDirectory": "/work"})

    FsReadOutput.model_validate(outputs)
    assert outputs == {"content": 'print("hello")'}
    assert sandbox.calls[0]["working_directory"] == Path("/work")


@pytest.mark.asyncio
async def test_a_nonzero_exit_code_raises_a_clear_error() -> None:
    tool = FsReadToolEntrypoint()
    tool.sandbox = _FakeSandbox(
        {
            ("python3", "-c", _READ_FILE_SCRIPT, "missing.py"): SandboxResult(
                exit_code=1,
                stdout="",
                stderr="FileNotFoundError",
                timed_out=False,
                truncated=False,
                duration_seconds=0.01,
            )
        }
    )

    with pytest.raises(FsReadToolInputError, match="could not read"):
        await tool.execute({"filePath": "missing.py", "workingDirectory": "/work"})


def test_input_and_output_models_document_the_tool_contract() -> None:
    FsReadInput(file_path="a.py", working_directory="/work")
    FsReadOutput(content="print(1)")
