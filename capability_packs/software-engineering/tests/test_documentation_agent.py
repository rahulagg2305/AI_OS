"""Deterministic tests for the Documentation Agent — no database, no
live LLM call (ADR-0004: a deterministic Protocol implementation is a
legitimate substitute), but a genuine, non-mocked sandbox: every write
in this file happens through a real ``LocalSubprocessSandbox``/real OS
subprocess, so a passing test means a real Markdown file genuinely
exists on disk afterward, not an assertion about a mock's call
arguments.

The opt-in live proof (a real LLM producing real documentation content)
lives under the Kernel's own
``tests/integration/workflow_engine/test_documentation_agent_pack.py``.
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
from ai_os_kernel.llm_gateway.gateway import EchoLLMGateway
from ai_os_kernel.prompt_engine.renderer import InMemoryPromptEngine
from ai_os_kernel.prompted_completion import PromptedCompletionService
from ai_os_kernel.workflow_engine.models import StepType, WorkflowStep
from ai_os_kernel.workflow_engine.registry import InMemoryAgentRegistry
from ai_os_kernel.workflow_engine.step_executor import AgentStepExecutor
from ai_os_pack_software_engineering.agents.documentation import (
    DocumentationAgentEntrypoint,
    DocumentationAgentInput,
    DocumentationAgentOutput,
    DocumentationInstructionError,
    _resolve_existing_file,
    _resolve_safe_relative_path,
)

_AGENT_ID = "documentation"
_PROMPT_ID = "documentation.record_artifact"
_PROMPT_VERSION = "0.1.0"
_TEMPLATE = (
    "# {{filePath}}\n\n"
    "Instruction: {{instruction}}\n"
    "Passed: {{passed}} (exit {{exitCode}})\n"
    "Output: {{output}}"
)


class _FixedPayloadResolver:
    """A fake `ContextSourceResolver` (ADR-0004: a legitimate test
    substitute) that always returns one item carrying a fixed,
    JSON-encoded build+test payload — the real channel
    `DocumentationAgentEntrypoint` reads from when invoked through a
    real `AgentStepExecutor` (see that module's own docstring)."""

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


async def _deterministic_service(template: str) -> PromptedCompletionService:
    return PromptedCompletionService(
        prompt_engine=InMemoryPromptEngine({(_PROMPT_ID, _PROMPT_VERSION): template}),
        llm_gateway=EchoLLMGateway(),
    )


def _step() -> WorkflowStep:
    return WorkflowStep(
        id="record_documentation",
        type=StepType.AGENT,
        agent_id=_AGENT_ID,
        prompt_id=_PROMPT_ID,
        prompt_version=_PROMPT_VERSION,
        model_alias="coding-strong",
    )


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_documentation_agent_entrypoint_constructs_with_zero_arguments() -> None:
    agent = DocumentationAgentEntrypoint()

    assert agent.output_schema["required"] == [
        "workingDirectory",
        "documentationPath",
        "written",
        "exitCode",
        "content",
    ]


@pytest.mark.asyncio
async def test_documentation_agent_genuinely_writes_a_real_doc_file_through_agent_step_executor(
    tmp_path: Path,
) -> None:
    """The real end-to-end proof this step exists for: a WorkflowStep of
    type agent, dispatched through the real AgentStepExecutor with a
    real (fake-resolver-backed) Context Manager, genuinely results in a
    real Markdown documentation file existing in the sandbox working
    directory afterward, with content traceable to the model's own
    completion."""
    _write(tmp_path / "ok.py", "print('all good')\n")
    payload = {
        "workingDirectory": str(tmp_path),
        "filePath": "ok.py",
        "instruction": "Write a script that prints 'all good'.",
        "passed": True,
        "exitCode": 0,
        "output": "all good\n",
    }

    async def factory() -> PromptedCompletionService:
        return await _deterministic_service(_TEMPLATE)

    agent = DocumentationAgentEntrypoint(service_factory=factory)
    context_manager = DefaultContextManager([_FixedPayloadResolver(payload)])
    registry = InMemoryAgentRegistry({_AGENT_ID: agent})
    executor = AgentStepExecutor(registry, context_manager)

    outputs = await executor.execute(_step(), workflow_id="wf_test")

    DocumentationAgentOutput.model_validate(outputs)
    assert outputs["workingDirectory"] == str(tmp_path)
    assert outputs["documentationPath"] == "ok.py.md"
    assert outputs["written"] is True
    assert outputs["exitCode"] == 0
    written_file = tmp_path / "ok.py.md"
    assert written_file.is_file()
    doc_text = written_file.read_text(encoding="utf-8")
    assert doc_text == outputs["content"]
    assert "ok.py" in doc_text
    assert "all good" in doc_text


@pytest.mark.asyncio
async def test_documentation_agent_records_a_genuine_failing_test_outcome(tmp_path: Path) -> None:
    """The identical dispatch chain, describing a genuinely *failed*
    Test Agent outcome — proving this agent records whatever status it
    is given, not only the happy path."""
    _write(tmp_path / "broken.py", "raise SystemExit(1)\n")
    payload = {
        "workingDirectory": str(tmp_path),
        "filePath": "broken.py",
        "instruction": "Write a script that always succeeds.",
        "passed": False,
        "exitCode": 1,
        "output": "Traceback (most recent call last):\nSystemExit: 1\n",
    }

    async def factory() -> PromptedCompletionService:
        return await _deterministic_service(_TEMPLATE)

    agent = DocumentationAgentEntrypoint(service_factory=factory)
    context_manager = DefaultContextManager([_FixedPayloadResolver(payload)])
    registry = InMemoryAgentRegistry({_AGENT_ID: agent})
    executor = AgentStepExecutor(registry, context_manager)

    outputs = await executor.execute(_step(), workflow_id="wf_test")

    assert outputs["written"] is True
    doc_text = (tmp_path / "broken.py.md").read_text(encoding="utf-8")
    assert "Passed: false" in doc_text
    assert "exit 1" in doc_text


@pytest.mark.asyncio
async def test_documentation_agent_via_direct_execute_with_inputs_supplied_directly(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "ok.py", "print('direct call')\n")

    async def factory() -> PromptedCompletionService:
        return await _deterministic_service(_TEMPLATE)

    agent = DocumentationAgentEntrypoint(service_factory=factory)

    outputs = await agent.execute(
        {
            "promptId": _PROMPT_ID,
            "promptVersion": _PROMPT_VERSION,
            "modelAlias": "coding-strong",
            "workingDirectory": str(tmp_path),
            "filePath": "ok.py",
            "instruction": "Write a script that prints 'direct call'.",
            "passed": True,
            "exitCode": 0,
            "output": "direct call\n",
        }
    )

    DocumentationAgentOutput.model_validate(outputs)
    assert outputs["written"] is True
    assert (tmp_path / "ok.py.md").is_file()


@pytest.mark.asyncio
async def test_documentation_agent_rejects_a_missing_file(tmp_path: Path) -> None:
    async def factory() -> PromptedCompletionService:
        return await _deterministic_service(_TEMPLATE)

    agent = DocumentationAgentEntrypoint(service_factory=factory)

    with pytest.raises(DocumentationInstructionError, match="does not exist"):
        await agent.execute(
            {
                "promptId": _PROMPT_ID,
                "promptVersion": _PROMPT_VERSION,
                "modelAlias": "coding-strong",
                "workingDirectory": str(tmp_path),
                "filePath": "does_not_exist.py",
                "instruction": "irrelevant",
                "passed": True,
                "exitCode": 0,
                "output": "",
            }
        )


@pytest.mark.asyncio
async def test_documentation_agent_rejects_a_nonexistent_working_directory(tmp_path: Path) -> None:
    async def factory() -> PromptedCompletionService:
        return await _deterministic_service(_TEMPLATE)

    agent = DocumentationAgentEntrypoint(service_factory=factory)
    missing = tmp_path / "does-not-exist"

    with pytest.raises(DocumentationInstructionError, match="does not exist or is not a"):
        await agent.execute(
            {
                "promptId": _PROMPT_ID,
                "promptVersion": _PROMPT_VERSION,
                "modelAlias": "coding-strong",
                "workingDirectory": str(missing),
                "filePath": "ok.py",
                "instruction": "irrelevant",
                "passed": True,
                "exitCode": 0,
                "output": "",
            }
        )


@pytest.mark.asyncio
async def test_documentation_agent_rejects_missing_required_fields() -> None:
    agent = DocumentationAgentEntrypoint()

    with pytest.raises(DocumentationInstructionError, match="requires"):
        await agent.execute({"filePath": "ok.py"})


@pytest.mark.asyncio
async def test_documentation_agent_via_agent_step_executor_rejects_a_malformed_context_payload(
    tmp_path: Path,
) -> None:
    context_manager = DefaultContextManager([_FixedPayloadResolver({"filePath": "ok.py"})])
    registry = InMemoryAgentRegistry({_AGENT_ID: DocumentationAgentEntrypoint()})
    executor = AgentStepExecutor(registry, context_manager)

    with pytest.raises(DocumentationInstructionError, match="missing"):
        await executor.execute(_step(), workflow_id="wf_test")


def test_resolve_existing_file_rejects_a_blank_path(tmp_path: Path) -> None:
    with pytest.raises(DocumentationInstructionError, match="must not be blank"):
        _resolve_existing_file(tmp_path, "   ")


@pytest.mark.parametrize("malicious_path", ["../../outside.txt.md", "/etc/passwd.md"])
def test_resolve_safe_relative_path_rejects_paths_that_escape_the_working_directory(
    tmp_path: Path, malicious_path: str
) -> None:
    with pytest.raises(DocumentationInstructionError, match="resolves outside"):
        _resolve_safe_relative_path(tmp_path, malicious_path)


def test_documentation_agent_input_documents_the_agent_contract() -> None:
    DocumentationAgentInput.model_validate(
        {
            "workingDirectory": "workspace",
            "filePath": "a.py",
            "instruction": "Write a hello-world script.",
            "passed": True,
            "exitCode": 0,
            "output": "hello\n",
        }
    )
