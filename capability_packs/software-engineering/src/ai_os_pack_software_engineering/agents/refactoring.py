"""The Refactoring Agent — `docs/06_capability_packs/software_engineering/
agents.md`'s "Agent Categories" Refactoring entry, FR-043 ("Refactor
existing code without changing observable behaviour... Tests pass
before and after; behaviour assertions unchanged").

**FR-043's own criterion is a real before/after comparison — no other
component in this codebase performs one for a single file, so this
agent's own real value is running it, not merely writing code.**
Every sibling `build.py`-based agent writes once and returns; a
Quality Gate reads one already-recorded outcome. Neither can express
"did *this specific* refactor preserve *this specific* file's own
passing behaviour" without this agent explicitly running the caller's
own test command twice — once against the real, already-existing
content (the baseline), once against the model's own refactored
content — and reporting both, mechanically compared, never an LLM's
opinion about its own change.

**"Behaviour assertions unchanged" is structurally guaranteed, not
separately verified — this agent never writes to any file except
``filePath`` itself.** It has no mechanism to touch a test file at
all, so "the tests themselves are unchanged" holds by construction.

**A real precondition, enforced before any LLM call or write:** if the
*baseline* run (against the file's own already-existing content) does
not pass, there is no valid, passing behaviour to preserve — refactoring
is refused before any model completion is requested or any byte is
written, the identical "raise clearly, before an expensive/destructive
call" discipline every sibling agent already establishes.

**Reads the target file's own real content back out of the sandbox —
`code_review.py`'s own read mechanism (the mirror image of `build.py`'s
write), reused verbatim, not reinvented.** Writes the refactored
content back through the identical write mechanism `build.py`/
`database.py`/`api_designer.py`/`frontend_developer.py` already
establish — but always to the caller-supplied ``filePath``, never a
path the model declares: unlike those agents, this one already knows
which file it is refactoring, so there is nothing for the model to get
wrong here that this module would need to detect. The model's own
completion therefore carries only ``FILE_CONTENT_BEGIN``/
``FILE_CONTENT_END``, no ``FILE_PATH`` line at all.

**Structured multi-field input, the identical dual-path shape
`verification.py`'s/`code_review.py`'s own ``_extract_payload`` already
establishes** — ``workingDirectory``/``filePath``/``runCommand``
(matching `verification.py`'s own field names exactly, since this agent
is meant to consume the same real test-run contract) plus one more
field, ``instruction`` (free text: what refactor to make), either
directly in ``inputs`` or as one JSON object in the assembled
``context``.

**No `evaluation.llm_calls` capability loss to disclose here** — SDK-
native from its first line, the identical "no migration debt" note
`database.py`'s/`api_designer.py`'s/`frontend_developer.py`'s own
docstrings already make.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ai_os_sdk.contracts.tool_invoker import (
    PLATFORM_PYTHON_INTERPRETER,
    PLATFORM_SANDBOX_RUN_COMMAND,
)
from ai_os_sdk.models import LLMRequest, Message, MessageRole, TraceContext

# Named, documented first-cut values — the same "placeholder safety
# limit, not yet tuned" carve-out every agent in this pack already uses.
_MAX_OUTPUT_TOKENS = 4096
_READ_TIMEOUT_SECONDS = 10.0
_READ_MAX_OUTPUT_BYTES = 65536
_RUN_TIMEOUT_SECONDS = 10.0
_RUN_MAX_OUTPUT_BYTES = 65536
_WRITE_TIMEOUT_SECONDS = 10.0
_WRITE_MAX_OUTPUT_BYTES = 65536

_REQUIRED_FIELDS = ("workingDirectory", "filePath", "runCommand", "instruction")

# code_review.py's own _READ_FILE_SCRIPT, reused verbatim — reads the
# given path and writes its raw bytes to stdout.
_READ_FILE_SCRIPT = (
    "import pathlib, sys\nsys.stdout.buffer.write(pathlib.Path(sys.argv[1]).read_bytes())\n"
)

# build.py's own _WRITE_FILE_SCRIPT, reused verbatim.
_WRITE_FILE_SCRIPT = (
    "import pathlib, sys\n"
    "target = pathlib.Path(sys.argv[1])\n"
    "target.parent.mkdir(parents=True, exist_ok=True)\n"
    "target.write_bytes(sys.stdin.buffer.read())\n"
)

# No FILE_PATH line — see this module's own docstring for why the
# model is never asked to declare one. DOTALL so `.` matches newlines
# inside the captured file content.
_CONTENT_PATTERN = re.compile(
    r"FILE_CONTENT_BEGIN\r?\n(?P<content>.*?)\r?\nFILE_CONTENT_END", re.DOTALL
)

_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "workingDirectory": {"type": "string"},
        "filePath": {"type": "string"},
        "passedBefore": {"type": "boolean"},
        "passedAfter": {"type": "boolean"},
        "refactored": {"type": "boolean"},
        "outputBefore": {"type": "string"},
        "outputAfter": {"type": "string"},
    },
    "required": [
        "workingDirectory",
        "filePath",
        "passedBefore",
        "passedAfter",
        "refactored",
        "outputBefore",
        "outputAfter",
    ],
    "additionalProperties": False,
}


class RefactoringInstructionError(Exception):
    """Either this entrypoint's own invocation contract was violated
    (called before :meth:`bind_pack_context`, or missing a required
    field), ``filePath`` does not resolve to a real, existing file
    inside ``workingDirectory``, the baseline test run (against the
    file's own already-existing content) did not pass, or the model's
    completion could not be parsed as the documented
    ``FILE_CONTENT_BEGIN``/``FILE_CONTENT_END`` format. Raised clearly,
    before any LLM call or write is attempted where possible."""


class RefactoringInput(BaseModel):
    """Documents this agent's Agent Contract "Required Inputs"
    (capability_pack_contract.md). Field names deliberately match
    ``TestAgentInput``'s own ``workingDirectory``/``filePath``/
    ``runCommand`` — this agent is meant to consume the same real
    test-run contract. ``instruction`` reaches this agent the same
    dual-path way, as one more field in the same JSON payload."""

    working_directory: str = Field(..., alias="workingDirectory")
    file_path: str = Field(..., alias="filePath")
    run_command: list[str] = Field(..., alias="runCommand")
    instruction: str = Field(
        ..., description="What refactor to make, without changing observable behaviour."
    )

    model_config = {"populate_by_name": True}


class RefactoringAgentOutput(BaseModel):
    """Documents this agent's Agent Contract "Produced Outputs." Mirrors
    the real fields :meth:`RefactoringAgentEntrypoint.execute` returns.
    ``refactored`` is mechanically derived — ``True`` iff the after-run
    also passed (the before-run always did, by the time this is
    returned, or this module would have refused already) — never a
    second LLM judgment, the identical gate principle `lint`/`qa-test`/
    `security-analysis`/`code-review` already establish."""

    working_directory: str = Field(..., alias="workingDirectory")
    file_path: str = Field(..., alias="filePath")
    passed_before: bool = Field(..., alias="passedBefore")
    passed_after: bool = Field(..., alias="passedAfter")
    refactored: bool
    output_before: str = Field(..., alias="outputBefore")
    output_after: str = Field(..., alias="outputAfter")

    model_config = {"populate_by_name": True}


def _resolve_existing_file(working_directory: Path, raw_path: str) -> Path:
    """Identical to `verification.py`'s/`build.py`'s own helper of the
    same name — duplicated, not imported."""
    stripped = raw_path.strip()
    if not stripped:
        raise RefactoringInstructionError("filePath must not be blank")

    resolved_root = working_directory.resolve()
    resolved_target = (working_directory / stripped).resolve()
    if not resolved_target.is_relative_to(resolved_root):
        raise RefactoringInstructionError(
            f"filePath {raw_path!r} resolves outside {working_directory}"
        )
    if not resolved_target.is_file():
        raise RefactoringInstructionError(
            f"filePath {raw_path!r} does not exist inside {working_directory}"
        )
    return resolved_target


def _extract_payload(inputs: dict[str, Any]) -> tuple[str, str, list[str], str]:
    """Identical dual-path shape to `verification.py`'s/`code_review.py`'s
    own ``_extract_payload`` — direct fields, or, when absent, parsed as
    JSON from the Context Manager's own assembled ``context``."""
    if all(field in inputs for field in _REQUIRED_FIELDS):
        payload = {field: inputs[field] for field in _REQUIRED_FIELDS}
    else:
        context = inputs.get("context")
        items = getattr(context, "items", None)
        if not items:
            raise RefactoringInstructionError(
                "RefactoringAgentEntrypoint requires 'workingDirectory', 'filePath', "
                "'runCommand', and 'instruction' — either directly in inputs, or as a "
                "JSON object in the assembled context"
            )
        raw = "\n\n".join(item.content for item in items)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RefactoringInstructionError(
                f"the assembled context is not a valid JSON object: {exc}"
            ) from exc
        if not isinstance(payload, dict) or not all(field in payload for field in _REQUIRED_FIELDS):
            raise RefactoringInstructionError(
                "the assembled context's JSON object is missing 'workingDirectory', "
                "'filePath', 'runCommand', or 'instruction'"
            )

    working_directory, file_path, run_command, instruction = (
        payload[field] for field in _REQUIRED_FIELDS
    )
    if not isinstance(working_directory, str) or not isinstance(file_path, str):
        raise RefactoringInstructionError("workingDirectory and filePath must both be strings")
    if not isinstance(run_command, list) or not all(isinstance(x, str) for x in run_command):
        raise RefactoringInstructionError("runCommand must be a list of strings")
    if not isinstance(instruction, str):
        raise RefactoringInstructionError("instruction must be a string")
    return working_directory, file_path, run_command, instruction


def _parse_refactored_content(completion_text: str) -> str:
    """Extracts the refactored file content from a completion following
    this module's own documented format. Raises
    :class:`RefactoringInstructionError` with the completion's own text
    included, so a failure is diagnosable."""
    match = _CONTENT_PATTERN.search(completion_text)
    if match is None:
        raise RefactoringInstructionError(
            "the model's completion did not follow the documented FILE_CONTENT_BEGIN/"
            f"FILE_CONTENT_END format:\n{completion_text}"
        )
    return match.group("content")


class RefactoringAgentEntrypoint:
    """The manifest's own ``agents[].entrypoint`` for the Refactoring
    Agent — zero-argument-constructible, the identical shape every
    other agent in this pack establishes."""

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
            raise RefactoringInstructionError(
                "RefactoringAgentEntrypoint.execute() called before bind_pack_context() bound "
                "a PackContext granting the llm:invoke and sandbox:execute permissions "
                "(context.llm/context.prompts/context.tools) — a real caller must inject "
                "one before first use"
            )

        working_directory_raw, file_path_raw, run_command, instruction = _extract_payload(inputs)

        working_directory = Path(working_directory_raw)
        if not await asyncio.to_thread(working_directory.is_dir):
            raise RefactoringInstructionError(
                f"workingDirectory {working_directory_raw!r} does not exist or is not a directory"
            )
        await asyncio.to_thread(_resolve_existing_file, working_directory, file_path_raw)

        prompt_id = inputs.get("promptId")
        prompt_version = inputs.get("promptVersion")
        model_alias = inputs.get("modelAlias")
        required_invocation_fields = ("promptId", "promptVersion", "modelAlias")
        missing = [
            name
            for name, value in zip(
                required_invocation_fields, (prompt_id, prompt_version, model_alias), strict=True
            )
            if not isinstance(value, str) or not value
        ]
        if missing:
            raise RefactoringInstructionError(
                "RefactoringAgentEntrypoint requires 'promptId', 'promptVersion', and "
                f"'modelAlias' in its inputs — missing: {', '.join(missing)}"
            )

        read_result = await self._context.tools.invoke(
            PLATFORM_SANDBOX_RUN_COMMAND,
            {
                "command": [PLATFORM_PYTHON_INTERPRETER, "-c", _READ_FILE_SCRIPT, file_path_raw],
                "working_directory": str(working_directory),
                "timeout_seconds": _READ_TIMEOUT_SECONDS,
                "max_output_bytes": _READ_MAX_OUTPUT_BYTES,
            },
        )
        if read_result.exit_code != 0:
            raise RefactoringInstructionError(
                f"could not read {file_path_raw!r} inside the sandbox: {read_result.stderr}"
            )
        original_content = read_result.stdout

        before_result = await self._context.tools.invoke(
            PLATFORM_SANDBOX_RUN_COMMAND,
            {
                "command": run_command,
                "working_directory": str(working_directory),
                "timeout_seconds": _RUN_TIMEOUT_SECONDS,
                "max_output_bytes": _RUN_MAX_OUTPUT_BYTES,
            },
        )
        passed_before = before_result.exit_code == 0 and not before_result.timed_out
        output_before = before_result.stdout + before_result.stderr
        if not passed_before:
            raise RefactoringInstructionError(
                f"the baseline test run against {file_path_raw!r}'s own existing content did "
                f"not pass (exitCode={before_result.exit_code}) — there is no passing "
                f"behaviour to preserve, refusing to refactor: {output_before}"
            )

        rendered = await self._context.prompts.render(
            prompt_id,
            {"instruction": instruction, "code": original_content},
            version=prompt_version,
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
        refactored_content = _parse_refactored_content(response.content)

        write_result = await self._context.tools.invoke(
            PLATFORM_SANDBOX_RUN_COMMAND,
            {
                "command": [PLATFORM_PYTHON_INTERPRETER, "-c", _WRITE_FILE_SCRIPT, file_path_raw],
                "working_directory": str(working_directory),
                "timeout_seconds": _WRITE_TIMEOUT_SECONDS,
                "max_output_bytes": _WRITE_MAX_OUTPUT_BYTES,
                "stdin": refactored_content,
            },
        )
        if write_result.exit_code != 0:
            raise RefactoringInstructionError(
                f"could not write the refactored content back to {file_path_raw!r}: "
                f"{write_result.stderr}"
            )

        after_result = await self._context.tools.invoke(
            PLATFORM_SANDBOX_RUN_COMMAND,
            {
                "command": run_command,
                "working_directory": str(working_directory),
                "timeout_seconds": _RUN_TIMEOUT_SECONDS,
                "max_output_bytes": _RUN_MAX_OUTPUT_BYTES,
            },
        )
        passed_after = after_result.exit_code == 0 and not after_result.timed_out
        output_after = after_result.stdout + after_result.stderr

        return {
            "workingDirectory": str(working_directory),
            "filePath": file_path_raw,
            "passedBefore": passed_before,
            "passedAfter": passed_after,
            "refactored": passed_before and passed_after,
            "outputBefore": output_before,
            "outputAfter": output_after,
        }
