"""Deterministic tests for the Refactoring Agent — no live LLM call
(ADR-0004: a deterministic Protocol implementation is a legitimate
substitute), but a genuine, non-mocked sandbox: every read/run/write in
this file happens through a real ``LocalSubprocessSandbox``/real OS
subprocess.

``EchoLLMGateway`` echoes the *rendered prompt* verbatim — since this
agent expects a real ``FILE_CONTENT_BEGIN``/``FILE_CONTENT_END``
completion back, every test template here is a fixed string ignoring
the real ``{{instruction}}``/``{{code}}`` interpolation, the identical
"the template itself is the expected completion" convention
``test_code_review_agent.py``'s own templates already establish.

The real proof this file exists for: a genuine before/after test
comparison against a real Python file, run through a real subprocess
twice.
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
from ai_os_kernel.llm_gateway.gateway import EchoLLMGateway
from ai_os_kernel.prompt_engine.renderer import InMemoryPromptEngine
from ai_os_kernel.sandbox.executor import LocalSubprocessSandbox
from ai_os_kernel.sdk_adapters.pack_context import build_pack_context
from ai_os_kernel.workflow_engine.models import StepType, WorkflowStep
from ai_os_kernel.workflow_engine.registry import InMemoryAgentRegistry
from ai_os_kernel.workflow_engine.step_executor import AgentStepExecutor
from ai_os_pack_software_engineering.agents.refactoring import (
    RefactoringAgentEntrypoint,
    RefactoringAgentOutput,
    RefactoringInput,
    RefactoringInstructionError,
    _parse_refactored_content,
    _resolve_existing_file,
)
from ai_os_sdk.contracts import Agent as SdkAgent
from ai_os_sdk.contracts import PackContextReceiver

_AGENT_ID = "refactoring"
_PACK_ID = "software-engineering"
_PACK_VERSION = "0.1.0"
_PROMPT_ID = "refactoring.rewrite_file"
_PROMPT_VERSION = "0.1.0"
_PYTHON = sys.executable

_PASSING_ORIGINAL = "def add(a, b):\n    return a + b\n\nassert add(2, 3) == 5\n"
_PASSING_REFACTORED_TEMPLATE = (
    "FILE_CONTENT_BEGIN\n"
    "def add(x, y):\n    return x + y\n\nassert add(2, 3) == 5\n"
    "FILE_CONTENT_END"
)
_BEHAVIOUR_CHANGING_REFACTORED_TEMPLATE = (
    "FILE_CONTENT_BEGIN\n"
    "def add(x, y):\n    return x - y\n\nassert add(2, 3) == 5\n"
    "FILE_CONTENT_END"
)
_FAILING_ORIGINAL = "def add(a, b):\n    return a - a\n\nassert add(2, 3) == 5\n"


def _agent_with_prompt(template: str) -> RefactoringAgentEntrypoint:
    agent = RefactoringAgentEntrypoint()
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
        id="refactor",
        type=StepType.AGENT,
        agent_id=_AGENT_ID,
        prompt_id=_PROMPT_ID,
        prompt_version=_PROMPT_VERSION,
        model_alias="coding-strong",
    )


def _invocation(
    tmp_path: Path, *, instruction: str = "Rename the parameters."
) -> dict[str, object]:
    return {
        "promptId": _PROMPT_ID,
        "promptVersion": _PROMPT_VERSION,
        "modelAlias": "coding-strong",
        "workingDirectory": str(tmp_path),
        "filePath": "calc.py",
        "runCommand": [_PYTHON, "calc.py"],
        "instruction": instruction,
    }


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


class _FixedPayloadResolver:
    """A fake `ContextSourceResolver` (ADR-0004: a legitimate test
    substitute) that always returns one item carrying a fixed,
    JSON-encoded payload — the real channel `RefactoringAgentEntrypoint`
    reads from when invoked through a real `AgentStepExecutor`."""

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


def test_refactoring_agent_entrypoint_constructs_with_zero_arguments() -> None:
    agent = RefactoringAgentEntrypoint()

    assert agent.output_schema["required"] == [
        "workingDirectory",
        "filePath",
        "passedBefore",
        "passedAfter",
        "refactored",
        "outputBefore",
        "outputAfter",
    ]


def test_the_entrypoint_satisfies_both_sdk_protocols() -> None:
    agent = RefactoringAgentEntrypoint()

    assert isinstance(agent, SdkAgent)
    assert isinstance(agent, PackContextReceiver)


@pytest.mark.asyncio
async def test_execute_before_bind_pack_context_raises_a_clear_error(tmp_path: Path) -> None:
    agent = RefactoringAgentEntrypoint()

    with pytest.raises(RefactoringInstructionError, match="bind_pack_context"):
        await agent.execute(_invocation(tmp_path))


@pytest.mark.asyncio
async def test_refactoring_agent_genuinely_refactors_a_real_file_preserving_behaviour(
    tmp_path: Path,
) -> None:
    """The real proof this agent exists for: a genuine before/after test
    run against a real Python file, through a real subprocess — the
    refactored version genuinely replaces the original on disk, and
    both runs genuinely pass."""
    _write(tmp_path / "calc.py", _PASSING_ORIGINAL)
    agent = _agent_with_prompt(_PASSING_REFACTORED_TEMPLATE)

    outputs = await agent.execute(_invocation(tmp_path))

    RefactoringAgentOutput.model_validate(outputs)
    assert outputs["passedBefore"] is True
    assert outputs["passedAfter"] is True
    assert outputs["refactored"] is True
    written = (tmp_path / "calc.py").read_text(encoding="utf-8")
    assert "def add(x, y):" in written
    assert "def add(a, b):" not in written


@pytest.mark.asyncio
async def test_refactoring_agent_reports_a_genuine_behaviour_regression(tmp_path: Path) -> None:
    """`refactored` is mechanically derived, never a second LLM
    judgment: a real behaviour change (subtraction instead of addition)
    genuinely fails the after-run, and is reported as such — the file
    on disk still reflects the model's own (bad) refactor, matching
    `build.py`'s own "write happens, pass/fail is reported separately"
    precedent; this agent does not roll back a failed refactor."""
    _write(tmp_path / "calc.py", _PASSING_ORIGINAL)
    agent = _agent_with_prompt(_BEHAVIOUR_CHANGING_REFACTORED_TEMPLATE)

    outputs = await agent.execute(_invocation(tmp_path))

    assert outputs["passedBefore"] is True
    assert outputs["passedAfter"] is False
    assert outputs["refactored"] is False


@pytest.mark.asyncio
async def test_refactoring_agent_refuses_when_the_baseline_itself_does_not_pass(
    tmp_path: Path,
) -> None:
    """FR-043's own real precondition: no valid baseline behaviour
    means nothing to preserve — refused before any LLM call or write."""
    _write(tmp_path / "calc.py", _FAILING_ORIGINAL)
    agent = _agent_with_prompt(_PASSING_REFACTORED_TEMPLATE)

    with pytest.raises(RefactoringInstructionError, match="baseline test run"):
        await agent.execute(_invocation(tmp_path))

    # The file is genuinely untouched — no write was ever attempted.
    assert (tmp_path / "calc.py").read_text(encoding="utf-8") == _FAILING_ORIGINAL


@pytest.mark.asyncio
async def test_refactoring_agent_rejects_a_malformed_completion(tmp_path: Path) -> None:
    _write(tmp_path / "calc.py", _PASSING_ORIGINAL)
    agent = _agent_with_prompt("this is not the documented format at all")

    with pytest.raises(RefactoringInstructionError, match="did not follow the documented"):
        await agent.execute(_invocation(tmp_path))


@pytest.mark.asyncio
async def test_refactoring_agent_dispatches_through_agent_step_executor(tmp_path: Path) -> None:
    """The real end-to-end proof this step exists for: a real
    WorkflowStep of type agent, dispatched through the real
    AgentStepExecutor with a real (fake-resolver-backed) Context
    Manager — the identical dispatch chain every other agent in this
    pack's own test suite proves, not only a direct `execute()` call."""
    _write(tmp_path / "calc.py", _PASSING_ORIGINAL)
    payload = {
        "workingDirectory": str(tmp_path),
        "filePath": "calc.py",
        "runCommand": [_PYTHON, "calc.py"],
        "instruction": "Rename the parameters.",
    }
    context_manager = DefaultContextManager([_FixedPayloadResolver(payload)])
    registry = InMemoryAgentRegistry({_AGENT_ID: _agent_with_prompt(_PASSING_REFACTORED_TEMPLATE)})
    executor = AgentStepExecutor(registry, context_manager)

    outputs = await executor.execute(_step(), workflow_id="wf_test")

    RefactoringAgentOutput.model_validate(outputs)
    assert outputs["refactored"] is True


@pytest.mark.asyncio
async def test_refactoring_agent_rejects_a_missing_file(tmp_path: Path) -> None:
    agent = _agent_with_prompt(_PASSING_REFACTORED_TEMPLATE)

    with pytest.raises(RefactoringInstructionError, match="does not exist"):
        await agent.execute(
            {
                "promptId": _PROMPT_ID,
                "promptVersion": _PROMPT_VERSION,
                "modelAlias": "coding-strong",
                "workingDirectory": str(tmp_path),
                "filePath": "does_not_exist.py",
                "runCommand": [_PYTHON, "does_not_exist.py"],
                "instruction": "unused",
            }
        )


@pytest.mark.asyncio
async def test_missing_required_invocation_fields_raise_a_clear_error(tmp_path: Path) -> None:
    _write(tmp_path / "calc.py", _PASSING_ORIGINAL)
    agent = _agent_with_prompt(_PASSING_REFACTORED_TEMPLATE)

    with pytest.raises(RefactoringInstructionError, match="workingDirectory"):
        await agent.execute({"modelAlias": "coding-strong"})


def test_resolve_existing_file_rejects_a_blank_path(tmp_path: Path) -> None:
    with pytest.raises(RefactoringInstructionError, match="must not be blank"):
        _resolve_existing_file(tmp_path, "   ")


def test_parse_refactored_content_extracts_the_content() -> None:
    content = _parse_refactored_content("FILE_CONTENT_BEGIN\nx = 1\nFILE_CONTENT_END")

    assert content == "x = 1"


def test_refactoring_input_documents_the_agent_contract() -> None:
    RefactoringInput.model_validate(
        {
            "workingDirectory": "workspace",
            "filePath": "a.py",
            "runCommand": ["python", "a.py"],
            "instruction": "Rename the parameters.",
        }
    )
