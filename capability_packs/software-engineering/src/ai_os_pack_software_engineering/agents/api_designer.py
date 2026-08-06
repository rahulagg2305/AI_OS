"""The API Designer Agent — `docs/06_capability_packs/software_engineering/
agents.md`'s "Agent Categories" API Design entry, FR-037 ("Define
versioned API contracts... Contract artifact produced and validated").
This pack's ninth agent, and the second genuinely new agent (not a
migration) since the module-27 Platform SDK hard gate lifted, following
`database.py`'s own precedent of building directly against
`ai_os_sdk.contracts` from the start.

**A genuine design fork was found and resolved before writing this
module (product-owner decision, 2026-08-06): how "validated" gets
proven for real.** Three real options existed — (1) a real,
standards-grade validator (`openapi-spec-validator`, a new but small,
real, actively-maintained dependency) genuinely checks the LLM-produced
document against the real OpenAPI 3.1 specification; (2) a hand-rolled
structural check (well-formed YAML plus a few required top-level keys),
avoiding a new dependency but materially weaker — a document could pass
and still be genuinely invalid OpenAPI; (3) sidestep OpenAPI entirely
with a narrower, custom "contract" shape validated the same way every
other agent's own output already is (`model_validate`), avoiding both a
new dependency and real OpenAPI semantics. **(1) was chosen**: this
project already has an established, real meaning for "API contract
artifact" in this exact codebase — the Kernel's own committed
`docs/07_api/openapi.json` (`P06-S01-M36-T01`) — and FR-037's "validated"
is a real acceptance criterion, not a soft suggestion; reusing a
mature, correct library beats re-implementing a subset of the OpenAPI
3.1 spec by hand. `openapi-spec-validator`/`pyyaml` are now real,
declared dependencies of this pack (`pyproject.toml`) — `pyyaml` was
already a real, transitive dependency via `ai-os-sdk`, declared
directly here too since this module imports it directly.

**Reuses `build.py`'s/`database.py`'s own real write mechanism
verbatim** — the identical `FILE_PATH`/`FILE_CONTENT_BEGIN`/
`FILE_CONTENT_END` delimited format, the identical safe-relative-path
containment check, and the identical write-through-sandbox script. The
one real addition: the parsed `FILE_CONTENT` is loaded as YAML and
validated as a real OpenAPI 3.1 document via `openapi_spec_validator`
before any sandbox call — FR-037's "is validated" criterion enforced as
a real precondition, not merely documented, the identical "raise
clearly, before any sandbox call" discipline `build.py`'s/`database.py`'s
own instruction errors already establish. A completion that is not
well-formed YAML, or is well-formed YAML but not a valid OpenAPI 3.1
document, is refused before it is ever written.

**No `evaluation.llm_calls` capability loss to disclose here** — SDK-
native from its first line, the identical "no migration debt" note
`database.py`'s own docstring already makes.
"""

from __future__ import annotations

import asyncio
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any

import yaml
from openapi_spec_validator import validate as validate_openapi
from openapi_spec_validator.validation.exceptions import OpenAPIValidationError
from pydantic import BaseModel, Field

from ai_os_sdk.contracts.tool_invoker import (
    PLATFORM_PYTHON_INTERPRETER,
    PLATFORM_SANDBOX_RUN_COMMAND,
)
from ai_os_sdk.models import LLMRequest, Message, MessageRole, TraceContext

# Named, documented first-cut values — the same "placeholder safety
# limit, not yet tuned" carve-out `build.py`/`database.py` already use.
_MAX_OUTPUT_TOKENS = 4096
_WRITE_TIMEOUT_SECONDS = 10.0
_WRITE_MAX_OUTPUT_BYTES = 65536

_WORKSPACE_PREFIX = "aios-api-designer-agent-"

_REQUIRED_INVOCATION_FIELDS = ("promptId", "promptVersion", "modelAlias")

# Identical shape to build.py's/database.py's own write-file script —
# portable (pathlib/sys.stdin only, no shell).
_WRITE_FILE_SCRIPT = (
    "import pathlib, sys\n"
    "target = pathlib.Path(sys.argv[1])\n"
    "target.parent.mkdir(parents=True, exist_ok=True)\n"
    "target.write_bytes(sys.stdin.buffer.read())\n"
)

# Identical to build.py's/database.py's own _INSTRUCTION_PATTERN — see
# either module's docstring for why this is a fixed delimited format,
# not JSON. DOTALL so `.` matches newlines inside the captured content.
_INSTRUCTION_PATTERN = re.compile(
    r"FILE_PATH:[ \t]*(?P<path>.+?)[ \t]*\r?\n"
    r"FILE_CONTENT_BEGIN\r?\n"
    r"(?P<content>.*?)"
    r"\r?\nFILE_CONTENT_END",
    re.DOTALL,
)


class ApiContractInstructionError(Exception):
    """Either this entrypoint's own invocation contract was violated
    (called before :meth:`bind_pack_context`, or missing a required
    ``promptId``/``promptVersion``/``modelAlias`` field), or the model's
    completion could not be turned into a safe, valid contract write —
    it did not follow the documented ``FILE_PATH``/``FILE_CONTENT_BEGIN``/
    ``FILE_CONTENT_END`` format, its content was not well-formed YAML,
    it was not a valid OpenAPI 3.1 document, or its declared path does
    not resolve inside the sandbox working directory. Raised clearly,
    before any sandbox call is attempted."""


class ApiContractInput(BaseModel):
    """Documents this agent's Agent Contract "Required Inputs"
    (capability_pack_contract.md). **Not yet validated at runtime** —
    see :mod:`ai_os_pack_software_engineering.agents.architecture`'s
    own ``ArchitectureProposalInput`` for why (the identical, still
    unchanged, "no per-step input-mapping mechanism exists" scope).
    ``design`` reaches this agent today via the Context Manager's own
    assembled ``context`` prompt variable, the one real channel this
    codebase's ``AgentStepExecutor`` establishes."""

    design: str = Field(
        ..., description="A design proposal or direct instruction describing one API to define."
    )


class ApiDesignerAgentOutput(BaseModel):
    """Documents this agent's Agent Contract "Produced Outputs." Mirrors
    the real fields :meth:`ApiDesignerAgentEntrypoint.execute` returns.
    ``openapi_version``/``paths`` are derived from the real, validated
    document — not re-derived by a future caller re-parsing the file."""

    working_directory: str = Field(..., alias="workingDirectory")
    file_path: str = Field(..., alias="filePath")
    written: bool
    exit_code: int | None = Field(..., alias="exitCode")
    stdout: str
    stderr: str
    instruction: str
    openapi_version: str = Field(..., alias="openapiVersion")
    paths: list[str]

    model_config = {"populate_by_name": True}


_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "workingDirectory": {"type": "string"},
        "filePath": {"type": "string"},
        "written": {"type": "boolean"},
        "exitCode": {"type": ["integer", "null"]},
        "stdout": {"type": "string"},
        "stderr": {"type": "string"},
        "instruction": {"type": "string"},
        "openapiVersion": {"type": "string"},
        "paths": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "workingDirectory",
        "filePath",
        "written",
        "exitCode",
        "stdout",
        "stderr",
        "instruction",
        "openapiVersion",
        "paths",
    ],
    "additionalProperties": False,
}


def _resolve_safe_relative_path(working_directory: Path, raw_path: str) -> Path:
    """Identical to build.py's/database.py's own helper of the same
    name — resolves ``raw_path`` (the model's own declared ``FILE_PATH``)
    against ``working_directory`` and returns a verified-safe relative
    path, or raises :class:`ApiContractInstructionError`."""
    stripped = raw_path.strip()
    if not stripped:
        raise ApiContractInstructionError("the model's FILE_PATH must not be blank")

    resolved_root = working_directory.resolve()
    resolved_target = (working_directory / stripped).resolve()
    if not resolved_target.is_relative_to(resolved_root):
        raise ApiContractInstructionError(
            f"FILE_PATH {raw_path!r} resolves outside the sandbox working directory"
        )
    return resolved_target.relative_to(resolved_root)


def _parse_contract_instruction(completion_text: str) -> tuple[str, str]:
    """Extracts ``(raw_path, content)`` from a completion following this
    module's own documented format — identical to build.py's/database.py's
    own parse helper."""
    match = _INSTRUCTION_PATTERN.search(completion_text)
    if match is None:
        raise ApiContractInstructionError(
            "the model's completion did not follow the documented FILE_PATH/"
            f"FILE_CONTENT_BEGIN/FILE_CONTENT_END format:\n{completion_text}"
        )
    return match.group("path"), match.group("content")


def _parse_and_validate_openapi_document(content: str) -> dict[str, Any]:
    """Loads ``content`` as YAML and validates it as a real OpenAPI 3.1
    document via :func:`openapi_spec_validator.validate`. Raises
    :class:`ApiContractInstructionError` for either failure — FR-037's
    "is validated" criterion enforced as a real precondition, before any
    sandbox write."""
    try:
        document = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise ApiContractInstructionError(
            f"the model's file content was not well-formed YAML: {exc}"
        ) from exc

    if not isinstance(document, dict):
        raise ApiContractInstructionError(
            "the model's file content did not parse to a YAML mapping — an OpenAPI "
            f"document must be a mapping, got {type(document).__name__}"
        )

    try:
        validate_openapi(document)
    except OpenAPIValidationError as exc:
        raise ApiContractInstructionError(
            f"the model's file content is not a valid OpenAPI 3.1 document: {exc}"
        ) from exc

    return document


def _build_variables(inputs: dict[str, Any]) -> dict[str, Any]:
    """Identical to build.py's/database.py's own helper of the same
    name — mirrors :meth:`~ai_os_kernel.workflow_engine.prompted_agent.
    PromptedAgent._build_variables` exactly, duck-typed rather than
    ``isinstance``-checked against ``AssembledContext``."""
    variables = dict(inputs.get("variables") or {})
    context = inputs.get("context")
    items = getattr(context, "items", None)
    if items and "context" not in variables:
        variables["context"] = "\n\n".join(item.content for item in items)
    return variables


class ApiDesignerAgentEntrypoint:
    """The manifest's own ``agents[].entrypoint`` for the API Designer
    Agent — zero-argument-constructible
    (:class:`~ai_os_kernel.workflow_engine.entrypoint_loader.EntrypointLoader`,
    :class:`~ai_os_kernel.workflow_engine.registry.SqlAgentRegistry`).
    Keeps the identical narrow lock ``build.py``/``database.py`` keep,
    guarding only lazy working-directory creation, not any LLM
    composition — the identical reasoning, not re-litigated here.

    ``working_directory`` is an optional constructor override — always
    its default (``None``) in production, and how a test substitutes a
    known temporary directory, the identical shape ``build.py``/
    ``database.py`` establish."""

    output_schema: dict[str, Any] = _OUTPUT_SCHEMA

    def __init__(self, *, working_directory: Path | None = None) -> None:
        self._context: Any | None = None
        self._working_directory = working_directory
        self._directory_lock = asyncio.Lock()

    def bind_pack_context(self, context: Any) -> None:
        self._context = context

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        if (
            self._context is None
            or self._context.llm is None
            or self._context.prompts is None
            or self._context.tools is None
        ):
            raise ApiContractInstructionError(
                "ApiDesignerAgentEntrypoint.execute() called before bind_pack_context() bound "
                "a PackContext granting the llm:invoke and sandbox:execute permissions "
                "(context.llm/context.prompts/context.tools) — a real caller must inject "
                "one before first use"
            )

        prompt_id = inputs.get("promptId")
        prompt_version = inputs.get("promptVersion")
        model_alias = inputs.get("modelAlias")
        missing = [
            name
            for name, value in zip(
                _REQUIRED_INVOCATION_FIELDS,
                (prompt_id, prompt_version, model_alias),
                strict=True,
            )
            if not isinstance(value, str) or not value
        ]
        if missing:
            raise ApiContractInstructionError(
                "ApiDesignerAgentEntrypoint requires 'promptId', 'promptVersion', and "
                f"'modelAlias' in its inputs — missing: {', '.join(missing)}"
            )

        working_directory = await self._ensure_working_directory()

        rendered = await self._context.prompts.render(
            prompt_id, _build_variables(inputs), version=prompt_version
        )

        workflow_id = inputs.get("workflowId")
        step_id = inputs.get("stepId")
        agent_id = inputs.get("agentId")
        metadata = (
            TraceContext(
                trace_id=uuid.uuid4().hex,
                span_id=uuid.uuid4().hex,
                workflow_id=workflow_id,
                step_id=step_id,
                agent_id=agent_id,
                prompt_id=prompt_id,
                prompt_version=prompt_version,
            )
            if workflow_id is not None or step_id is not None
            else None
        )

        response = await self._context.llm.complete(
            LLMRequest(
                model_alias=model_alias,
                messages=[Message(role=MessageRole.USER, content=rendered.content)],
                max_output_tokens=_MAX_OUTPUT_TOKENS,
                metadata=metadata,
            )
        )
        instruction_text = response.content
        raw_path, content = _parse_contract_instruction(instruction_text)
        document = await asyncio.to_thread(_parse_and_validate_openapi_document, content)
        relative_path = await asyncio.to_thread(
            _resolve_safe_relative_path, working_directory, raw_path
        )

        result = await self._context.tools.invoke(
            PLATFORM_SANDBOX_RUN_COMMAND,
            {
                "command": [
                    PLATFORM_PYTHON_INTERPRETER,
                    "-c",
                    _WRITE_FILE_SCRIPT,
                    str(relative_path),
                ],
                "working_directory": str(working_directory),
                "timeout_seconds": _WRITE_TIMEOUT_SECONDS,
                "max_output_bytes": _WRITE_MAX_OUTPUT_BYTES,
                "stdin": content,
            },
        )

        return {
            "workingDirectory": str(working_directory),
            "filePath": str(relative_path),
            "written": result.exit_code == 0 and not result.timed_out,
            "exitCode": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "instruction": instruction_text,
            "openapiVersion": str(document.get("openapi", "")),
            "paths": sorted(document.get("paths", {}).keys()),
        }

    async def _ensure_working_directory(self) -> Path:
        async with self._directory_lock:
            if self._working_directory is None:
                self._working_directory = await asyncio.to_thread(
                    lambda: Path(tempfile.mkdtemp(prefix=_WORKSPACE_PREFIX))
                )
        return self._working_directory
