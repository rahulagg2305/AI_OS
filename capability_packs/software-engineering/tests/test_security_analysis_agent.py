"""Deterministic tests for the Security Analysis Agent — no database,
no LLM call at all (this agent makes none — see its own module
docstring), but a genuine, non-mocked sandbox and a genuine, real
embedded ``ast``-scan invocation: every run in this file happens
through a real ``LocalSubprocessSandbox``/real OS subprocess, so a
passing test means the scan script genuinely found (or didn't find) a
real, AST-precise security pattern, not an assertion about a mock's
call arguments.

**Proves this pack's tenth agent independently first, before it could
ever be chained into `se.delivery_pipeline`** — the identical "prove
each agent alone first, chain later" sequencing every other agent in
this pack's own history has followed. Directly mirrors
``test_lint_agent.py``'s own shape (its own direct template),
substituting the fixed embedded scan for ``lintCommand``/``py_compile``
and ``findings`` for ``output``.
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
from ai_os_pack_software_engineering.agents.security_analysis import (
    SecurityAnalysisAgentEntrypoint,
    SecurityAnalysisInput,
    SecurityAnalysisInstructionError,
    SecurityAnalysisOutput,
    _resolve_existing_file,
)
from ai_os_sdk.contracts import Agent as SdkAgent
from ai_os_sdk.contracts import PackContextReceiver

_AGENT_ID = "security-analysis"
_PACK_ID = "software-engineering"
_PACK_VERSION = "0.1.0"

_VULNERABLE_SOURCE = (
    "eval('1+1')\n"
    "import subprocess\n"
    "subprocess.run(['ls'], shell=True)\n"
    "import pickle\n"
    "pickle.loads(b'')\n"
    "import yaml\n"
    "yaml.load('x')\n"
)
_CLEAN_SOURCE = "def add(a, b):\n    return a + b\n"


def _agent_with_sandbox(sandbox: SandboxExecutor) -> SecurityAnalysisAgentEntrypoint:
    """The real, zero-arg-constructed entrypoint, bound to a real
    ``PackContext`` granting exactly ``sandbox:execute`` over
    ``sandbox`` — the same construction+injection sequence
    ``test_lint_agent.py``'s own ``_agent_with_sandbox`` establishes."""
    agent = SecurityAnalysisAgentEntrypoint()
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
    JSON-encoded ``{workingDirectory, filePath}`` payload — the real
    channel `SecurityAnalysisAgentEntrypoint` reads from when invoked
    through a real `AgentStepExecutor`."""

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
    return WorkflowStep(id="run_security_analysis", type=StepType.AGENT, agent_id=_AGENT_ID)


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_security_analysis_agent_entrypoint_constructs_with_zero_arguments() -> None:
    """The exact call EntrypointLoader/SqlAgentRegistry make in
    production — must succeed instantly, with no I/O."""
    agent = SecurityAnalysisAgentEntrypoint()

    assert agent.output_schema["required"] == ["passed", "exitCode", "findings"]


@pytest.mark.asyncio
async def test_security_analysis_agent_reports_a_genuine_clean_case_via_direct_execute(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "clean.py", _CLEAN_SOURCE)
    agent = _agent_with_sandbox(LocalSubprocessSandbox())

    outputs = await agent.execute({"workingDirectory": str(tmp_path), "filePath": "clean.py"})

    SecurityAnalysisOutput.model_validate(outputs)
    assert outputs["passed"] is True
    assert outputs["exitCode"] == 0
    assert outputs["findings"] == []


@pytest.mark.asyncio
async def test_security_analysis_agent_reports_a_genuine_violating_case_via_direct_execute(
    tmp_path: Path,
) -> None:
    """The real proof this agent exists for: four genuinely dangerous,
    AST-precise patterns in one file are all found — not a stand-in,
    the real embedded scan script's own real findings."""
    _write(tmp_path / "dirty.py", _VULNERABLE_SOURCE)
    agent = _agent_with_sandbox(LocalSubprocessSandbox())

    outputs = await agent.execute({"workingDirectory": str(tmp_path), "filePath": "dirty.py"})

    SecurityAnalysisOutput.model_validate(outputs)
    assert outputs["passed"] is False
    assert outputs["exitCode"] == 1
    rules = {finding["rule"] for finding in outputs["findings"]}
    assert rules == {
        "dangerous-call",
        "subprocess-shell-true",
        "unsafe-deserialization",
        "unsafe-yaml-load",
    }


@pytest.mark.asyncio
async def test_security_analysis_agent_does_not_flag_yaml_load_with_an_explicit_loader(
    tmp_path: Path,
) -> None:
    """A real, deliberate negative case: `yaml.load(x, Loader=...)` is
    the safe form and must not be flagged — proves the check is
    AST-precise, not a blunt substring match on `yaml.load`."""
    _write(tmp_path / "safe_yaml.py", "import yaml\nyaml.load('x', Loader=yaml.SafeLoader)\n")
    agent = _agent_with_sandbox(LocalSubprocessSandbox())

    outputs = await agent.execute({"workingDirectory": str(tmp_path), "filePath": "safe_yaml.py"})

    assert outputs["passed"] is True
    assert outputs["findings"] == []


@pytest.mark.asyncio
async def test_security_analysis_agent_rejects_a_missing_file(tmp_path: Path) -> None:
    agent = _agent_with_sandbox(LocalSubprocessSandbox())

    with pytest.raises(SecurityAnalysisInstructionError, match="does not exist"):
        await agent.execute({"workingDirectory": str(tmp_path), "filePath": "does_not_exist.py"})


@pytest.mark.asyncio
async def test_security_analysis_agent_rejects_a_path_that_escapes_the_working_directory(
    tmp_path: Path,
) -> None:
    agent = _agent_with_sandbox(LocalSubprocessSandbox())

    with pytest.raises(SecurityAnalysisInstructionError, match="resolves outside"):
        await agent.execute({"workingDirectory": str(tmp_path), "filePath": "../outside.py"})


@pytest.mark.asyncio
async def test_security_analysis_agent_rejects_missing_required_fields() -> None:
    agent = _agent_with_sandbox(LocalSubprocessSandbox())

    with pytest.raises(SecurityAnalysisInstructionError, match="requires"):
        await agent.execute({})


@pytest.mark.asyncio
async def test_security_analysis_agent_rejects_a_nonexistent_working_directory(
    tmp_path: Path,
) -> None:
    agent = _agent_with_sandbox(LocalSubprocessSandbox())
    missing = tmp_path / "does-not-exist"

    with pytest.raises(
        SecurityAnalysisInstructionError, match="does not exist or is not a directory"
    ):
        await agent.execute({"workingDirectory": str(missing), "filePath": "clean.py"})


def test_resolve_existing_file_rejects_a_blank_path(tmp_path: Path) -> None:
    with pytest.raises(SecurityAnalysisInstructionError, match="must not be blank"):
        _resolve_existing_file(tmp_path, "   ")


@pytest.mark.asyncio
async def test_security_analysis_agent_dispatches_through_agent_step_executor_passing(
    tmp_path: Path,
) -> None:
    """The real end-to-end proof this step exists for (the passing
    half): a real WorkflowStep of type agent, dispatched through the
    real AgentStepExecutor with a real (fake-resolver-backed) Context
    Manager, genuinely runs the scan inside the sandbox and reports a
    genuinely correct pass outcome."""
    _write(tmp_path / "clean.py", _CLEAN_SOURCE)
    payload = {"workingDirectory": str(tmp_path), "filePath": "clean.py"}
    context_manager = DefaultContextManager([_FixedPayloadResolver(payload)])
    registry = InMemoryAgentRegistry({_AGENT_ID: _agent_with_sandbox(LocalSubprocessSandbox())})
    executor = AgentStepExecutor(registry, context_manager)

    outputs = await executor.execute(_step(), workflow_id="wf_test")

    SecurityAnalysisOutput.model_validate(outputs)
    assert outputs["passed"] is True


@pytest.mark.asyncio
async def test_security_analysis_agent_dispatches_through_agent_step_executor_violating(
    tmp_path: Path,
) -> None:
    """The real end-to-end proof this step exists for (the violating
    half): the identical dispatch chain, against a file with real
    dangerous patterns, genuinely reports a correct fail outcome with
    real findings."""
    _write(tmp_path / "dirty.py", _VULNERABLE_SOURCE)
    payload = {"workingDirectory": str(tmp_path), "filePath": "dirty.py"}
    context_manager = DefaultContextManager([_FixedPayloadResolver(payload)])
    registry = InMemoryAgentRegistry({_AGENT_ID: _agent_with_sandbox(LocalSubprocessSandbox())})
    executor = AgentStepExecutor(registry, context_manager)

    outputs = await executor.execute(_step(), workflow_id="wf_test")

    SecurityAnalysisOutput.model_validate(outputs)
    assert outputs["passed"] is False
    assert len(outputs["findings"]) == 4


def test_security_analysis_input_documents_the_agent_contract() -> None:
    SecurityAnalysisInput.model_validate({"workingDirectory": "workspace", "filePath": "a.py"})


@pytest.mark.asyncio
async def test_execute_before_bind_pack_context_raises_a_clear_error(tmp_path: Path) -> None:
    _write(tmp_path / "clean.py", _CLEAN_SOURCE)
    agent = SecurityAnalysisAgentEntrypoint()

    with pytest.raises(SecurityAnalysisInstructionError, match="bind_pack_context"):
        await agent.execute({"workingDirectory": str(tmp_path), "filePath": "clean.py"})


def test_the_entrypoint_satisfies_both_sdk_protocols() -> None:
    agent = SecurityAnalysisAgentEntrypoint()

    assert isinstance(agent, SdkAgent)
    assert isinstance(agent, PackContextReceiver)
