"""Deterministic, fake-sandbox unit tests for the `build.run` Tool — no
database, no real subprocess (ADR-0004: a scripted fake Protocol
substitute is a legitimate stand-in for pure, deterministic logic).

The real, live proof (a genuine `SqlToolRegistry` resolution + a real
`LocalSubprocessSandbox` running a real command) lives in
`tests/integration/workflow_engine/test_registry.py`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ai_os_kernel.sandbox.models import SandboxResult
from ai_os_pack_software_engineering.tools.build_run import (
    BuildRunInput,
    BuildRunOutput,
    BuildRunToolEntrypoint,
    BuildRunToolInputError,
)


class _FakeSandbox:
    """Scripted by (command tuple) -> :class:`SandboxResult`; records
    every call, including the real `working_directory` passed."""

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
        self.calls.append(
            {
                "command": tuple(command),
                "working_directory": working_directory,
                "timeout_seconds": timeout_seconds,
                "max_output_bytes": max_output_bytes,
            }
        )
        key = tuple(command)
        if key not in self._scripted:
            raise AssertionError(f"unscripted command: {command!r}")
        return self._scripted[key]


def test_entrypoint_constructs_with_zero_arguments_and_starts_with_no_sandbox() -> None:
    tool = BuildRunToolEntrypoint()

    assert tool.sandbox is None
    assert tool.output_schema["required"] == [
        "exitCode",
        "stdout",
        "stderr",
        "timedOut",
        "truncated",
        "durationSeconds",
    ]


@pytest.mark.asyncio
async def test_execute_before_a_sandbox_is_injected_raises_a_clear_error() -> None:
    tool = BuildRunToolEntrypoint()

    with pytest.raises(BuildRunToolInputError, match="before a real sandbox was injected"):
        await tool.execute(
            {
                "command": ["pytest"],
                "workingDirectory": "/work",
                "timeoutSeconds": 30.0,
                "maxOutputBytes": 1000,
            }
        )


@pytest.mark.asyncio
async def test_missing_required_fields_raise_a_clear_error() -> None:
    tool = BuildRunToolEntrypoint()
    tool.sandbox = _FakeSandbox({})

    with pytest.raises(BuildRunToolInputError, match="workingDirectory"):
        await tool.execute({"command": ["pytest"]})


@pytest.mark.asyncio
async def test_a_non_list_command_raises_a_clear_error() -> None:
    tool = BuildRunToolEntrypoint()
    tool.sandbox = _FakeSandbox({})

    with pytest.raises(BuildRunToolInputError, match="non-empty list of strings"):
        await tool.execute(
            {
                "command": "pytest",
                "workingDirectory": "/work",
                "timeoutSeconds": 30.0,
                "maxOutputBytes": 1000,
            }
        )


@pytest.mark.asyncio
async def test_a_real_run_returns_the_full_sandbox_result_shape() -> None:
    tool = BuildRunToolEntrypoint()
    sandbox = _FakeSandbox(
        {
            ("pytest", "-q"): SandboxResult(
                exit_code=0,
                stdout="3 passed",
                stderr="",
                timed_out=False,
                truncated=False,
                duration_seconds=1.5,
            )
        }
    )
    tool.sandbox = sandbox

    outputs = await tool.execute(
        {
            "command": ["pytest", "-q"],
            "workingDirectory": "/work",
            "timeoutSeconds": 30.0,
            "maxOutputBytes": 1_000_000,
        }
    )

    BuildRunOutput.model_validate(outputs)
    assert outputs == {
        "exitCode": 0,
        "stdout": "3 passed",
        "stderr": "",
        "timedOut": False,
        "truncated": False,
        "durationSeconds": 1.5,
    }
    assert sandbox.calls[0]["working_directory"] == Path("/work")
    assert sandbox.calls[0]["timeout_seconds"] == 30.0
    assert sandbox.calls[0]["max_output_bytes"] == 1_000_000


def test_input_and_output_models_document_the_tool_contract() -> None:
    BuildRunInput(
        command=["pytest"], working_directory="/work", timeout_seconds=30.0, max_output_bytes=1000
    )
    BuildRunOutput(
        exit_code=0,
        stdout="ok",
        stderr="",
        timed_out=False,
        truncated=False,
        duration_seconds=0.1,
    )
