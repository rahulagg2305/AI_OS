"""Deterministic tests for the Performance Agent — no database, no LLM
call at all (this agent makes none — see its own module docstring),
but a genuine, non-mocked sandbox for every ``execute()``-level test:
every read in this file happens through a real
``LocalSubprocessSandbox``/real OS subprocess, so a passing test means
this agent genuinely read a real file's real bytes and computed a real
AST-derived complexity score, not an assertion about a mock's call
arguments.

**Proves this pack's newest agent independently first** — the
identical "prove each agent alone first, chain later" sequencing every
other agent in this pack's own history has followed (`test_lint_agent.py`,
this file's own direct template).
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
from ai_os_kernel.sandbox.executor import LocalSubprocessSandbox, SandboxExecutor
from ai_os_kernel.sdk_adapters.pack_context import build_pack_context
from ai_os_kernel.workflow_engine.models import StepType, WorkflowStep
from ai_os_kernel.workflow_engine.registry import InMemoryAgentRegistry
from ai_os_kernel.workflow_engine.step_executor import AgentStepExecutor
from ai_os_pack_software_engineering.agents.performance import (
    PerformanceAgentEntrypoint,
    PerformanceAgentInput,
    PerformanceAgentOutput,
    PerformanceInstructionError,
    _resolve_existing_file,
    compute_performance_report,
)
from ai_os_sdk.contracts import Agent as SdkAgent
from ai_os_sdk.contracts import PackContextReceiver

_AGENT_ID = "performance"
_PACK_ID = "software-engineering"
_PACK_VERSION = "0.1.0"

_SIMPLE_SOURCE = "def add(a, b):\n    return a + b\n"

# A real, high-complexity function: 11 independent `if` branches ->
# real cyclomatic complexity 12 (1 base + 11 decision points),
# genuinely over the real threshold of 10.
_COMPLEX_SOURCE = (
    "def check(x):\n"
    + "".join(f"    if x == {i}:\n        return {i}\n" for i in range(11))
    + "    return -1\n"
)


def _agent_with_sandbox(sandbox: SandboxExecutor) -> PerformanceAgentEntrypoint:
    agent = PerformanceAgentEntrypoint()
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
    JSON-encoded ``{workingDirectory, filePath}`` payload."""

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
    return WorkflowStep(id="run_performance", type=StepType.AGENT, agent_id=_AGENT_ID)


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_performance_agent_entrypoint_constructs_with_zero_arguments() -> None:
    agent = PerformanceAgentEntrypoint()

    assert agent.output_schema["required"] == [
        "filePath",
        "lineCount",
        "functionCount",
        "hotspots",
        "recommendations",
    ]


def test_compute_performance_report_reports_a_real_low_complexity_function() -> None:
    report = compute_performance_report(_SIMPLE_SOURCE, "add.py")

    assert report["functionCount"] == 1
    assert report["hotspots"][0]["name"] == "add"
    assert report["hotspots"][0]["complexity"] == 1
    assert report["recommendations"] == []


def test_compute_performance_report_flags_a_real_high_complexity_function() -> None:
    report = compute_performance_report(_COMPLEX_SOURCE, "check.py")

    assert report["hotspots"][0]["name"] == "check"
    assert report["hotspots"][0]["complexity"] == 12
    assert len(report["recommendations"]) == 1
    assert "check" in report["recommendations"][0]
    assert "12" in report["recommendations"][0]


def test_compute_performance_report_raises_on_genuinely_invalid_python() -> None:
    with pytest.raises(SyntaxError):
        compute_performance_report("def f(:\n    pass\n", "dirty.py")


@pytest.mark.asyncio
async def test_performance_agent_reports_a_genuine_report_via_direct_execute(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "add.py", _SIMPLE_SOURCE)
    agent = _agent_with_sandbox(LocalSubprocessSandbox())

    outputs = await agent.execute({"workingDirectory": str(tmp_path), "filePath": "add.py"})

    PerformanceAgentOutput.model_validate(outputs)
    assert outputs["functionCount"] == 1
    assert outputs["hotspots"][0]["complexity"] == 1


@pytest.mark.asyncio
async def test_performance_agent_rejects_a_syntactically_invalid_file_via_direct_execute(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "dirty.py", "def f(:\n    pass\n")
    agent = _agent_with_sandbox(LocalSubprocessSandbox())

    with pytest.raises(PerformanceInstructionError, match="not syntactically valid"):
        await agent.execute({"workingDirectory": str(tmp_path), "filePath": "dirty.py"})


@pytest.mark.asyncio
async def test_performance_agent_rejects_a_missing_file(tmp_path: Path) -> None:
    agent = _agent_with_sandbox(LocalSubprocessSandbox())

    with pytest.raises(PerformanceInstructionError, match="does not exist"):
        await agent.execute({"workingDirectory": str(tmp_path), "filePath": "does_not_exist.py"})


@pytest.mark.asyncio
async def test_performance_agent_rejects_a_path_that_escapes_the_working_directory(
    tmp_path: Path,
) -> None:
    agent = _agent_with_sandbox(LocalSubprocessSandbox())

    with pytest.raises(PerformanceInstructionError, match="resolves outside"):
        await agent.execute({"workingDirectory": str(tmp_path), "filePath": "../outside.py"})


@pytest.mark.asyncio
async def test_performance_agent_rejects_missing_required_fields() -> None:
    agent = _agent_with_sandbox(LocalSubprocessSandbox())

    with pytest.raises(PerformanceInstructionError, match="requires"):
        await agent.execute({})


@pytest.mark.asyncio
async def test_performance_agent_rejects_a_nonexistent_working_directory(tmp_path: Path) -> None:
    agent = _agent_with_sandbox(LocalSubprocessSandbox())
    missing = tmp_path / "does-not-exist"

    with pytest.raises(PerformanceInstructionError, match="does not exist or is not a directory"):
        await agent.execute({"workingDirectory": str(missing), "filePath": "add.py"})


def test_resolve_existing_file_rejects_a_blank_path(tmp_path: Path) -> None:
    with pytest.raises(PerformanceInstructionError, match="must not be blank"):
        _resolve_existing_file(tmp_path, "   ")


@pytest.mark.asyncio
async def test_performance_agent_genuinely_dispatches_through_agent_step_executor(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "add.py", _SIMPLE_SOURCE)
    payload = {"workingDirectory": str(tmp_path), "filePath": "add.py"}
    context_manager = DefaultContextManager([_FixedPayloadResolver(payload)])
    registry = InMemoryAgentRegistry({_AGENT_ID: _agent_with_sandbox(LocalSubprocessSandbox())})
    executor = AgentStepExecutor(registry, context_manager)

    outputs = await executor.execute(_step(), workflow_id="wf_test")

    PerformanceAgentOutput.model_validate(outputs)
    assert outputs["functionCount"] == 1


@pytest.mark.asyncio
async def test_performance_agent_via_agent_step_executor_rejects_a_malformed_context_payload(
    tmp_path: Path,
) -> None:
    context_manager = DefaultContextManager([_FixedPayloadResolver({"filePath": "add.py"})])
    registry = InMemoryAgentRegistry({_AGENT_ID: _agent_with_sandbox(LocalSubprocessSandbox())})
    executor = AgentStepExecutor(registry, context_manager)

    with pytest.raises(PerformanceInstructionError, match="missing"):
        await executor.execute(_step(), workflow_id="wf_test")


def test_performance_agent_input_documents_the_agent_contract() -> None:
    PerformanceAgentInput.model_validate({"workingDirectory": "workspace", "filePath": "a.py"})


@pytest.mark.asyncio
async def test_execute_before_bind_pack_context_raises_a_clear_error(tmp_path: Path) -> None:
    _write(tmp_path / "add.py", _SIMPLE_SOURCE)
    agent = PerformanceAgentEntrypoint()

    with pytest.raises(PerformanceInstructionError, match="bind_pack_context"):
        await agent.execute({"workingDirectory": str(tmp_path), "filePath": "add.py"})


def test_the_entrypoint_satisfies_both_sdk_protocols() -> None:
    agent = PerformanceAgentEntrypoint()

    assert isinstance(agent, SdkAgent)
    assert isinstance(agent, PackContextReceiver)
