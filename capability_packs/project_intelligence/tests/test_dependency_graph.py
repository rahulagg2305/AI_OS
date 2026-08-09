"""Deterministic, fake-sandbox unit tests for the `dependency.graph`
Tool — no database, no real subprocess (ADR-0004: a scripted fake
Protocol substitute is a legitimate stand-in for pure, deterministic
logic).

The real, live proof (a genuine `DockerSandbox` genuinely parsing a
real Python package's real imports) lives in
`test_dependency_graph_live.py`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ai_os_kernel.sandbox.models import SandboxResult
from ai_os_pack_project_intelligence.tools.dependency_graph import (
    _GRAPH_SCRIPT,
    DependencyGraphInput,
    DependencyGraphOutput,
    DependencyGraphToolEntrypoint,
    DependencyGraphToolInputError,
)


class _FakeSandbox:
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
        self.calls.append(
            {
                "command": tuple(command),
                "working_directory": working_directory,
                "stdin": stdin,
            }
        )
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


def _valid_inputs(**overrides: Any) -> dict[str, Any]:
    base = {
        "workingDirectory": "/repo",
        "pythonFiles": ["a.py"],
        "timeoutSeconds": 30.0,
        "maxOutputBytes": 1_000_000,
    }
    base.update(overrides)
    return base


def test_entrypoint_constructs_with_zero_arguments_and_starts_with_no_sandbox() -> None:
    tool = DependencyGraphToolEntrypoint()

    assert tool.sandbox is None
    assert tool.trust_tier.value == "tier1_sandboxed"


@pytest.mark.asyncio
async def test_execute_before_a_sandbox_is_injected_raises_a_clear_error() -> None:
    tool = DependencyGraphToolEntrypoint()

    with pytest.raises(DependencyGraphToolInputError, match="before a real sandbox"):
        await tool.execute(_valid_inputs())


@pytest.mark.asyncio
async def test_missing_required_fields_raise_a_clear_error() -> None:
    tool = DependencyGraphToolEntrypoint()
    tool.sandbox = _FakeSandbox({})

    with pytest.raises(DependencyGraphToolInputError, match="pythonFiles"):
        await tool.execute({"workingDirectory": "/repo", "maxOutputBytes": 1_000_000})


@pytest.mark.asyncio
async def test_python_files_must_be_a_list_of_strings() -> None:
    tool = DependencyGraphToolEntrypoint()
    tool.sandbox = _FakeSandbox({})

    with pytest.raises(DependencyGraphToolInputError, match="list of strings"):
        await tool.execute(_valid_inputs(pythonFiles="a.py"))


@pytest.mark.asyncio
async def test_a_real_graph_is_returned_and_python_files_delivered_via_stdin() -> None:
    tool = DependencyGraphToolEntrypoint()
    payload = {
        "nodes": [{"path": "a.py"}, {"path": "b.py"}],
        "edges": [{"from": "a.py", "to": "b.py", "importedName": "b"}],
        "unresolvedImports": [{"from": "a.py", "importedName": "os"}],
        "parseErrors": [],
    }
    sandbox = _FakeSandbox({("python3", "-c", _GRAPH_SCRIPT): _stdout_result(payload)})
    tool.sandbox = sandbox

    outputs = await tool.execute(_valid_inputs(pythonFiles=["a.py", "b.py"]))

    DependencyGraphOutput.model_validate(outputs)
    assert outputs == payload
    assert sandbox.calls[0]["working_directory"] == Path("/repo")
    assert json.loads(sandbox.calls[0]["stdin"]) == ["a.py", "b.py"]


@pytest.mark.asyncio
async def test_a_nonzero_exit_code_raises_a_clear_error() -> None:
    tool = DependencyGraphToolEntrypoint()
    tool.sandbox = _FakeSandbox(
        {
            ("python3", "-c", _GRAPH_SCRIPT): SandboxResult(
                exit_code=1,
                stdout="",
                stderr="boom",
                timed_out=False,
                truncated=False,
                duration_seconds=0.01,
            )
        }
    )

    with pytest.raises(DependencyGraphToolInputError, match="could not build the graph"):
        await tool.execute(_valid_inputs())


@pytest.mark.asyncio
async def test_a_timed_out_parse_raises_a_clear_error() -> None:
    tool = DependencyGraphToolEntrypoint()
    tool.sandbox = _FakeSandbox(
        {
            ("python3", "-c", _GRAPH_SCRIPT): SandboxResult(
                exit_code=None,
                stdout="",
                stderr="",
                timed_out=True,
                truncated=False,
                duration_seconds=30.0,
            )
        }
    )

    with pytest.raises(DependencyGraphToolInputError, match="timed out"):
        await tool.execute(_valid_inputs())


@pytest.mark.asyncio
async def test_a_truncated_result_is_refused_rather_than_silently_parsed() -> None:
    tool = DependencyGraphToolEntrypoint()
    tool.sandbox = _FakeSandbox(
        {
            ("python3", "-c", _GRAPH_SCRIPT): SandboxResult(
                exit_code=0,
                stdout='{"nodes": [',
                stderr="",
                timed_out=False,
                truncated=True,
                duration_seconds=1.0,
            )
        }
    )

    with pytest.raises(DependencyGraphToolInputError, match="truncated"):
        await tool.execute(_valid_inputs(maxOutputBytes=10))


def test_input_and_output_models_document_the_tool_contract() -> None:
    DependencyGraphInput(
        working_directory="/repo",
        python_files=["a.py"],
        timeout_seconds=30.0,
        max_output_bytes=1000,
    )
    DependencyGraphOutput(
        nodes=[{"path": "a.py"}],
        edges=[],
        unresolved_imports=[],
        parse_errors=[],
    )
