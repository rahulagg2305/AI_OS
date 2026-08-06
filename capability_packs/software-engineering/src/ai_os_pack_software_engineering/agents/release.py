"""The Release Agent — `docs/06_capability_packs/software_engineering/
agents.md`'s "Agent Categories" Release entry, FR-042 ("Manage version,
changelog, and release readiness... Release gate evaluates and records
readiness"). This pack's eleventh agent, and the fourth genuinely new
agent (not a migration) since the module-27 Platform SDK hard gate
lifted.

**Deliberately near-identical to `documentation.py`'s own
`DocumentationAgentEntrypoint` — not accidental duplication, the same
"no shared module needed for a single real caller each" reasoning that
module's own docstring already applies.** Same real dependencies
(Build Agent + QA-Test Agent's own outputs, per this ticket's own
`depends_on`), same six-field input shape
(`workingDirectory`/`filePath`/`instruction`/`passed`/`exitCode`/
`output`), same LLM-call-then-write-through-sandbox mechanism, same
"no completion-text parsing, the model's entire completion is the
file content" simplicity, same derived target path
(`"<filePath>.changelog.md"`, written alongside the source file).

**The one real addition, and the only part FR-042's own acceptance
criterion ("Release gate evaluates and records readiness") actually
requires: `ready`, a mechanically-derived field, never an LLM's
opinion.** `ready = passed` — the QA/Test Agent's own real outcome,
reused directly, the identical "a gate's pass/fail must derive only
from a real, already-known input, never an LLM's judgment" principle
`lint.py`/`verification.py`/`security_analysis.py` already establish
for their own gates. A build whose own tests did not pass is not
release-ready, by definition, not by inference — no new decision logic
exists here to get wrong.

**Version and changelog content are LLM-generated free text, never
independently validated or parsed** — the identical, disclosed
boundary `documentation.py`'s own docstring already draws ("the
model's entire completion is used verbatim"). This agent does not
compute or verify a semver bump; the model proposes one as part of its
own generated changelog entry, exactly as `release_record_changelog.md`
instructs. Attempting to compute a "correct" version bump mechanically
would need a real diff of the actual code change, which this agent's
own input (a `passed`/`exitCode`/`output` triple, no diff) does not
carry — inventing that analysis is out of this ticket's own narrow
scope, the identical "smallest real slice" discipline this whole pack
has followed.

**No `evaluation.llm_calls` capability loss to disclose here** — SDK-
native from its first line, the identical "no migration debt" note
`database.py`'s/`api_designer.py`'s/`security_analysis.py`'s own
docstrings already make.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any, NamedTuple

from pydantic import BaseModel, Field

from ai_os_sdk.contracts.tool_invoker import (
    PLATFORM_PYTHON_INTERPRETER,
    PLATFORM_SANDBOX_RUN_COMMAND,
)
from ai_os_sdk.models import LLMRequest, Message, MessageRole, TraceContext

# Named, documented first-cut values — the identical "placeholder
# safety limit, not yet tuned" carve-out `documentation.py` already
# uses. A concise changelog entry for one file is not expected to
# exceed these.
_MAX_OUTPUT_TOKENS = 2048
_WRITE_TIMEOUT_SECONDS = 10.0
_WRITE_MAX_OUTPUT_BYTES = 65536

_REQUIRED_INVOCATION_FIELDS = ("promptId", "promptVersion", "modelAlias")

# Identical to documentation.py's own script — duplicated, not
# imported, per this module's own docstring. Portable
# (pathlib/sys.stdin only, no shell).
_WRITE_FILE_SCRIPT = (
    "import pathlib, sys\n"
    "target = pathlib.Path(sys.argv[1])\n"
    "target.parent.mkdir(parents=True, exist_ok=True)\n"
    "target.write_bytes(sys.stdin.buffer.read())\n"
)

_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "workingDirectory": {"type": "string"},
        "changelogPath": {"type": "string"},
        "written": {"type": "boolean"},
        "exitCode": {"type": ["integer", "null"]},
        "content": {"type": "string"},
        "ready": {"type": "boolean"},
    },
    "required": [
        "workingDirectory",
        "changelogPath",
        "written",
        "exitCode",
        "content",
        "ready",
    ],
    "additionalProperties": False,
}


class ReleaseInstructionError(Exception):
    """Either this entrypoint's own invocation contract was violated
    (called before :meth:`bind_pack_context`, or missing a required
    ``promptId``/``promptVersion``/``modelAlias`` field), or this
    agent's input could not be turned into a safe changelog write — a
    required field was missing or malformed, or ``filePath`` does not
    resolve to a real, existing file inside ``workingDirectory``.
    Raised clearly, before any LLM or sandbox call is attempted."""


class ReleaseAgentInput(BaseModel):
    """Documents this agent's Agent Contract "Required Inputs"
    (capability_pack_contract.md). Identical field shape to
    ``documentation.py``'s own ``DocumentationAgentInput`` — this agent
    is meant to consume the same Build Agent + QA/Test Agent results
    directly."""

    working_directory: str = Field(..., alias="workingDirectory")
    file_path: str = Field(..., alias="filePath")
    instruction: str = Field(
        ..., description="The original design/instruction the Build Agent implemented."
    )
    passed: bool = Field(..., description="The Test Agent's own pass/fail outcome for filePath.")
    exit_code: int | None = Field(..., alias="exitCode")
    output: str = Field(..., description="The Test Agent's own captured stdout+stderr.")

    model_config = {"populate_by_name": True}


class ReleaseAgentOutput(BaseModel):
    """Documents this agent's Agent Contract "Produced Outputs." Mirrors
    the real fields :meth:`ReleaseAgentEntrypoint.execute` returns —
    ``ready`` is derived only from the caller-supplied ``passed``,
    never from any judgment about ``content``'s own text."""

    working_directory: str = Field(..., alias="workingDirectory")
    changelog_path: str = Field(..., alias="changelogPath")
    written: bool
    exit_code: int | None = Field(..., alias="exitCode")
    content: str
    ready: bool

    model_config = {"populate_by_name": True}


class _BuildTestPayload(NamedTuple):
    working_directory: str
    file_path: str
    instruction: str
    passed: bool
    exit_code: int | None
    output: str


_REQUIRED_FIELDS = ("workingDirectory", "filePath", "instruction", "passed", "exitCode", "output")


def _extract_payload(inputs: dict[str, Any]) -> _BuildTestPayload:
    """Identical to documentation.py's own ``_extract_payload`` —
    duplicated, not imported, per this module's own docstring."""
    if all(field in inputs for field in _REQUIRED_FIELDS):
        payload = {field: inputs[field] for field in _REQUIRED_FIELDS}
    else:
        context = inputs.get("context")
        items = getattr(context, "items", None)
        if not items:
            raise ReleaseInstructionError(
                "ReleaseAgentEntrypoint requires 'workingDirectory', 'filePath', "
                "'instruction', 'passed', 'exitCode', and 'output' — either directly in "
                "inputs, or as a JSON object in the assembled context"
            )
        raw = "\n\n".join(item.content for item in items)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ReleaseInstructionError(
                f"the assembled context is not a valid JSON object: {exc}"
            ) from exc
        if not isinstance(payload, dict) or not all(field in payload for field in _REQUIRED_FIELDS):
            raise ReleaseInstructionError(
                "the assembled context's JSON object is missing one of 'workingDirectory', "
                "'filePath', 'instruction', 'passed', 'exitCode', or 'output'"
            )

    working_directory = payload["workingDirectory"]
    file_path = payload["filePath"]
    instruction = payload["instruction"]
    passed = payload["passed"]
    exit_code = payload["exitCode"]
    output = payload["output"]

    if not isinstance(working_directory, str) or not isinstance(file_path, str):
        raise ReleaseInstructionError("workingDirectory and filePath must both be strings")
    if not isinstance(instruction, str) or not isinstance(output, str):
        raise ReleaseInstructionError("instruction and output must both be strings")
    if not isinstance(passed, bool):
        raise ReleaseInstructionError("passed must be a boolean")
    if exit_code is not None and not isinstance(exit_code, int):
        raise ReleaseInstructionError("exitCode must be an integer or null")

    return _BuildTestPayload(working_directory, file_path, instruction, passed, exit_code, output)


def _resolve_existing_file(working_directory: Path, raw_path: str) -> Path:
    """Identical to documentation.py's/verification.py's own helper of
    the same name — duplicated, not imported."""
    stripped = raw_path.strip()
    if not stripped:
        raise ReleaseInstructionError("filePath must not be blank")

    resolved_root = working_directory.resolve()
    resolved_target = (working_directory / stripped).resolve()
    if not resolved_target.is_relative_to(resolved_root):
        raise ReleaseInstructionError(f"filePath {raw_path!r} resolves outside {working_directory}")
    if not resolved_target.is_file():
        raise ReleaseInstructionError(
            f"filePath {raw_path!r} does not exist inside {working_directory}"
        )
    return resolved_target


def _resolve_safe_relative_path(working_directory: Path, raw_path: str) -> Path:
    """Identical to documentation.py's/build.py's own helper of the
    same name — duplicated, not imported. Does not require the target
    to already exist: this path is about to be created."""
    stripped = raw_path.strip()
    if not stripped:
        raise ReleaseInstructionError("the changelog path must not be blank")

    resolved_root = working_directory.resolve()
    resolved_target = (working_directory / stripped).resolve()
    if not resolved_target.is_relative_to(resolved_root):
        raise ReleaseInstructionError(
            f"changelog path {raw_path!r} resolves outside the sandbox working directory"
        )
    return resolved_target.relative_to(resolved_root)


class ReleaseAgentEntrypoint:
    """The manifest's own ``agents[].entrypoint`` for the Release
    Agent — zero-argument-constructible. Needs no lock at all, the
    identical reasoning ``documentation.py``'s own docstring already
    establishes: nothing is built lazily, nothing is created before
    the one real write this agent performs."""

    output_schema: dict[str, Any] = _OUTPUT_SCHEMA

    def __init__(self) -> None:
        self._context: Any | None = None

    def bind_pack_context(self, context: Any) -> None:
        self._context = context

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        if (
            self._context is None
            or self._context.llm is None
            or self._context.prompts is None
            or self._context.tools is None
        ):
            raise ReleaseInstructionError(
                "ReleaseAgentEntrypoint.execute() called before bind_pack_context() bound a "
                "PackContext granting both the llm:invoke and sandbox:execute permissions "
                "(context.llm/context.prompts/context.tools) — a real caller must inject "
                "one before first use"
            )

        payload = _extract_payload(inputs)

        working_directory = Path(payload.working_directory)
        if not await asyncio.to_thread(working_directory.is_dir):
            raise ReleaseInstructionError(
                f"workingDirectory {payload.working_directory!r} does not exist or is not a "
                "directory"
            )
        await asyncio.to_thread(_resolve_existing_file, working_directory, payload.file_path)
        changelog_relative_path = await asyncio.to_thread(
            _resolve_safe_relative_path, working_directory, f"{payload.file_path}.changelog.md"
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
            raise ReleaseInstructionError(
                "ReleaseAgentEntrypoint requires 'promptId', 'promptVersion', and "
                f"'modelAlias' in its inputs — missing: {', '.join(missing)}"
            )

        variables = {
            "filePath": payload.file_path,
            "instruction": payload.instruction,
            "passed": "true" if payload.passed else "false",
            "exitCode": "none" if payload.exit_code is None else str(payload.exit_code),
            "output": payload.output,
        }
        rendered = await self._context.prompts.render(prompt_id, variables, version=prompt_version)

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
        content = response.content

        result = await self._context.tools.invoke(
            PLATFORM_SANDBOX_RUN_COMMAND,
            {
                "command": [
                    PLATFORM_PYTHON_INTERPRETER,
                    "-c",
                    _WRITE_FILE_SCRIPT,
                    str(changelog_relative_path),
                ],
                "working_directory": str(working_directory),
                "timeout_seconds": _WRITE_TIMEOUT_SECONDS,
                "max_output_bytes": _WRITE_MAX_OUTPUT_BYTES,
                "stdin": content,
            },
        )

        return {
            "workingDirectory": str(working_directory),
            "changelogPath": str(changelog_relative_path),
            "written": result.exit_code == 0 and not result.timed_out,
            "exitCode": result.exit_code,
            "content": content,
            "ready": payload.passed,
        }
