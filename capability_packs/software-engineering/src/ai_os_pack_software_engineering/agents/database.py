"""The Database Agent — `docs/06_capability_packs/software_engineering/
agents.md`'s "Agent Categories" Database entry, FR-036 ("Design database
schemas and migrations... Migration applies cleanly and is reversible").
This pack's eighth agent, and the first added since the module-27
Platform SDK hard gate lifted for real new agents (not a migration of an
existing one) — built directly against `ai_os_sdk.contracts` from the
start, the identical zero-argument-constructible,
:meth:`bind_pack_context`-injected shape `architecture.py`/`build.py`
already establish, never a Kernel import.

**A genuine design fork was found and resolved before writing this
module (product-owner decision, 2026-08-06): the migration artifact's
own shape.** Three real options existed — (1) a plain SQL `-- UP`/
`-- DOWN` pair, written through the sandbox exactly like `build.py`
writes one file; (2) a full Alembic revision module
(`kernel/alembic/versions/*.py`, `upgrade()`/`downgrade()`), linked into
this project's real migration chain; (3) a structured schema-diff
description compiled to SQL by a new, deterministic Kernel-side
component. (2) was rejected: a wrong model-generated `down_revision`
could corrupt the real chain if ever run outside an isolated test
config, and correctly chaining revision ids is a much harder target for
a non-deterministic model than this ticket's own three-line scope calls
for. (3) was rejected as over-engineering — a whole new DDL-diff-to-SQL
compiler this ticket never asked for, against this pack's own
established "smallest real slice" discipline (see `architecture.py`'s
own docstring). **(1) was chosen**: it satisfies FR-036's literal
acceptance criterion directly and is provable with a real Postgres
container, with no new abstraction beyond what `build.py` already
established.

**Reuses `build.py`'s own real write mechanism verbatim** — the
identical `FILE_PATH`/`FILE_CONTENT_BEGIN`/`FILE_CONTENT_END` delimited
format (avoids the same JSON-escaping risk `build.py`'s own docstring
already names), the identical safe-relative-path containment check, and
the identical write-through-sandbox script (portable, no shell). The
one real addition: this agent also splits the written `FILE_CONTENT`
into `-- UP`/`-- DOWN` halves and returns both separately
(`upSql`/`downSql`), so a real caller can apply and later revert this
specific migration without re-parsing the file. **A completion with no
parseable `-- DOWN` section is refused before any sandbox call is
attempted** — FR-036's own "is reversible" criterion enforced as a real
precondition, not merely documented, the identical "raise clearly,
before any sandbox call" discipline `build.py`'s own
`BuildInstructionError` already establishes for a malformed completion.

**No `evaluation.llm_calls` capability loss to disclose here** — unlike
`architecture.py`/`build.py`/`documentation.py`, this agent was never
migrated from a pre-SDK version that used to record completions; it is
SDK-native from its first line. It inherits the identical, already-real
recording path every SDK-native agent gets for free once resolved
through `SqlAgentRegistry` (`P04-S01-M12-T10` — see that ticket and
`llm_gateway_adapter.py`'s own docstring; this session found and fixed a
stale claim in `feature_inventory.md` §6a implying this was still
broken for every agent in this pack, which it is not).
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
# limit, not yet tuned" carve-out `build.py` already uses. A generated
# single migration file is not expected to exceed these; a future step
# can make either configurable once a real need to tune them arises.
_MAX_OUTPUT_TOKENS = 4096
_WRITE_TIMEOUT_SECONDS = 10.0
_WRITE_MAX_OUTPUT_BYTES = 65536

_WORKSPACE_PREFIX = "aios-database-agent-"

_REQUIRED_INVOCATION_FIELDS = ("promptId", "promptVersion", "modelAlias")

# Identical shape to build.py's own write-file script — portable
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

# Splits the parsed FILE_CONTENT into its forward/reverse halves. DOTALL
# so `.` matches newlines within each SQL block.
_UP_DOWN_PATTERN = re.compile(
    r"--\s*UP\s*\r?\n(?P<up>.*?)\r?\n--\s*DOWN\s*\r?\n(?P<down>.*)",
    re.DOTALL,
)


class DatabaseMigrationInstructionError(Exception):
    """Either this entrypoint's own invocation contract was violated
    (called before :meth:`bind_pack_context`, or missing a required
    ``promptId``/``promptVersion``/``modelAlias`` field), or the model's
    completion could not be turned into a safe, reversible migration
    write — it did not follow the documented ``FILE_PATH``/
    ``FILE_CONTENT_BEGIN``/``FILE_CONTENT_END`` format, its content had
    no parseable ``-- UP``/``-- DOWN`` split, or its declared path does
    not resolve inside the sandbox working directory. Raised clearly,
    before any sandbox call is attempted."""


class DatabaseMigrationInput(BaseModel):
    """Documents this agent's Agent Contract "Required Inputs"
    (capability_pack_contract.md). **Not yet validated at runtime** —
    see :mod:`ai_os_pack_software_engineering.agents.architecture`'s own
    ``ArchitectureProposalInput`` for why (the identical, still
    unchanged, "no per-step input-mapping mechanism exists" scope).
    ``design`` reaches this agent today via the Context Manager's own
    assembled ``context`` prompt variable, the one real channel this
    codebase's ``AgentStepExecutor`` establishes — it may be the
    Architecture Agent's own proposal, or a simpler direct instruction;
    either is free text from this agent's own point of view."""

    design: str = Field(
        ..., description="A design proposal or direct instruction describing one schema change."
    )


class DatabaseAgentOutput(BaseModel):
    """Documents this agent's Agent Contract "Produced Outputs." Mirrors
    the real fields :meth:`DatabaseAgentEntrypoint.execute` returns.
    ``up_sql``/``down_sql`` are the parsed halves of the written file's
    own content — kept alongside the raw file so a future caller (a
    migration-runner tool, or this ticket's own reversibility proof) can
    apply/revert without re-parsing the file itself."""

    working_directory: str = Field(..., alias="workingDirectory")
    file_path: str = Field(..., alias="filePath")
    written: bool
    exit_code: int | None = Field(..., alias="exitCode")
    stdout: str
    stderr: str
    instruction: str
    up_sql: str = Field(..., alias="upSql")
    down_sql: str = Field(..., alias="downSql")

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
        "upSql": {"type": "string"},
        "downSql": {"type": "string"},
    },
    "required": [
        "workingDirectory",
        "filePath",
        "written",
        "exitCode",
        "stdout",
        "stderr",
        "instruction",
        "upSql",
        "downSql",
    ],
    "additionalProperties": False,
}


def _resolve_safe_relative_path(working_directory: Path, raw_path: str) -> Path:
    """Identical to build.py's own helper of the same name — resolves
    ``raw_path`` (the model's own declared ``FILE_PATH``) against
    ``working_directory`` and returns a verified-safe relative path, or
    raises :class:`DatabaseMigrationInstructionError`."""
    stripped = raw_path.strip()
    if not stripped:
        raise DatabaseMigrationInstructionError("the model's FILE_PATH must not be blank")

    resolved_root = working_directory.resolve()
    resolved_target = (working_directory / stripped).resolve()
    if not resolved_target.is_relative_to(resolved_root):
        raise DatabaseMigrationInstructionError(
            f"FILE_PATH {raw_path!r} resolves outside the sandbox working directory"
        )
    return resolved_target.relative_to(resolved_root)


def _parse_migration_instruction(completion_text: str) -> tuple[str, str]:
    """Extracts ``(raw_path, content)`` from a completion following this
    module's own documented format — identical to build.py's own
    ``_parse_build_instruction``."""
    match = _INSTRUCTION_PATTERN.search(completion_text)
    if match is None:
        raise DatabaseMigrationInstructionError(
            "the model's completion did not follow the documented FILE_PATH/"
            f"FILE_CONTENT_BEGIN/FILE_CONTENT_END format:\n{completion_text}"
        )
    return match.group("path"), match.group("content")


def _split_up_down(content: str) -> tuple[str, str]:
    """Extracts ``(up_sql, down_sql)`` from a migration file's own
    content. Raises :class:`DatabaseMigrationInstructionError` when no
    ``-- DOWN`` section is present — FR-036's "is reversible" criterion
    enforced as a real precondition, before any sandbox write."""
    match = _UP_DOWN_PATTERN.search(content)
    if match is None:
        raise DatabaseMigrationInstructionError(
            "the model's file content had no parseable '-- UP'/'-- DOWN' split — a "
            f"migration must be reversible:\n{content}"
        )
    return match.group("up").strip(), match.group("down").strip()


def _build_variables(inputs: dict[str, Any]) -> dict[str, Any]:
    """Identical to build.py's own helper of the same name — mirrors
    :meth:`~ai_os_kernel.workflow_engine.prompted_agent.PromptedAgent.
    _build_variables` exactly, duck-typed rather than
    ``isinstance``-checked against ``AssembledContext``."""
    variables = dict(inputs.get("variables") or {})
    context = inputs.get("context")
    items = getattr(context, "items", None)
    if items and "context" not in variables:
        variables["context"] = "\n\n".join(item.content for item in items)
    return variables


class DatabaseAgentEntrypoint:
    """The manifest's own ``agents[].entrypoint`` for the Database Agent
    — zero-argument-constructible
    (:class:`~ai_os_kernel.workflow_engine.entrypoint_loader.EntrypointLoader`,
    :class:`~ai_os_kernel.workflow_engine.registry.SqlAgentRegistry`).
    Keeps the identical narrow lock ``build.py`` keeps, guarding only
    lazy working-directory creation, not any LLM composition — the
    identical reasoning, not re-litigated here.

    ``working_directory`` is an optional constructor override — always
    its default (``None``) in production, and how a test substitutes a
    known temporary directory, the identical shape ``build.py``
    establishes."""

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
            raise DatabaseMigrationInstructionError(
                "DatabaseAgentEntrypoint.execute() called before bind_pack_context() bound a "
                "PackContext granting the llm:invoke, and sandbox:execute permissions "
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
            raise DatabaseMigrationInstructionError(
                "DatabaseAgentEntrypoint requires 'promptId', 'promptVersion', and "
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
        raw_path, content = _parse_migration_instruction(instruction_text)
        up_sql, down_sql = _split_up_down(content)
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
            "upSql": up_sql,
            "downSql": down_sql,
        }

    async def _ensure_working_directory(self) -> Path:
        async with self._directory_lock:
            if self._working_directory is None:
                self._working_directory = await asyncio.to_thread(
                    lambda: Path(tempfile.mkdtemp(prefix=_WORKSPACE_PREFIX))
                )
        return self._working_directory
