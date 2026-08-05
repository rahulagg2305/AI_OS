"""The Build Agent — agent_architecture.md's "Agent Categories (Initial
Target)" #4/#5 (Backend/Frontend Development), reduced to the smallest
real slice this step approves: given a design/instruction, produce
*one* concrete file and genuinely write it — the first real connection
in this codebase between an LLM-produced instruction and sandboxed
execution.

**Migrated onto the real Platform SDK (``platform_sdk_v1_scope.md``
step 12) — the third migration, and the first needing both real gateway
injection AND real tool injection together.** This entrypoint now
implements :class:`~ai_os_sdk.contracts.Agent` and
:class:`~ai_os_sdk.contracts.entrypoint_context.PackContextReceiver`
only. It imports nothing from ``ai_os_kernel`` at all. Where it used to
lazily build its own real :class:`~ai_os_kernel.workflow_engine.
prompted_agent.PromptedAgent` and construct a
:class:`~ai_os_kernel.workflow_engine.sandboxed_tool.SandboxedCommandTool`
directly over an injected :class:`~ai_os_kernel.sandbox.executor.
SandboxExecutor`, it now reads ``self._context.llm``/
``self._context.prompts`` (replicating
:meth:`~ai_os_kernel.prompted_completion.PromptedCompletionService.
complete_from_prompt`'s own real render-then-complete logic, exactly as
``requirements_analyst.py``/``architecture.py`` already do) and calls
``self._context.tools.invoke(PLATFORM_SANDBOX_RUN_COMMAND, ...)`` for
the write itself, exactly as ``verification.py`` (step 9) already does.

**The lock is *not* fully obsolete here — a real, discovered nuance
neither step 10 nor step 11 needed to consider.** Those two migrations
found their own lazy-build lock entirely obsolete, because the *only*
thing it ever guarded (a concurrent double-build race on a lazily
constructed LLM completion service) cannot occur once composition
arrives once, synchronously, via :meth:`bind_pack_context`. This agent's
own lock guarded a *second*, unrelated concern too: lazily creating its
own private working directory (``tempfile.mkdtemp()``) on first
:meth:`execute`, when none is supplied — a concern that has nothing to
do with ``PackContext`` injection at all and is not resolved by it. Two
concurrent first ``execute()`` calls with no shared lock would each call
``mkdtemp()`` independently, silently forking into two different,
unrelated directories instead of sharing one — a real correctness bug,
not merely a missed optimisation. **This module therefore keeps a
narrower lock**, guarding only the working-directory creation, not any
LLM composition (there is none left to guard). Proven by a concurrent-
execute test asserting every call shares the identical working
directory, not merely that all calls individually succeed.

**A real tension using ``ToolInvoker`` instead of direct sandbox
construction was found at step 12, then closed for good at step 12a
(inserted, 2026-07-29) — no longer a constructor default this module
must keep in sync.** The old, pre-migration code asked its own injected
``SandboxExecutor`` for its ``python_command`` property (``sys.executable``
for ``LocalSubprocessSandbox``, ``python3`` for ``DockerSandbox`` — a
real, backend-specific fact). A migrated agent no longer holds a
``SandboxExecutor`` at all — only a generic
:class:`~ai_os_sdk.contracts.ToolInvoker`. Step 12's own first attempt
resolved this with a constructor-time default (``("python3",)``) —
correct for the real system-wide default backend, but silently wrong
the moment ``AIOS_SANDBOX_BACKEND=local`` was set without also updating
that default: a real, recorded regression from the pre-migration
behaviour's own "always automatically correct" guarantee. **Step 12a
closes this properly, at the correct layer**: this module now writes
:data:`~ai_os_sdk.contracts.tool_invoker.PLATFORM_PYTHON_INTERPRETER`
as the interpreter token in its own ``command``, and
``ToolInvokerAdapter`` (the one place that still holds the real
``SandboxExecutor``) substitutes it with that instance's own real
``python_command`` before dispatch — restoring automatic correctness
against every backend, with no constructor default, and no backend
knowledge, in this module at all. See that token's own docstring for
the full history and reasoning, and ``platform_sdk_v1_scope.md`` §6p
for this step's own record.

**The identical, already-recorded ``evaluation.llm_calls`` capability
loss applies here too.** No new finding — see
``requirements_analyst.py``'s own docstring for the full reasoning.

**The LLM's file-write instruction is parsed from a fixed, explicit
text format, not JSON.** JSON would need the model to correctly escape
arbitrary file content (quotes, newlines, backslashes) inside a JSON
string — a real source of avoidable parse failures for exactly the
payload (source code) this agent exists to move. A delimited format
(``FILE_PATH: ...`` / ``FILE_CONTENT_BEGIN`` ... ``FILE_CONTENT_END``)
needs no escaping at all: the content between the markers is used
verbatim. This agent's own prompt (``prompts/build_write_file.md``)
instructs the model to respond in exactly this format and nothing else.

**The write itself happens through the sandbox, never through this
module's own Python code touching the filesystem directly.** File
content is delivered to a small, fixed write-file script via the
``platform.sandbox.run_command`` tool's own ``stdin`` input (a string;
the real Kernel-side adapter encodes it) rather than as a command-line
argument, avoiding both shell-quoting risk and argv length limits for
what may be a full source file. The script itself never touches
anything outside ``working_directory`` (POSIX/Windows-portable, uses
only ``pathlib``/``sys.stdin``, no shell).

**The model's own declared file path is independently validated by
this module before being trusted, not merely passed through.** The real
sandbox backend provides no filesystem containment on its own — a path
like ``../../etc/passwd`` would otherwise reach the write script
unchanged. :func:`_resolve_safe_relative_path` resolves the model's
path against the working directory and rejects anything that does not
remain inside it (absolute paths, ``..`` escapes, and — on Windows
specifically — a root-anchored-but-driveless path like ``/etc/passwd``,
which naive ``Path.is_absolute()``-only checks miss). This is the
identical canonical-path-resolution discipline security_architecture.md
§5.2 already mandates for Tier 2 operations, applied here defensively
for a Tier 1 one.

**No per-workflow workspace exists yet (security_architecture.md §5.3
— still Stage C, unbuilt).** Absent an explicit ``working_directory``,
this agent creates and reuses one private temporary directory of its
own — real isolation for *this agent instance*, not the documented
per-workflow isolation a real Workspace Service will eventually
provide.
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
# limit, not yet tuned" carve-out already used throughout this
# codebase, not magic numbers. A generated single file is not expected
# to exceed these; a future step can make either configurable once a
# real need to tune them arises.
_MAX_OUTPUT_TOKENS = 4096
_WRITE_TIMEOUT_SECONDS = 10.0
_WRITE_MAX_OUTPUT_BYTES = 65536

_WORKSPACE_PREFIX = "aios-build-agent-"

_REQUIRED_INVOCATION_FIELDS = ("promptId", "promptVersion", "modelAlias")

# The write-file script executed inside the sandbox — portable
# (pathlib/sys.stdin only, no shell), and confined to writing exactly
# the one path it is given, relative to its own cwd (the sandbox's
# working_directory). Creates parent directories for a nested path
# (e.g. "src/app.py") the same way any normal file write would.
_WRITE_FILE_SCRIPT = (
    "import pathlib, sys\n"
    "target = pathlib.Path(sys.argv[1])\n"
    "target.parent.mkdir(parents=True, exist_ok=True)\n"
    "target.write_bytes(sys.stdin.buffer.read())\n"
)

# See this module's own docstring's "fixed, explicit text format"
# section for why this is not JSON. DOTALL so `.` matches newlines
# inside the captured file content.
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


class BuildInstructionError(Exception):
    """Either this entrypoint's own invocation contract was violated
    (called before :meth:`bind_pack_context`, or missing a required
    ``promptId``/``promptVersion``/``modelAlias`` field), or the model's
    completion could not be turned into a safe file write — it did not
    follow the documented ``FILE_PATH``/``FILE_CONTENT_BEGIN``/
    ``FILE_CONTENT_END`` format, or its declared path does not resolve
    inside the sandbox working directory. Raised clearly, before any
    sandbox call is attempted — never a bare regex-miss or path
    exception."""


class BuildInstructionInput(BaseModel):
    """Documents this agent's Agent Contract "Required Inputs"
    (capability_pack_contract.md). **Not yet validated at runtime** —
    see :mod:`ai_os_pack_software_engineering.agents.architecture`'s
    own ``ArchitectureProposalInput`` for why (the identical, still
    unchanged, "no per-step input-mapping mechanism exists" scope).
    ``instruction`` reaches this agent today via the Context Manager's
    own assembled ``context`` prompt variable, the one real channel
    this codebase's ``AgentStepExecutor`` establishes — it may be the
    Architecture Agent's own proposal, or a simpler direct instruction;
    either is free text from this agent's own point of view.
    """

    instruction: str = Field(
        ..., description="A design proposal or direct instruction describing one file to produce."
    )


class BuildAgentOutput(BaseModel):
    """Documents this agent's Agent Contract "Produced Outputs." Mirrors
    the real fields :meth:`BuildAgentEntrypoint.execute` returns —
    ``instruction`` is the model's own raw completion text, kept for
    traceability ("content traceable back to the LLM's instruction"),
    not re-derived from the parsed path/content. ``workingDirectory`` is
    included because, absent a real per-workflow workspace (still Stage
    C/unbuilt — see this module's own docstring), each agent instance's
    directory is private and otherwise undiscoverable — a future Test
    Agent verifying what this agent wrote needs both fields together,
    not ``filePath`` alone.
    """

    working_directory: str = Field(..., alias="workingDirectory")
    file_path: str = Field(..., alias="filePath")
    written: bool
    exit_code: int | None = Field(..., alias="exitCode")
    stdout: str
    stderr: str
    instruction: str

    model_config = {"populate_by_name": True}


def _resolve_safe_relative_path(working_directory: Path, raw_path: str) -> Path:
    """Resolves ``raw_path`` (the model's own declared ``FILE_PATH``)
    against ``working_directory`` and returns a verified-safe relative
    path — or raises :class:`BuildInstructionError`. See this module's
    own docstring for why containment is checked by resolving and
    comparing, not by a syntactic ``is_absolute()`` check alone."""
    stripped = raw_path.strip()
    if not stripped:
        raise BuildInstructionError("the model's FILE_PATH must not be blank")

    resolved_root = working_directory.resolve()
    resolved_target = (working_directory / stripped).resolve()
    if not resolved_target.is_relative_to(resolved_root):
        raise BuildInstructionError(
            f"FILE_PATH {raw_path!r} resolves outside the sandbox working directory"
        )
    return resolved_target.relative_to(resolved_root)


def _parse_build_instruction(completion_text: str) -> tuple[str, str]:
    """Extracts ``(raw_path, content)`` from a completion following this
    module's own documented format. Raises :class:`BuildInstructionError`
    with the completion's own text included, so a failure is
    diagnosable rather than a bare "no match" ever reaching a caller."""
    match = _INSTRUCTION_PATTERN.search(completion_text)
    if match is None:
        raise BuildInstructionError(
            "the model's completion did not follow the documented FILE_PATH/"
            f"FILE_CONTENT_BEGIN/FILE_CONTENT_END format:\n{completion_text}"
        )
    return match.group("path"), match.group("content")


def _build_variables(inputs: dict[str, Any]) -> dict[str, Any]:
    """Mirrors :meth:`~ai_os_kernel.workflow_engine.prompted_agent.
    PromptedAgent._build_variables` exactly, duck-typed rather than
    ``isinstance``-checked against ``AssembledContext`` — see
    ``requirements_analyst.py``'s own docstring and
    ``platform_sdk_v1_scope.md`` §6k for why."""
    variables = dict(inputs.get("variables") or {})
    context = inputs.get("context")
    items = getattr(context, "items", None)
    if items and "context" not in variables:
        variables["context"] = "\n\n".join(item.content for item in items)
    return variables


class BuildAgentEntrypoint:
    """The manifest's own ``agents[].entrypoint`` for the Build Agent —
    zero-argument-constructible. See this module's own docstring for
    why it still keeps a lock (guarding only lazy working-directory
    creation, not any LLM composition).

    ``working_directory`` is an optional constructor override — always
    its default (``None``) in production (``EntrypointLoader`` only
    ever calls ``cls()``), and how a test substitutes a known temporary
    directory. This does not weaken the zero-arg boundary: the
    parameter is optional and defaulted, so ``cls()`` still succeeds
    exactly as ``EntrypointLoader`` requires. There is no
    ``python_command`` override any more (step 12a) — the real
    interpreter command is now resolved by ``ToolInvokerAdapter`` itself
    from :data:`~ai_os_sdk.contracts.tool_invoker.PLATFORM_PYTHON_INTERPRETER`,
    never guessed here.
    """

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
            raise BuildInstructionError(
                "BuildAgentEntrypoint.execute() called before bind_pack_context() bound a "
                "PackContext granting both the llm:invoke and sandbox:execute permissions "
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
            raise BuildInstructionError(
                "BuildAgentEntrypoint requires 'promptId', 'promptVersion', and 'modelAlias' "
                f"in its inputs — missing: {', '.join(missing)}"
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
        raw_path, content = _parse_build_instruction(instruction_text)
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
        }

    async def _ensure_working_directory(self) -> Path:
        async with self._directory_lock:
            if self._working_directory is None:
                self._working_directory = await asyncio.to_thread(
                    lambda: Path(tempfile.mkdtemp(prefix=_WORKSPACE_PREFIX))
                )
        return self._working_directory
