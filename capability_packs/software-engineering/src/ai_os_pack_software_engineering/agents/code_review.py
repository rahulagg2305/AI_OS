"""The Code Reviewer Agent — `docs/06_capability_packs/software_engineering/
agents.md`'s "Agent Categories" Code Review entry, FR-039 ("Review
generated code and produce structured findings... Findings carry file,
line, severity, and confidence") — a **MUST**-priority v1 requirement,
unlike every prior new agent this pack added (all SHOULD). This pack's
twelfth agent, and the fifth genuinely new agent (not a migration)
since the module-27 Platform SDK hard gate lifted.

**`lint.py`'s own docstring already discloses the real reason this
agent still needed to exist**: `lint` is "closest to FR-039 while
satisfying only its static-analysis portion" — a real syntax check, no
`confidence`, no readability/standards judgment. FR-039's own
`confidence` field is inherently a model judgment, not a fact a
mechanical tool can compute — this is therefore the first agent in
this pack's own "code analysis" family (`lint`, `qa-test`,
`security-analysis`) to deliberately use an LLM's *opinion* as the
whole point, rather than avoiding it. Findings are real LLM output,
disclosed as such — never independently re-judged by this module.

**Reads the target file's own real content back out of the sandbox —
the mirror image of `build.py`'s own write, not a new mechanism.** No
agent in this pack previously needed a file's raw content *returned*
to it (`lint`/`qa-test`/`security-analysis` all pass a path to a
sandboxed command and read back a verdict, never raw content); this
agent needs the content itself to embed in its own LLM prompt. The
identical `PLATFORM_SANDBOX_RUN_COMMAND` tool every other sandboxed
agent already uses, with a script that is `build.py`'s own
`_WRITE_FILE_SCRIPT` in reverse (reads bytes from the path, writes them
to stdout, instead of the reverse) — reusing the real tool contract's
own `stdout` field, the same field Lint/QA-Test/Security-Analysis
already read their own results from.

**The model responds with a real JSON array, not this pack's usual
`FILE_PATH`/`FILE_CONTENT_BEGIN` delimited text format** — a deliberate,
disclosed departure. That format exists specifically to avoid needing
the model to escape arbitrary *file content* (`build.py`'s own
docstring); a findings array is short, structured data (a line number,
one of three severity words, a confidence number, a short message),
where JSON's own escaping is exactly the tool built for the job, not a
risk to avoid. Parsed and validated field-by-field via Pydantic before
being trusted — a malformed or out-of-range response is rejected with a
clear error, never silently coerced or partially accepted.

**`file` is attached by this module from the real, caller-supplied
``filePath`` — never trusted from the model's own response.** The
model is never asked to echo the path back; there is nothing for it to
get wrong here that this module would need to detect.

**Supports the same JSON-context fallback every other agent in this
pack's "code analysis" family already establishes — a real omission
found and fixed before this ticket shipped, not designed in from the
start.** An early draft read ``workingDirectory``/``filePath`` directly
from ``inputs`` only; every sibling (`lint`/`qa-test`/
`security_analysis`) also falls back to parsing the Context Manager's
own assembled ``context`` when those fields are absent, since that is
the real channel a live `se.delivery_pipeline` step would use, not raw
inputs. Fixed via :func:`_extract_payload`, identical to
`security_analysis.py`'s own helper of the same name.

**No `evaluation.llm_calls` capability loss to disclose here** — SDK-
native from its first line, the identical "no migration debt" note
`database.py`'s/`api_designer.py`'s/`security_analysis.py`'s/
`release.py`'s own docstrings already make.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from ai_os_sdk.contracts.tool_invoker import (
    PLATFORM_PYTHON_INTERPRETER,
    PLATFORM_SANDBOX_RUN_COMMAND,
)
from ai_os_sdk.models import LLMRequest, Message, MessageRole, TraceContext

# Named, documented first-cut values — the identical "placeholder
# safety limit, not yet tuned" carve-out every agent in this pack
# already uses.
_MAX_OUTPUT_TOKENS = 2048
_READ_TIMEOUT_SECONDS = 10.0
_READ_MAX_OUTPUT_BYTES = 65536

_REQUIRED_INVOCATION_FIELDS = ("promptId", "promptVersion", "modelAlias")

# build.py's own _WRITE_FILE_SCRIPT, in reverse — reads the given path
# and writes its raw bytes to stdout. Portable (pathlib/sys.stdout
# only, no shell).
_READ_FILE_SCRIPT = (
    "import pathlib, sys\nsys.stdout.buffer.write(pathlib.Path(sys.argv[1]).read_bytes())\n"
)


class Severity(StrEnum):
    """A real, minimal, three-level scale — this ticket's own choice,
    since no per-finding severity vocabulary exists anywhere else in
    this codebase to reuse (the manifest schema's own `severity` enum,
    `["blocking", "warning"]`, is a *quality-gate* concept, a different
    axis than one finding's own real severity)."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CodeReviewInstructionError(Exception):
    """Either this entrypoint's own invocation contract was violated
    (called before :meth:`bind_pack_context`, or missing a required
    ``promptId``/``promptVersion``/``modelAlias`` field), ``filePath``
    does not resolve to a real, existing file inside
    ``workingDirectory``, or the model's completion could not be
    parsed and validated as the documented JSON findings array. Raised
    clearly, with the real completion text included when parsing
    fails, never a silent, empty findings list standing in for a real
    failure."""


class CodeReviewInput(BaseModel):
    """Documents this agent's Agent Contract "Required Inputs"
    (capability_pack_contract.md). Field names deliberately match
    ``BuildAgentOutput``'s own ``workingDirectory``/``filePath`` — the
    identical convention ``LintAgentInput``/``TestAgentInput``/
    ``SecurityAnalysisInput`` already establish."""

    working_directory: str = Field(..., alias="workingDirectory")
    file_path: str = Field(..., alias="filePath")

    model_config = {"populate_by_name": True}


class Finding(BaseModel):
    """One real review finding. ``file`` is attached by this module,
    never parsed from the model's own response — see this module's
    own docstring."""

    file: str
    line: int
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    message: str


class _ModelFinding(BaseModel):
    """The four fields the model is actually asked for — ``file`` is
    deliberately absent; this module attaches it separately."""

    line: int
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    message: str


class CodeReviewerAgentOutput(BaseModel):
    """Documents this agent's Agent Contract "Produced Outputs." Mirrors
    the real fields :meth:`CodeReviewerAgentEntrypoint.execute` returns."""

    file_path: str = Field(..., alias="filePath")
    findings: list[Finding]

    model_config = {"populate_by_name": True}


_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "filePath": {"type": "string"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "file": {"type": "string"},
                    "line": {"type": "integer"},
                    "severity": {"type": "string", "enum": ["high", "medium", "low"]},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "message": {"type": "string"},
                },
                "required": ["file", "line", "severity", "confidence", "message"],
            },
        },
    },
    "required": ["filePath", "findings"],
    "additionalProperties": False,
}


_REQUIRED_FIELDS = ("workingDirectory", "filePath")


def _extract_payload(inputs: dict[str, Any]) -> tuple[str, str]:
    """Identical fallback shape to `security_analysis.py`'s own
    ``_extract_payload`` — direct fields, or, when absent, parsed as
    JSON from the Context Manager's own assembled ``context``. Every
    other agent in this pack's own "code analysis" family already
    establishes this fallback so it can be chained into a real
    workflow, where the executor supplies the assembled context, not
    raw inputs — this agent had omitted it, a real inconsistency found
    and fixed before this ticket shipped."""
    if all(field in inputs for field in _REQUIRED_FIELDS):
        payload = {field: inputs[field] for field in _REQUIRED_FIELDS}
    else:
        context = inputs.get("context")
        items = getattr(context, "items", None)
        if not items:
            raise CodeReviewInstructionError(
                "CodeReviewerAgentEntrypoint requires 'workingDirectory' and 'filePath' "
                "— either directly in inputs, or as a JSON object in the assembled context"
            )
        raw = "\n\n".join(item.content for item in items)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CodeReviewInstructionError(
                f"the assembled context is not a valid JSON object: {exc}"
            ) from exc
        if not isinstance(payload, dict) or not all(field in payload for field in _REQUIRED_FIELDS):
            raise CodeReviewInstructionError(
                "the assembled context's JSON object is missing 'workingDirectory' or 'filePath'"
            )

    working_directory, file_path = (payload[field] for field in _REQUIRED_FIELDS)
    if not isinstance(working_directory, str) or not isinstance(file_path, str):
        raise CodeReviewInstructionError("workingDirectory and filePath must both be strings")
    return working_directory, file_path


def _resolve_existing_file(working_directory: Path, raw_path: str) -> Path:
    """Identical to `lint.py`'s/`security_analysis.py`'s own helper of
    the same name — duplicated, not imported."""
    stripped = raw_path.strip()
    if not stripped:
        raise CodeReviewInstructionError("filePath must not be blank")

    resolved_root = working_directory.resolve()
    resolved_target = (working_directory / stripped).resolve()
    if not resolved_target.is_relative_to(resolved_root):
        raise CodeReviewInstructionError(
            f"filePath {raw_path!r} resolves outside {working_directory}"
        )
    if not resolved_target.is_file():
        raise CodeReviewInstructionError(
            f"filePath {raw_path!r} does not exist inside {working_directory}"
        )
    return resolved_target


def _parse_findings(completion_text: str, *, file_path: str) -> list[Finding]:
    """Parses and validates the model's own completion as the
    documented JSON findings array, attaching the real, caller-supplied
    ``file_path`` to each — never trusting one out of the model's own
    response. Raises :class:`CodeReviewInstructionError` for any
    failure, with the real completion text included."""
    try:
        parsed = json.loads(completion_text)
    except json.JSONDecodeError as exc:
        raise CodeReviewInstructionError(
            f"the model's completion was not valid JSON: {exc}\ncompletion: {completion_text}"
        ) from exc

    if not isinstance(parsed, list):
        raise CodeReviewInstructionError(
            f"the model's completion was not a JSON array: {completion_text}"
        )

    try:
        model_findings = [_ModelFinding.model_validate(item) for item in parsed]
    except ValidationError as exc:
        raise CodeReviewInstructionError(
            f"the model's completion did not match the documented findings shape: {exc}\n"
            f"completion: {completion_text}"
        ) from exc

    return [
        Finding(file=file_path, **model_finding.model_dump()) for model_finding in model_findings
    ]


class CodeReviewerAgentEntrypoint:
    """The manifest's own ``agents[].entrypoint`` for the Code Reviewer
    Agent — zero-argument-constructible, trivially so here: nothing is
    built lazily, the identical shape ``documentation.py``'s own
    docstring already establishes for an agent with no internal state
    to guard."""

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
            raise CodeReviewInstructionError(
                "CodeReviewerAgentEntrypoint.execute() called before bind_pack_context() bound "
                "a PackContext granting the llm:invoke and sandbox:execute permissions "
                "(context.llm/context.prompts/context.tools) — a real caller must inject "
                "one before first use"
            )

        working_directory_raw, file_path_raw = _extract_payload(inputs)

        working_directory = Path(working_directory_raw)
        if not await asyncio.to_thread(working_directory.is_dir):
            raise CodeReviewInstructionError(
                f"workingDirectory {working_directory_raw!r} does not exist or is not a directory"
            )
        await asyncio.to_thread(_resolve_existing_file, working_directory, file_path_raw)

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
            raise CodeReviewInstructionError(
                "CodeReviewerAgentEntrypoint requires 'promptId', 'promptVersion', and "
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
            raise CodeReviewInstructionError(
                f"could not read {file_path_raw!r} inside the sandbox: {read_result.stderr}"
            )
        code = read_result.stdout

        rendered = await self._context.prompts.render(
            prompt_id, {"filePath": file_path_raw, "code": code}, version=prompt_version
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
        findings = _parse_findings(response.content, file_path=file_path_raw)

        return {
            "filePath": file_path_raw,
            "findings": [finding.model_dump() for finding in findings],
        }
