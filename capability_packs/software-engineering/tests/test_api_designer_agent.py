"""Deterministic tests for the API Designer Agent — no live LLM call
(ADR-0004: a deterministic Protocol implementation is a legitimate
substitute), but a genuine, non-mocked sandbox: every write in this
file happens through a real ``LocalSubprocessSandbox``/real OS
subprocess, so a passing test means a real file genuinely exists on
disk afterward.

Mirrors ``test_database_agent.py``'s own real substitute exactly:
construct the agent with zero arguments (aside from
``working_directory``), then bind it a real ``PackContext`` via
``build_pack_context``/``bind_pack_context``.

The real, FR-037-specific proof this file adds: validation is
performed by the real, genuine ``openapi_spec_validator`` library, not
a hand-rolled structural check — proven by feeding it a document that
is well-formed YAML but genuinely violates the OpenAPI 3.1
specification (missing ``info.version``) and confirming the *real*
library's own error propagates, not a synthetic stand-in. See
``docs/19_roadmap/tickets/P08/P08-S01-M29-T03.md`` for the design-fork
record (a real spec validator, chosen over a hand-rolled structural
check or a non-OpenAPI contract shape).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from ai_os_kernel.llm_gateway.gateway import EchoLLMGateway
from ai_os_kernel.prompt_engine.renderer import InMemoryPromptEngine
from ai_os_kernel.sandbox.executor import LocalSubprocessSandbox
from ai_os_kernel.sdk_adapters.pack_context import build_pack_context
from ai_os_kernel.workflow_engine.models import StepType, WorkflowStep
from ai_os_kernel.workflow_engine.registry import InMemoryAgentRegistry
from ai_os_kernel.workflow_engine.step_executor import AgentStepExecutor
from ai_os_pack_software_engineering.agents.api_designer import (
    ApiContractInput,
    ApiContractInstructionError,
    ApiDesignerAgentEntrypoint,
    ApiDesignerAgentOutput,
    _parse_and_validate_openapi_document,
    _parse_contract_instruction,
    _resolve_safe_relative_path,
)
from ai_os_sdk.contracts import Agent as SdkAgent
from ai_os_sdk.contracts import PackContextReceiver

_AGENT_ID = "api-designer"
_PACK_ID = "software-engineering"
_PACK_VERSION = "0.1.0"
_PROMPT_ID = "apidesigner.write_contract"
_PROMPT_VERSION = "0.1.0"


def _agent_with_prompt(
    template: str, *, working_directory: Path | None = None
) -> ApiDesignerAgentEntrypoint:
    """The real, zero-arg-constructed (aside from ``working_directory``)
    entrypoint, bound to a real ``PackContext`` — identical construction
    sequence to ``test_database_agent.py``'s own ``_agent_with_prompt``."""
    agent = ApiDesignerAgentEntrypoint(working_directory=working_directory)
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
        id="write_contract",
        type=StepType.AGENT,
        agent_id=_AGENT_ID,
        prompt_id=_PROMPT_ID,
        prompt_version=_PROMPT_VERSION,
        model_alias="coding-strong",
    )


_VALID_CONTRACT = (
    "openapi: 3.1.0\n"
    "info:\n"
    "  title: Widgets API\n"
    "  version: 1.0.0\n"
    "paths:\n"
    "  /widgets:\n"
    "    get:\n"
    "      responses:\n"
    "        '200':\n"
    "          description: OK\n"
)

_CONTRACT_TEMPLATE = (
    f"FILE_PATH: contracts/widgets.yaml\nFILE_CONTENT_BEGIN\n{_VALID_CONTRACT}FILE_CONTENT_END"
)


def test_api_designer_agent_entrypoint_constructs_with_zero_arguments() -> None:
    """The exact call EntrypointLoader/SqlAgentRegistry make in
    production — must succeed instantly, with no I/O."""
    agent = ApiDesignerAgentEntrypoint()

    assert agent.output_schema["required"] == [
        "workingDirectory",
        "filePath",
        "written",
        "exitCode",
        "stdout",
        "stderr",
        "instruction",
        "openapiVersion",
        "paths",
    ]


def test_the_entrypoint_satisfies_both_sdk_protocols() -> None:
    agent = ApiDesignerAgentEntrypoint()

    assert isinstance(agent, SdkAgent)
    assert isinstance(agent, PackContextReceiver)


@pytest.mark.asyncio
async def test_execute_before_bind_pack_context_raises_a_clear_error() -> None:
    agent = ApiDesignerAgentEntrypoint()

    with pytest.raises(ApiContractInstructionError, match="bind_pack_context"):
        await agent.execute(
            {
                "promptId": _PROMPT_ID,
                "promptVersion": _PROMPT_VERSION,
                "modelAlias": "coding-strong",
            }
        )


@pytest.mark.asyncio
async def test_api_designer_agent_genuinely_writes_a_real_valid_contract_through_the_sandbox(
    tmp_path: Path,
) -> None:
    """A WorkflowStep of type agent, dispatched through the real
    AgentStepExecutor, genuinely results in a real, valid OpenAPI
    contract file existing in the sandbox working directory, with its
    real openapiVersion/paths derived from the validated document."""
    agent = _agent_with_prompt(_CONTRACT_TEMPLATE, working_directory=tmp_path)
    registry = InMemoryAgentRegistry({_AGENT_ID: agent})
    executor = AgentStepExecutor(registry)

    outputs = await executor.execute(_step())

    ApiDesignerAgentOutput.model_validate(outputs)
    assert outputs["written"] is True
    assert outputs["exitCode"] == 0
    written_file = tmp_path / "contracts" / "widgets.yaml"
    assert written_file.is_file()
    assert outputs["openapiVersion"] == "3.1.0"
    assert outputs["paths"] == ["/widgets"]


@pytest.mark.asyncio
async def test_api_designer_agent_rejects_a_document_that_violates_the_real_openapi_spec(
    tmp_path: Path,
) -> None:
    """FR-037's own "is validated" criterion enforced as a real
    precondition: well-formed YAML that is genuinely invalid OpenAPI
    (missing the required info.version) is refused by the real
    openapi_spec_validator library before any sandbox call, not
    silently written."""
    invalid_contract = "openapi: 3.1.0\ninfo:\n  title: Widgets API\npaths: {}\n"
    template = f"FILE_PATH: bad.yaml\nFILE_CONTENT_BEGIN\n{invalid_contract}FILE_CONTENT_END"
    agent = _agent_with_prompt(template, working_directory=tmp_path)
    registry = InMemoryAgentRegistry({_AGENT_ID: agent})
    executor = AgentStepExecutor(registry)

    with pytest.raises(ApiContractInstructionError, match="not a valid OpenAPI 3.1 document"):
        await executor.execute(_step())

    assert await asyncio.to_thread(lambda: list(tmp_path.rglob("*"))) == []


@pytest.mark.asyncio
async def test_api_designer_agent_rejects_content_that_is_not_well_formed_yaml(
    tmp_path: Path,
) -> None:
    template = "FILE_PATH: bad.yaml\nFILE_CONTENT_BEGIN\nkey: [unclosed\nFILE_CONTENT_END"
    agent = _agent_with_prompt(template, working_directory=tmp_path)
    registry = InMemoryAgentRegistry({_AGENT_ID: agent})
    executor = AgentStepExecutor(registry)

    with pytest.raises(ApiContractInstructionError, match="not well-formed YAML"):
        await executor.execute(_step())


@pytest.mark.asyncio
async def test_api_designer_agent_rejects_a_malformed_completion(tmp_path: Path) -> None:
    agent = _agent_with_prompt(
        "this completion follows no documented format at all", working_directory=tmp_path
    )
    registry = InMemoryAgentRegistry({_AGENT_ID: agent})
    executor = AgentStepExecutor(registry)

    with pytest.raises(ApiContractInstructionError, match="did not follow the documented"):
        await executor.execute(_step())


@pytest.mark.asyncio
async def test_missing_required_invocation_fields_raise_a_clear_error() -> None:
    agent = _agent_with_prompt("unused")

    with pytest.raises(ApiContractInstructionError, match="promptId"):
        await agent.execute({"modelAlias": "coding-strong"})


def test_parse_contract_instruction_extracts_path_and_content() -> None:
    completion = f"FILE_PATH: a/b.yaml\nFILE_CONTENT_BEGIN\n{_VALID_CONTRACT}FILE_CONTENT_END"

    path, content = _parse_contract_instruction(completion)

    assert path == "a/b.yaml"
    assert "openapi: 3.1.0" in content


def test_parse_and_validate_openapi_document_accepts_a_real_valid_document() -> None:
    document = _parse_and_validate_openapi_document(_VALID_CONTRACT)

    assert document["openapi"] == "3.1.0"
    assert "/widgets" in document["paths"]


def test_parse_and_validate_openapi_document_rejects_a_real_spec_violation() -> None:
    with pytest.raises(ApiContractInstructionError, match="not a valid OpenAPI 3.1 document"):
        _parse_and_validate_openapi_document("openapi: 3.1.0\ninfo:\n  title: X\npaths: {}\n")


def test_parse_and_validate_openapi_document_rejects_a_non_mapping_document() -> None:
    with pytest.raises(ApiContractInstructionError, match="did not parse to a YAML mapping"):
        _parse_and_validate_openapi_document("- just\n- a\n- list\n")


@pytest.mark.parametrize("malicious_path", ["../../outside.yaml", "/etc/passwd"])
def test_resolve_safe_relative_path_rejects_paths_that_escape_the_working_directory(
    tmp_path: Path, malicious_path: str
) -> None:
    with pytest.raises(ApiContractInstructionError, match="resolves outside"):
        _resolve_safe_relative_path(tmp_path, malicious_path)


def test_api_contract_input_documents_the_agent_contract() -> None:
    ApiContractInput(design="Define a GET /widgets endpoint.")
