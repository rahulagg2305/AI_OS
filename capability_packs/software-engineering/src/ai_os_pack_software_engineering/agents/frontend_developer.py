"""The Frontend Developer Agent — `docs/06_capability_packs/
software_engineering/agents.md`'s "Agent Categories" Frontend
Development entry, FR-035 ("Implement frontend components from the
plan... As FR-034 for frontend"). This pack's own first implementation
of the `frontend-developer` identity `workflows.md` §4's own
`se.implement_task` graph names as one of the real `task.kind`-routed
choices ("backend-developer (or frontend-developer / database, by
task.kind)") — no `backend-developer` ticket exists anywhere in this
roadmap (a real, disclosed gap this ticket does not attempt to close),
so this agent's real value is establishing the distinct, catalog-
documented `frontend-developer` identity `se.implement_task`'s routing
needs, not a new file-writing mechanism.

**Reuses `build.py`'s/`database.py`'s/`api_designer.py`'s own real
write mechanism verbatim** — the identical `FILE_PATH`/
`FILE_CONTENT_BEGIN`/`FILE_CONTENT_END` delimited format, the identical
safe-relative-path containment check, and the identical
write-through-sandbox script. **The one real addition, a deliberate,
disclosed choice, not FR-mandated:** the model's declared `FILE_PATH`
must end in a real, closed frontend-file extension (`_FRONTEND_EXTENSIONS`)
or the completion is refused before any sandbox call — the identical
"raise clearly, before any sandbox call" discipline `build.py`'s/
`database.py`'s/`api_designer.py`'s own instruction errors already
establish, here enforcing this agent's own name ("frontend"), not a
letter of FR-035 itself.

**FR-035's own literal acceptance criterion ("generated code builds
and passes generated tests in the sandbox") is deliberately NOT
enforced by this agent** — that is qa-test's/the Quality Gate Engine's
generic job for any file `build.py`'s own mechanism writes, exactly as
undisclosed for `build.py` itself; inventing a second, agent-specific
test runner here would be a parallel mechanism, not a real addition.

**No `evaluation.llm_calls` capability loss to disclose here** — SDK-
native from its first line, the identical "no migration debt" note
`database.py`'s/`api_designer.py`'s own docstrings already make.
"""

from __future__ import annotations

import asyncio
import re
import tempfile
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
# limit, not yet tuned" carve-out `build.py` already uses.
_MAX_OUTPUT_TOKENS = 4096
_WRITE_TIMEOUT_SECONDS = 10.0
_WRITE_MAX_OUTPUT_BYTES = 65536

_WORKSPACE_PREFIX = "aios-frontend-developer-agent-"

_REQUIRED_INVOCATION_FIELDS = ("promptId", "promptVersion", "modelAlias")

# A real, closed vocabulary of frontend file extensions — this agent's
# own name is its scope, not a letter of FR-035. Component markup/logic
# (tsx/jsx/ts/js/vue/svelte/html) and component styling (css/scss),
# matching agents.md's own "user interfaces and client-side logic."
_FRONTEND_EXTENSIONS = frozenset(
    {".tsx", ".jsx", ".ts", ".js", ".vue", ".svelte", ".html", ".css", ".scss"}
)

# Identical to build.py's own write-file script — portable
# (pathlib/sys.stdin only, no shell), confined to writing exactly the
# one path it is given, relative to its own cwd (the sandbox's
# working_directory).
_WRITE_FILE_SCRIPT = (
    "import pathlib, sys\n"
    "target = pathlib.Path(sys.argv[1])\n"
    "target.parent.mkdir(parents=True, exist_ok=True)\n"
    "target.write_bytes(sys.stdin.buffer.read())\n"
)

# Identical to build.py's own _INSTRUCTION_PATTERN — see that module's
# docstring for why this is a fixed delimited format, not JSON. DOTALL
# so `.` matches newlines inside the captured file content.
_INSTRUCTION_PATTERN = re.compile(
    r"FILE_PATH:[ \t]*(?P<path>.+?)[ \t]*\r?\n"
    r"FILE_CONTENT_BEGIN\r?\n"
    r"(?P<content>.*?)"
    r"\r?\nFILE_CONTENT_END",
    re.DOTALL,
)

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
    },
    "required": [
        "workingDirectory",
        "filePath",
        "written",
        "exitCode",
        "stdout",
        "stderr",
        "instruction",
    ],
    "additionalProperties": False,
}


class FrontendDeveloperInstructionError(Exception):
    """Either this entrypoint's own invocation contract was violated
    (called before :meth:`bind_pack_context`, or missing a required
    ``promptId``/``promptVersion``/``modelAlias`` field), or the model's
    completion could not be turned into a safe frontend-file write — it
    did not follow the documented ``FILE_PATH``/``FILE_CONTENT_BEGIN``/
    ``FILE_CONTENT_END`` format, its declared path is not a real
    frontend file extension, or its declared path does not resolve
    inside the sandbox working directory. Raised clearly, before any
    sandbox call is attempted."""


class FrontendComponentInput(BaseModel):
    """Documents this agent's Agent Contract "Required Inputs"
    (capability_pack_contract.md). ``plan`` reaches this agent today via
    the Context Manager's own assembled ``context`` prompt variable, the
    one real channel this codebase's ``AgentStepExecutor`` establishes —
    it may be one task from the Technical Planner's own real plan
    artifact (`ai_os_pack_software_engineering.agents.technical_planner.
    PlanTask`), or a simpler direct instruction; either is free text
    from this agent's own point of view, the identical "free text in,
    from wherever a real composition sources it" shape `build.py`'s own
    ``instruction`` already establishes."""

    plan: str = Field(
        ..., description="A plan task or direct instruction describing one frontend component."
    )


class FrontendDeveloperAgentOutput(BaseModel):
    """Documents this agent's Agent Contract "Produced Outputs." Mirrors
    the real fields :meth:`FrontendDeveloperAgentEntrypoint.execute`
    returns — identical shape to `BuildAgentOutput`; no new field beyond
    it, since this agent's one real addition is a precondition on the
    write, not a new derived value (unlike `database.py`'s `upSql`/
    `downSql`)."""

    working_directory: str = Field(..., alias="workingDirectory")
    file_path: str = Field(..., alias="filePath")
    written: bool
    exit_code: int | None = Field(..., alias="exitCode")
    stdout: str
    stderr: str
    instruction: str

    model_config = {"populate_by_name": True}


def _resolve_safe_relative_path(working_directory: Path, raw_path: str) -> Path:
    """Identical to `build.py`'s own helper of the same name — resolves
    ``raw_path`` (the model's own declared ``FILE_PATH``) against
    ``working_directory`` and returns a verified-safe relative path, or
    raises :class:`FrontendDeveloperInstructionError`."""
    stripped = raw_path.strip()
    if not stripped:
        raise FrontendDeveloperInstructionError("the model's FILE_PATH must not be blank")

    resolved_root = working_directory.resolve()
    resolved_target = (working_directory / stripped).resolve()
    if not resolved_target.is_relative_to(resolved_root):
        raise FrontendDeveloperInstructionError(
            f"FILE_PATH {raw_path!r} resolves outside the sandbox working directory"
        )
    return resolved_target.relative_to(resolved_root)


def _require_frontend_extension(relative_path: Path) -> None:
    """This agent's own one real addition — see this module's own
    docstring. Enforced before any sandbox call, the identical
    "raise clearly, before any sandbox call" discipline every sibling
    build.py-based agent already establishes."""
    if relative_path.suffix.lower() not in _FRONTEND_EXTENSIONS:
        raise FrontendDeveloperInstructionError(
            f"FILE_PATH {str(relative_path)!r} is not a real frontend file extension "
            f"(expected one of {sorted(_FRONTEND_EXTENSIONS)}) — this agent writes frontend "
            "components only"
        )


def _parse_frontend_instruction(completion_text: str) -> tuple[str, str]:
    """Identical to `build.py`'s own `_parse_build_instruction` —
    extracts ``(raw_path, content)`` from a completion following this
    module's own documented format."""
    match = _INSTRUCTION_PATTERN.search(completion_text)
    if match is None:
        raise FrontendDeveloperInstructionError(
            "the model's completion did not follow the documented FILE_PATH/"
            f"FILE_CONTENT_BEGIN/FILE_CONTENT_END format:\n{completion_text}"
        )
    return match.group("path"), match.group("content")


def _build_variables(inputs: dict[str, Any]) -> dict[str, Any]:
    """Mirrors `build.py`'s own ``_build_variables`` exactly."""
    variables = dict(inputs.get("variables") or {})
    context = inputs.get("context")
    items = getattr(context, "items", None)
    if items and "context" not in variables:
        variables["context"] = "\n\n".join(item.content for item in items)
    return variables


class FrontendDeveloperAgentEntrypoint:
    """The manifest's own ``agents[].entrypoint`` for the Frontend
    Developer Agent — zero-argument-constructible, the identical shape
    `build.py`'s own entrypoint establishes, including its own narrow
    lock guarding only lazy working-directory creation (see that
    module's own docstring for why the lock is not fully obsolete)."""

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
            raise FrontendDeveloperInstructionError(
                "FrontendDeveloperAgentEntrypoint.execute() called before bind_pack_context() "
                "bound a PackContext granting both the llm:invoke and sandbox:execute "
                "permissions (context.llm/context.prompts/context.tools) — a real caller must "
                "inject one before first use"
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
            raise FrontendDeveloperInstructionError(
                "FrontendDeveloperAgentEntrypoint requires 'promptId', 'promptVersion', and "
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
        raw_path, content = _parse_frontend_instruction(instruction_text)
        relative_path = await asyncio.to_thread(
            _resolve_safe_relative_path, working_directory, raw_path
        )
        _require_frontend_extension(relative_path)

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
        }

    async def _ensure_working_directory(self) -> Path:
        async with self._directory_lock:
            if self._working_directory is None:
                self._working_directory = await asyncio.to_thread(
                    lambda: Path(tempfile.mkdtemp(prefix=_WORKSPACE_PREFIX))
                )
        return self._working_directory
