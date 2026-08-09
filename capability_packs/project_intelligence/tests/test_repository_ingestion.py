"""Deterministic, fake-sandbox unit tests for the `repository.ingest`
Tool — no database, no real subprocess (ADR-0004: a scripted fake
Protocol substitute is a legitimate stand-in for pure, deterministic
logic).

The real, live proof (a genuine `DockerSandbox` genuinely walking a
real directory tree) lives in `test_repository_ingestion_live.py`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ai_os_kernel.sandbox.models import SandboxResult
from ai_os_pack_project_intelligence.tools.repository_ingestion import (
    _INGEST_SCRIPT,
    RepositoryIngestionInput,
    RepositoryIngestionOutput,
    RepositoryIngestionToolEntrypoint,
    RepositoryIngestionToolInputError,
)


class _FakeSandbox:
    """Scripted by (command tuple) -> :class:`SandboxResult`."""

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


def _stdout_result(payload: dict[str, Any]) -> SandboxResult:
    return SandboxResult(
        exit_code=0,
        stdout=json.dumps(payload),
        stderr="",
        timed_out=False,
        truncated=False,
        duration_seconds=0.01,
    )


def test_entrypoint_constructs_with_zero_arguments_and_starts_with_no_sandbox() -> None:
    tool = RepositoryIngestionToolEntrypoint()

    assert tool.sandbox is None
    assert tool.output_schema["required"] == ["fileCount", "languageCounts", "modules", "files"]


@pytest.mark.asyncio
async def test_execute_before_a_sandbox_is_injected_raises_a_clear_error() -> None:
    tool = RepositoryIngestionToolEntrypoint()

    with pytest.raises(RepositoryIngestionToolInputError, match="before a real sandbox"):
        await tool.execute(
            {"workingDirectory": "/repo", "timeoutSeconds": 30.0, "maxOutputBytes": 1_000_000}
        )


@pytest.mark.asyncio
async def test_missing_required_fields_raise_a_clear_error() -> None:
    tool = RepositoryIngestionToolEntrypoint()
    tool.sandbox = _FakeSandbox({})

    with pytest.raises(RepositoryIngestionToolInputError, match="timeoutSeconds"):
        await tool.execute({"workingDirectory": "/repo", "maxOutputBytes": 1_000_000})


@pytest.mark.asyncio
async def test_a_real_ingestion_returns_the_structural_model() -> None:
    tool = RepositoryIngestionToolEntrypoint()
    payload = {
        "fileCount": 2,
        "languageCounts": {"python": 1, "markdown": 1},
        "modules": [{"name": "src", "fileCount": 1}, {"name": ".", "fileCount": 1}],
        "files": [
            {"path": "README.md", "language": "markdown"},
            {"path": "src/main.py", "language": "python"},
        ],
    }
    sandbox = _FakeSandbox({("python3", "-c", _INGEST_SCRIPT): _stdout_result(payload)})
    tool.sandbox = sandbox

    outputs = await tool.execute(
        {"workingDirectory": "/repo", "timeoutSeconds": 30.0, "maxOutputBytes": 1_000_000}
    )

    RepositoryIngestionOutput.model_validate(outputs)
    assert outputs == payload
    assert sandbox.calls[0]["working_directory"] == Path("/repo")


@pytest.mark.asyncio
async def test_a_nonzero_exit_code_raises_a_clear_error() -> None:
    tool = RepositoryIngestionToolEntrypoint()
    tool.sandbox = _FakeSandbox(
        {
            ("python3", "-c", _INGEST_SCRIPT): SandboxResult(
                exit_code=1,
                stdout="",
                stderr="FileNotFoundError",
                timed_out=False,
                truncated=False,
                duration_seconds=0.01,
            )
        }
    )

    with pytest.raises(RepositoryIngestionToolInputError, match="could not ingest"):
        await tool.execute(
            {"workingDirectory": "/missing", "timeoutSeconds": 30.0, "maxOutputBytes": 1_000_000}
        )


@pytest.mark.asyncio
async def test_a_timed_out_walk_raises_a_clear_error() -> None:
    tool = RepositoryIngestionToolEntrypoint()
    tool.sandbox = _FakeSandbox(
        {
            ("python3", "-c", _INGEST_SCRIPT): SandboxResult(
                exit_code=None,
                stdout="",
                stderr="",
                timed_out=True,
                truncated=False,
                duration_seconds=30.0,
            )
        }
    )

    with pytest.raises(RepositoryIngestionToolInputError, match="timed out"):
        await tool.execute(
            {"workingDirectory": "/huge", "timeoutSeconds": 30.0, "maxOutputBytes": 1_000_000}
        )


@pytest.mark.asyncio
async def test_a_truncated_result_is_refused_rather_than_silently_parsed() -> None:
    tool = RepositoryIngestionToolEntrypoint()
    tool.sandbox = _FakeSandbox(
        {
            ("python3", "-c", _INGEST_SCRIPT): SandboxResult(
                exit_code=0,
                stdout='{"fileCount": 999,',  # deliberately cut off
                stderr="",
                timed_out=False,
                truncated=True,
                duration_seconds=1.0,
            )
        }
    )

    with pytest.raises(RepositoryIngestionToolInputError, match="truncated"):
        await tool.execute(
            {"workingDirectory": "/big", "timeoutSeconds": 30.0, "maxOutputBytes": 10}
        )


def test_input_and_output_models_document_the_tool_contract() -> None:
    RepositoryIngestionInput(
        working_directory="/repo", timeout_seconds=30.0, max_output_bytes=1_000_000
    )
    RepositoryIngestionOutput(
        file_count=1,
        language_counts={"python": 1},
        modules=[{"name": ".", "fileCount": 1}],
        files=[{"path": "a.py", "language": "python"}],
    )
