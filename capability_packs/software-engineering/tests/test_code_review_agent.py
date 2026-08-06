"""Deterministic tests for the Code Reviewer Agent — no live LLM call
(ADR-0004: a deterministic Protocol implementation is a legitimate
substitute), but a genuine, non-mocked sandbox: this agent's own real
file *read* happens through a real ``LocalSubprocessSandbox``/real OS
subprocess, so a passing test means the agent's own prompt was built
from a file's genuinely-read real content, not an assertion about a
mock's call arguments.

``EchoLLMGateway`` echoes the *rendered prompt* verbatim (see that
class's own docstring) — since this agent expects a real JSON findings
array back, every test template here is a fixed JSON string, the
identical "the template itself is the expected completion" convention
``test_build_agent.py``'s own template already establishes for its own
delimited format.
"""

from __future__ import annotations

import asyncio
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
from ai_os_kernel.llm_gateway.gateway import EchoLLMGateway
from ai_os_kernel.prompt_engine.renderer import InMemoryPromptEngine
from ai_os_kernel.sandbox.executor import LocalSubprocessSandbox
from ai_os_kernel.sdk_adapters.pack_context import build_pack_context
from ai_os_kernel.workflow_engine.models import StepType, WorkflowStep
from ai_os_kernel.workflow_engine.registry import InMemoryAgentRegistry
from ai_os_kernel.workflow_engine.step_executor import AgentStepExecutor
from ai_os_pack_software_engineering.agents.code_review import (
    CodeReviewerAgentEntrypoint,
    CodeReviewerAgentOutput,
    CodeReviewInput,
    CodeReviewInstructionError,
    Finding,
    Severity,
    _parse_findings,
    _resolve_existing_file,
)
from ai_os_sdk.contracts import Agent as SdkAgent
from ai_os_sdk.contracts import PackContextReceiver

_AGENT_ID = "code-review"
_PACK_ID = "software-engineering"
_PACK_VERSION = "0.1.0"
_PROMPT_ID = "codereview.produce_findings"
_PROMPT_VERSION = "0.1.0"

_ONE_FINDING = json.dumps(
    [{"line": 2, "severity": "medium", "confidence": 0.8, "message": "unclear variable name"}]
)
_NO_FINDINGS: str = json.dumps([])


class _FixedPayloadResolver:
    """A fake `ContextSourceResolver` (ADR-0004: a legitimate test
    substitute) that always returns one item carrying a fixed,
    JSON-encoded ``{workingDirectory, filePath}`` payload — the real
    channel `CodeReviewerAgentEntrypoint` reads from when invoked
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


def _agent_with_prompt(template: str) -> CodeReviewerAgentEntrypoint:
    """The real, zero-arg-constructed entrypoint, bound to a real
    ``PackContext`` — identical construction sequence to
    ``test_security_analysis_agent.py``'s own ``_agent_with_sandbox``,
    extended with a real, Echo-backed gateway + prompt engine since
    this agent also calls an LLM."""
    agent = CodeReviewerAgentEntrypoint()
    agent.bind_pack_context(
        build_pack_context(
            pack_id=_PACK_ID,
            pack_version=_PACK_VERSION,
            permissions=["llm:invoke", "sandbox:execute"],
            llm_gateway=EchoLLMGateway(),
            prompt_engine=InMemoryPromptEngine(templates={(_PROMPT_ID, _PROMPT_VERSION): template}),
            sandbox=LocalSubprocessSandbox(),
        )
    )
    return agent


def _step() -> WorkflowStep:
    return WorkflowStep(
        id="review_code",
        type=StepType.AGENT,
        agent_id=_AGENT_ID,
        prompt_id=_PROMPT_ID,
        prompt_version=_PROMPT_VERSION,
        model_alias="coding-strong",
    )


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_code_reviewer_agent_entrypoint_constructs_with_zero_arguments() -> None:
    agent = CodeReviewerAgentEntrypoint()

    assert agent.output_schema["required"] == ["filePath", "findings"]


def test_the_entrypoint_satisfies_both_sdk_protocols() -> None:
    agent = CodeReviewerAgentEntrypoint()

    assert isinstance(agent, SdkAgent)
    assert isinstance(agent, PackContextReceiver)


@pytest.mark.asyncio
async def test_execute_before_bind_pack_context_raises_a_clear_error() -> None:
    agent = CodeReviewerAgentEntrypoint()

    with pytest.raises(CodeReviewInstructionError, match="bind_pack_context"):
        await agent.execute(
            {
                "promptId": _PROMPT_ID,
                "promptVersion": _PROMPT_VERSION,
                "modelAlias": "coding-strong",
                "workingDirectory": ".",
                "filePath": "x.py",
            }
        )


def _invocation(tmp_path: Path, file_path: str) -> dict[str, object]:
    return {
        "promptId": _PROMPT_ID,
        "promptVersion": _PROMPT_VERSION,
        "modelAlias": "coding-strong",
        "workingDirectory": str(tmp_path),
        "filePath": file_path,
    }


@pytest.mark.asyncio
async def test_code_reviewer_agent_reads_a_real_file_and_returns_a_real_finding(
    tmp_path: Path,
) -> None:
    """The real proof this agent exists for: the file's own real
    content is genuinely read out of the sandbox (proven by the
    working directory containing only the source file — the agent
    writes nothing), and the model's own real JSON completion becomes
    a real, validated Finding with `file` attached from the caller's
    own input, never the model's."""
    _write(tmp_path / "messy.py", "def add(a, b):\n\tx = a+b\n\treturn x\n")
    agent = _agent_with_prompt(_ONE_FINDING)

    outputs = await agent.execute(_invocation(tmp_path, "messy.py"))

    CodeReviewerAgentOutput.model_validate(outputs)
    assert outputs["filePath"] == "messy.py"
    assert len(outputs["findings"]) == 1
    finding = outputs["findings"][0]
    assert finding["file"] == "messy.py"
    assert finding["line"] == 2
    assert finding["severity"] == "medium"
    assert finding["confidence"] == 0.8
    # The agent writes nothing — only the source file exists afterward.
    names = await asyncio.to_thread(lambda: [p.name for p in tmp_path.iterdir()])
    assert names == ["messy.py"]


@pytest.mark.asyncio
async def test_code_reviewer_agent_returns_an_empty_list_for_a_clean_file(tmp_path: Path) -> None:
    _write(tmp_path / "clean.py", "def add(a, b):\n    return a + b\n")
    agent = _agent_with_prompt(_NO_FINDINGS)

    outputs = await agent.execute(_invocation(tmp_path, "clean.py"))

    assert outputs["findings"] == []


@pytest.mark.asyncio
async def test_code_reviewer_agent_rejects_a_non_json_completion(tmp_path: Path) -> None:
    _write(tmp_path / "x.py", "pass\n")
    agent = _agent_with_prompt("this is not json at all")

    with pytest.raises(CodeReviewInstructionError, match="not valid JSON"):
        await agent.execute(_invocation(tmp_path, "x.py"))


@pytest.mark.asyncio
async def test_code_reviewer_agent_rejects_an_out_of_range_confidence(tmp_path: Path) -> None:
    _write(tmp_path / "x.py", "pass\n")
    bad = json.dumps([{"line": 1, "severity": "high", "confidence": 1.5, "message": "x"}])
    agent = _agent_with_prompt(bad)

    with pytest.raises(CodeReviewInstructionError, match="did not match the documented"):
        await agent.execute(_invocation(tmp_path, "x.py"))


@pytest.mark.asyncio
async def test_code_reviewer_agent_rejects_an_unknown_severity(tmp_path: Path) -> None:
    _write(tmp_path / "x.py", "pass\n")
    bad = json.dumps([{"line": 1, "severity": "critical", "confidence": 0.5, "message": "x"}])
    agent = _agent_with_prompt(bad)

    with pytest.raises(CodeReviewInstructionError, match="did not match the documented"):
        await agent.execute(_invocation(tmp_path, "x.py"))


@pytest.mark.asyncio
async def test_code_reviewer_agent_dispatches_through_agent_step_executor(tmp_path: Path) -> None:
    """The real end-to-end proof this step exists for: a real
    WorkflowStep of type agent, dispatched through the real
    AgentStepExecutor with a real (fake-resolver-backed) Context
    Manager — the identical dispatch chain every other agent in this
    pack's own test suite proves, not only a direct `execute()` call."""
    _write(tmp_path / "messy.py", "def add(a, b):\n\tx = a+b\n\treturn x\n")
    payload = {"workingDirectory": str(tmp_path), "filePath": "messy.py"}
    context_manager = DefaultContextManager([_FixedPayloadResolver(payload)])
    registry = InMemoryAgentRegistry({_AGENT_ID: _agent_with_prompt(_ONE_FINDING)})
    executor = AgentStepExecutor(registry, context_manager)

    outputs = await executor.execute(_step(), workflow_id="wf_test")

    CodeReviewerAgentOutput.model_validate(outputs)
    assert len(outputs["findings"]) == 1


@pytest.mark.asyncio
async def test_code_reviewer_agent_rejects_a_missing_file(tmp_path: Path) -> None:
    agent = _agent_with_prompt(_NO_FINDINGS)

    with pytest.raises(CodeReviewInstructionError, match="does not exist"):
        await agent.execute(
            {
                "promptId": _PROMPT_ID,
                "promptVersion": _PROMPT_VERSION,
                "modelAlias": "coding-strong",
                "workingDirectory": str(tmp_path),
                "filePath": "does_not_exist.py",
            }
        )


@pytest.mark.asyncio
async def test_code_reviewer_agent_rejects_a_nonexistent_working_directory(
    tmp_path: Path,
) -> None:
    agent = _agent_with_prompt(_NO_FINDINGS)
    missing = tmp_path / "does-not-exist"

    with pytest.raises(CodeReviewInstructionError, match="does not exist or is not a"):
        await agent.execute(
            {
                "promptId": _PROMPT_ID,
                "promptVersion": _PROMPT_VERSION,
                "modelAlias": "coding-strong",
                "workingDirectory": str(missing),
                "filePath": "x.py",
            }
        )


@pytest.mark.asyncio
async def test_missing_required_invocation_fields_raise_a_clear_error(tmp_path: Path) -> None:
    _write(tmp_path / "x.py", "pass\n")
    agent = _agent_with_prompt(_NO_FINDINGS)

    with pytest.raises(CodeReviewInstructionError, match="promptId"):
        await agent.execute(
            {
                "modelAlias": "coding-strong",
                "workingDirectory": str(tmp_path),
                "filePath": "x.py",
            }
        )


def test_resolve_existing_file_rejects_a_blank_path(tmp_path: Path) -> None:
    with pytest.raises(CodeReviewInstructionError, match="must not be blank"):
        _resolve_existing_file(tmp_path, "   ")


def test_parse_findings_attaches_the_real_caller_supplied_file_path() -> None:
    findings = _parse_findings(_ONE_FINDING, file_path="a/b.py")

    assert findings == [
        Finding(
            file="a/b.py",
            line=2,
            severity=Severity.MEDIUM,
            confidence=0.8,
            message="unclear variable name",
        )
    ]


def test_code_review_input_documents_the_agent_contract() -> None:
    CodeReviewInput.model_validate({"workingDirectory": "workspace", "filePath": "a.py"})
