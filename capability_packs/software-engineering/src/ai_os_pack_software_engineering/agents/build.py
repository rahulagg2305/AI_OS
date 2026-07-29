"""The Build Agent — agent_architecture.md's "Agent Categories (Initial
Target)" #4/#5 (Backend/Frontend Development), reduced to the smallest
real slice this step approves: given a design/instruction, produce
*one* concrete file and genuinely write it — the first real connection
in this codebase between an LLM-produced instruction and sandboxed
execution. No Test/Documentation Agent, no automatic multi-step
Architecture -> Build pipeline, no ``DockerSandbox`` backend — exactly
this step's own approved scope.

**Composes two already-real pieces; invents neither.** This agent's
``execute()`` does two things, in order: (1) render this agent's own
prompt and complete it against a real LLM, by delegating to a real,
internally-built :class:`~ai_os_kernel.workflow_engine.prompted_agent.
PromptedAgent` — identical composition to
:mod:`ai_os_pack_software_engineering.agents.architecture`'s own
``_build_real_service()``, not a second, divergent way to assemble the
same pieces; (2) parse that completion's text into a file path and
content, then genuinely write it through a
:class:`~ai_os_kernel.workflow_engine.sandboxed_tool.SandboxedCommandTool`
— reusing that Tool exactly as this step's own approved framing names
it ("through a real SandboxedCommandTool"), not a parallel write
mechanism.

**Zero-argument-constructible, lazily self-composing — the identical
``ArchitectureAgentEntrypoint`` pattern, reused, not reinvented.** See
that module's own docstring for the full reasoning behind why
``PromptedAgent`` cannot itself be the zero-arg entrypoint
(:class:`~ai_os_kernel.workflow_engine.entrypoint_loader.EntrypointLoader`
always calls ``cls()``) and why deferring real async composition to the
first :meth:`execute` call, lock-guarded, is the resolution. This agent
additionally defers creating its own sandbox working directory the
same way, for the same reason: creating a directory is I/O, and
``__init__`` must stay synchronous and free of it.

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
module's own Python code touching the filesystem directly — the
constraint this step's own approved framing states explicitly ("no
direct/unsandboxed file writes from agent code").** File content is
delivered to a small, fixed write-file script via the Sandbox
Executor's own ``stdin`` parameter (a small, additive extension made
this step — see :mod:`ai_os_kernel.sandbox.executor`'s own docstring)
rather than as a command-line argument, avoiding both shell-quoting
risk and argv length limits for what may be a full source file. The
script itself never touches anything outside ``working_directory``
(POSIX/Windows-portable, uses only ``pathlib``/``sys.stdin``, no shell).

**The model's own declared file path is independently validated by
this module before being trusted, not merely passed through.**
:class:`~ai_os_kernel.sandbox.executor.LocalSubprocessSandbox` itself
provides no filesystem containment (its own ``guarantees`` say so
honestly) — a path like ``../../etc/passwd`` would otherwise reach the
write script unchanged. :func:`_resolve_safe_relative_path` resolves
the model's path against the working directory and rejects anything
that does not remain inside it (absolute paths, ``..`` escapes, and —
on Windows specifically — a root-anchored-but-driveless path like
``/etc/passwd``, which naive ``Path.is_absolute()``-only checks miss,
since joining an anchored path onto an existing one discards the
existing path's own tail). This is the identical canonical-path-
resolution discipline security_architecture.md §5.2 already mandates
for Tier 2 operations, applied here defensively for a Tier 1 one, since
the sandbox itself cannot be relied on to enforce it.

**No per-workflow workspace exists yet (security_architecture.md §5.3
— still Stage C, unbuilt).** Absent an explicit ``working_directory``,
this agent creates and reuses one private temporary directory of its
own — real isolation for *this agent instance*, not the documented
per-workflow isolation a real Workspace Service will eventually
provide. A future step assigning a real per-workflow workspace replaces
this default; it does not change this agent's own write path.
"""

from __future__ import annotations

import asyncio
import re
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ai_os_kernel.llm_gateway.adapters.anthropic_adapter import PROVIDER_NAME
from ai_os_kernel.llm_gateway.adapters.model_config import load_provider_config
from ai_os_kernel.llm_gateway.router import RoutingDecision, StaticRouter
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.settings import DatabaseSettings
from ai_os_kernel.prompted_completion import (
    PromptedCompletionService,
    build_anthropic_prompted_completion_service,
)
from ai_os_kernel.sandbox.default_executor import build_default_sandbox_executor
from ai_os_kernel.sandbox.executor import SandboxExecutor
from ai_os_kernel.secrets_manager.env_provider import EnvSecretProvider
from ai_os_kernel.workflow_engine.prompted_agent import PromptedAgent
from ai_os_kernel.workflow_engine.sandboxed_tool import SandboxedCommandTool

# Mirrors architecture.py's own identical constant exactly.
_API_KEY_SECRET_REFERENCE = "secret://env/llm/anthropic-api-key"  # noqa: S105 — a reference URI, not a credential

# Named, documented first-cut values — the same "placeholder safety
# limit, not yet tuned" carve-out already used throughout this
# codebase, not magic numbers. A generated single file is not expected
# to exceed these; a future step can make either configurable once a
# real need to tune them arises.
_MAX_OUTPUT_TOKENS = 4096
_WRITE_TIMEOUT_SECONDS = 10.0
_WRITE_MAX_OUTPUT_BYTES = 65536

_CONFIG_PATH = Path.cwd() / "config" / "llm.yaml"
_WORKSPACE_PREFIX = "aios-build-agent-"

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
    """The model's completion could not be turned into a safe file
    write — either it did not follow the documented ``FILE_PATH``/
    ``FILE_CONTENT_BEGIN``/``FILE_CONTENT_END`` format, or its declared
    path does not resolve inside the sandbox working directory. Raised
    clearly, before any sandbox call is attempted — never a bare
    regex-miss or path exception."""


class BuildInstructionInput(BaseModel):
    """Documents this agent's Agent Contract "Required Inputs"
    (capability_pack_contract.md). **Not yet validated at runtime** —
    see :mod:`ai_os_pack_software_engineering.agents.architecture`'s
    own ``ArchitectureProposalInput`` for why (the identical, still
    unchanged, "no per-step input-mapping mechanism exists" scope).
    ``instruction`` reaches this agent today via the Context Manager's
    own assembled ``context`` prompt variable, the one real channel
    this codebase's ``AgentStepExecutor``/``PromptedAgent`` establish —
    it may be the Architecture Agent's own proposal, or, per this
    step's own approved framing, a simpler direct instruction; either
    is free text from this agent's own point of view.
    """

    instruction: str = Field(
        ..., description="A design proposal or direct instruction describing one file to produce."
    )


class BuildAgentOutput(BaseModel):
    """Documents this agent's Agent Contract "Produced Outputs." Mirrors
    the real fields :meth:`BuildAgentEntrypoint.execute` returns —
    ``instruction`` is the model's own raw completion text, kept for
    traceability ("content traceable back to the LLM's instruction,"
    this step's own requirement), not re-derived from the parsed
    path/content. ``workingDirectory`` is included because, absent a
    real per-workflow workspace (still Stage C/unbuilt — see this
    module's own docstring), each agent instance's directory is private
    and otherwise undiscoverable — a future Test Agent verifying what
    this agent wrote needs both fields together, not ``filePath`` alone.
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


async def _build_real_service() -> PromptedCompletionService:
    """The real, production composition — identical to
    :func:`ai_os_pack_software_engineering.agents.documentation._build_real_service`
    (architecture.py's own former copy was removed in step 11's
    migration onto the Platform SDK; see that module's docstring and
    `platform_sdk_v1_scope.md` §6m/§6n). Not shared as a common helper:
    each still-unmigrated agent module owns its own copy of this small,
    already-minimal composition, the same "no shared module needed for
    a single real caller each" reasoning ADR-0004 already applies
    elsewhere in this codebase; a real second use would justify
    factoring it out, not anticipating one now.
    """
    provider_config = load_provider_config(_CONFIG_PATH)
    router = StaticRouter(
        routes={
            alias: RoutingDecision(
                provider=provider_config.providers.get(alias, PROVIDER_NAME), model_id=model_id
            )
            for alias, model_id in provider_config.model_ids.items()
        }
    )
    engine = build_engine(DatabaseSettings().database_url)
    return await build_anthropic_prompted_completion_service(
        engine=engine,
        secret_provider=EnvSecretProvider(),
        api_key_secret_reference=_API_KEY_SECRET_REFERENCE,
        router=router,
        pricing=provider_config.pricing,
    )


class BuildAgentEntrypoint:
    """The manifest's own ``agents[].entrypoint`` for the Build Agent —
    zero-argument-constructible, lazily building both a real
    ``PromptedAgent`` and (unless one is supplied) its own private
    sandbox working directory on first :meth:`execute` call. See this
    module's own docstring for the full reasoning.

    ``service_factory``/``sandbox``/``working_directory`` are optional
    constructor overrides — always their defaults in production
    (``EntrypointLoader`` only ever calls ``cls()``), and how a test
    substitutes a deterministic completion service, a fake/inspectable
    sandbox, or a known temporary directory. None of these weaken the
    zero-arg boundary: every parameter is optional and defaulted, so
    ``cls()`` still succeeds exactly as ``EntrypointLoader`` requires.
    """

    output_schema: dict[str, Any] = _OUTPUT_SCHEMA

    def __init__(
        self,
        *,
        service_factory: Callable[[], Awaitable[PromptedCompletionService]] | None = None,
        sandbox: SandboxExecutor | None = None,
        working_directory: Path | None = None,
    ) -> None:
        self._service_factory = service_factory or _build_real_service
        self.sandbox = sandbox or build_default_sandbox_executor()
        self._working_directory = working_directory
        self._agent: PromptedAgent | None = None
        self._setup_lock = asyncio.Lock()

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        agent, working_directory = await self._ensure_ready()

        completion_outputs = await agent.execute(inputs)
        instruction_text = completion_outputs["content"]
        raw_path, content = _parse_build_instruction(instruction_text)
        relative_path = await asyncio.to_thread(
            _resolve_safe_relative_path, working_directory, raw_path
        )

        writer = SandboxedCommandTool(
            self.sandbox,
            command=[*self.sandbox.python_command, "-c", _WRITE_FILE_SCRIPT, str(relative_path)],
            working_directory=working_directory,
            timeout_seconds=_WRITE_TIMEOUT_SECONDS,
            max_output_bytes=_WRITE_MAX_OUTPUT_BYTES,
            stdin=content.encode("utf-8"),
        )
        write_outputs = await writer.execute({})

        return {
            "workingDirectory": str(working_directory),
            "filePath": str(relative_path),
            "written": write_outputs["exitCode"] == 0 and not write_outputs["timedOut"],
            "exitCode": write_outputs["exitCode"],
            "stdout": write_outputs["stdout"],
            "stderr": write_outputs["stderr"],
            "instruction": instruction_text,
        }

    async def _ensure_ready(self) -> tuple[PromptedAgent, Path]:
        async with self._setup_lock:
            if self._agent is None:
                service = await self._service_factory()
                self._agent = PromptedAgent(service=service, max_output_tokens=_MAX_OUTPUT_TOKENS)
            if self._working_directory is None:
                self._working_directory = await asyncio.to_thread(
                    lambda: Path(tempfile.mkdtemp(prefix=_WORKSPACE_PREFIX))
                )
        return self._agent, self._working_directory
