"""The Documentation Agent — agent_architecture.md's "Agent Categories
(Initial Target)" #12 (Documentation), reduced to the smallest real
slice this step approves: given a Build Agent result and its Test
Agent outcome, genuinely call an LLM to produce a Markdown record and
write it through the sandbox — the pipeline's fourth and, for this
phase, final named role. No automatic Architecture -> Build -> Test ->
Documentation pipeline, no new persistence/templating system — exactly
this step's own approved scope.

**``PromptedAgent``-backed, like Architecture/Build — unlike the Test
Agent, this role genuinely needs a model call.** Test's own docstring
explains why *it* makes none ("verifying an exit code needs no model
call"); describing what was built, why, and how it was verified is
exactly the kind of free-text synthesis an LLM is the right tool for.
This agent therefore composes a real, internally-built
:class:`~ai_os_kernel.workflow_engine.prompted_agent.PromptedAgent` on
first use — the identical lazy-build/zero-arg pattern
:class:`~ai_os_pack_software_engineering.agents.architecture.
ArchitectureAgentEntrypoint`/:class:`~ai_os_pack_software_engineering.
agents.build.BuildAgentEntrypoint` already establish, reused, not
reinvented.

**Combines two already-real pieces this pack already owns; invents
neither.** The write path is exactly Build's own: content delivered to
the identical portable, no-shell write script via the Sandbox
Executor's own ``stdin`` parameter, through a real
:class:`~ai_os_kernel.workflow_engine.sandboxed_tool.SandboxedCommandTool`
— reusing that Tool exactly as this step's own approved framing names
it ("reuse SandboxedCommandTool/stdin delivery exactly as the Build
Agent already established, do not invent a second file-write path").

**No completion-text parsing at all — simpler than Build, and
deliberately so.** Build's own completion must be split into a file
path (chosen by the model) and content; this agent's own target path is
never the model's to choose — it is derived deterministically from the
Build Agent's own ``filePath`` (``"<filePath>.md"``, written alongside
the source file, inside the same ``workingDirectory``). The model's
entire completion is therefore used verbatim as the documentation
file's content — this agent's own prompt (``prompts/
documentation_record_artifact.md``) instructs the model to respond with
the Markdown document and nothing else, the same "exactly this format,
nothing else" discipline Build's own prompt already establishes, just
without any delimiters to parse back out.

**Reuses the caller-supplied ``workingDirectory`` directly — like the
Test Agent, unlike the Build Agent.** This agent writes *into* the same
directory the Build Agent's own file already lives in (so the resulting
``<filePath>.md`` sits beside it), not a private temporary directory of
its own; there is nothing for this agent to lazily create. Absent a
real per-workflow workspace (security_architecture.md §5.3, still Stage
C — the identical gap Build/Test's own docstrings already record),
that shared directory is still whatever the Build Agent itself created.

**A genuine, discovered need to extend the Test Agent's own
``context``-JSON dual-path resolution — not a new mechanism, a second
real use of the one this pack already built.**
:mod:`~ai_os_pack_software_engineering.agents.verification`'s own
docstring already documents why :class:`~ai_os_kernel.workflow_engine.
step_executor.AgentStepExecutor` has no per-step mechanism for
arbitrary structured fields, and resolved it for a *non-prompted* agent
by JSON-encoding the payload inside the Context Manager's own
``context`` channel. This agent needs the identical resolution for the
identical reason (its own real input — a Build result plus a Test
outcome — is six structured fields, not the one free-text string
Build/Architecture's own inputs are), but for a *prompted* agent: once
:func:`_extract_payload` recovers the six fields (directly from
``inputs``, or from JSON-encoded ``context``, mirroring
:mod:`~ai_os_pack_software_engineering.agents.verification` exactly),
they are placed into a ``variables`` dict this module builds itself and
forwards, alongside the caller's own ``promptId``/``promptVersion``/
``modelAlias``/trace fields, into the internal ``PromptedAgent.execute()``
call — :meth:`~ai_os_kernel.workflow_engine.prompted_agent.PromptedAgent.
_build_variables` already reads ``inputs.get("variables")`` as a direct,
unmodified passthrough (its own docstring: "No new input-mapping
system"), so this is that existing seam, used, not extended. The
original ``context`` key is popped before forwarding, since this
module has already consumed it — leaving it in would otherwise also
have ``PromptedAgent`` redundantly re-flatten it into a ``context``
prompt variable this agent's own template never references.

**``filePath`` is independently checked before any sandbox call or LLM
call, the same defensive discipline Test's own ``_resolve_existing_file``
and Build's own ``_resolve_safe_relative_path`` already establish —
both duplicated here, not imported from either.** Small, already-
minimal, single-real-caller-each functions — the identical "no shared
module needed for a single real caller each" reasoning (ADR-0004)
every agent module in this pack already applies to its own copy of
``_build_real_service`` and path-safety checks. Checking before the LLM
call specifically also avoids spending a real model call on an input
this agent cannot safely act on regardless of what the model returns.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, NamedTuple

from pydantic import BaseModel, Field

from ai_os_kernel.context_manager.models import AssembledContext
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

# Mirrors architecture.py's/build.py's own identical constant exactly.
_API_KEY_SECRET_REFERENCE = "secret://env/llm/anthropic-api-key"  # noqa: S105 — a reference URI, not a credential

# Named, documented first-cut values — the same "placeholder safety
# limit, not yet tuned" carve-out already used throughout this
# codebase. A concise Markdown record of one file is not expected to
# exceed these; a future step can make either configurable once a real
# need to tune them arises.
_MAX_OUTPUT_TOKENS = 2048
_WRITE_TIMEOUT_SECONDS = 10.0
_WRITE_MAX_OUTPUT_BYTES = 65536

_CONFIG_PATH = Path.cwd() / "config" / "llm.yaml"

# Identical to build.py's own script — duplicated, not imported, per
# this module's own docstring. Portable (pathlib/sys.stdin only, no
# shell), confined to writing exactly the one path it is given,
# relative to its own cwd (the sandbox's working_directory).
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
        "documentationPath": {"type": "string"},
        "written": {"type": "boolean"},
        "exitCode": {"type": ["integer", "null"]},
        "content": {"type": "string"},
    },
    "required": ["workingDirectory", "documentationPath", "written", "exitCode", "content"],
    "additionalProperties": False,
}


class DocumentationInstructionError(Exception):
    """This agent's input could not be turned into a safe documentation
    write — a required field was missing or malformed, or ``filePath``
    does not resolve to a real, existing file inside ``workingDirectory``.
    Raised clearly, before any LLM or sandbox call is attempted."""


class DocumentationAgentInput(BaseModel):
    """Documents this agent's Agent Contract "Required Inputs"
    (capability_pack_contract.md). **Not yet validated at runtime** —
    the identical, still unchanged "no per-step input-mapping mechanism
    exists" scope every agent in this pack already documents. Field
    names deliberately match ``BuildAgentOutput``'s own
    ``workingDirectory``/``filePath`` and ``TestAgentOutput``'s own
    ``passed``/``exitCode``/``output`` — this agent is meant to consume
    both agents' real results directly, even though no automatic
    pipeline wires that hand-off yet (a distinct, later step).
    """

    working_directory: str = Field(..., alias="workingDirectory")
    file_path: str = Field(..., alias="filePath")
    instruction: str = Field(
        ..., description="The original design/instruction the Build Agent implemented."
    )
    passed: bool = Field(..., description="The Test Agent's own pass/fail outcome for filePath.")
    exit_code: int | None = Field(..., alias="exitCode")
    output: str = Field(..., description="The Test Agent's own captured stdout+stderr.")

    model_config = {"populate_by_name": True}


class DocumentationAgentOutput(BaseModel):
    """Documents this agent's Agent Contract "Produced Outputs." Mirrors
    the real fields :meth:`DocumentationAgentEntrypoint.execute` returns
    — ``content`` is the model's own raw completion text, kept for
    traceability, identical in spirit to ``BuildAgentOutput.instruction``.
    """

    working_directory: str = Field(..., alias="workingDirectory")
    documentation_path: str = Field(..., alias="documentationPath")
    written: bool
    exit_code: int | None = Field(..., alias="exitCode")
    content: str

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
    """Returns the six real fields this agent needs from ``inputs``
    directly, or, when absent, parsed as JSON from the Context
    Manager's own assembled ``context`` — see this module's own
    docstring's "genuine, discovered need" section for why both paths
    exist (the identical resolution
    :mod:`~ai_os_pack_software_engineering.agents.verification` already
    established, reused here for a six-field payload instead of three).
    Raises :class:`DocumentationInstructionError` with a clear reason if
    neither yields a complete, well-typed payload."""
    if all(field in inputs for field in _REQUIRED_FIELDS):
        payload = {field: inputs[field] for field in _REQUIRED_FIELDS}
    else:
        context = inputs.get("context")
        if not isinstance(context, AssembledContext) or not context.items:
            raise DocumentationInstructionError(
                "DocumentationAgentEntrypoint requires 'workingDirectory', 'filePath', "
                "'instruction', 'passed', 'exitCode', and 'output' — either directly in "
                "inputs, or as a JSON object in the assembled context"
            )
        raw = "\n\n".join(item.content for item in context.items)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DocumentationInstructionError(
                f"the assembled context is not a valid JSON object: {exc}"
            ) from exc
        if not isinstance(payload, dict) or not all(field in payload for field in _REQUIRED_FIELDS):
            raise DocumentationInstructionError(
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
        raise DocumentationInstructionError("workingDirectory and filePath must both be strings")
    if not isinstance(instruction, str) or not isinstance(output, str):
        raise DocumentationInstructionError("instruction and output must both be strings")
    if not isinstance(passed, bool):
        raise DocumentationInstructionError("passed must be a boolean")
    if exit_code is not None and not isinstance(exit_code, int):
        raise DocumentationInstructionError("exitCode must be an integer or null")

    return _BuildTestPayload(working_directory, file_path, instruction, passed, exit_code, output)


def _resolve_existing_file(working_directory: Path, raw_path: str) -> Path:
    """Identical to :func:`~ai_os_pack_software_engineering.agents.
    verification._resolve_existing_file` — duplicated, not imported, per
    this module's own docstring. Resolves ``raw_path`` against
    ``working_directory``, verifies containment, and verifies the file
    genuinely exists. Raises :class:`DocumentationInstructionError`
    otherwise."""
    stripped = raw_path.strip()
    if not stripped:
        raise DocumentationInstructionError("filePath must not be blank")

    resolved_root = working_directory.resolve()
    resolved_target = (working_directory / stripped).resolve()
    if not resolved_target.is_relative_to(resolved_root):
        raise DocumentationInstructionError(
            f"filePath {raw_path!r} resolves outside {working_directory}"
        )
    if not resolved_target.is_file():
        raise DocumentationInstructionError(
            f"filePath {raw_path!r} does not exist inside {working_directory}"
        )
    return resolved_target


def _resolve_safe_relative_path(working_directory: Path, raw_path: str) -> Path:
    """Identical to :func:`~ai_os_pack_software_engineering.agents.build.
    _resolve_safe_relative_path` — duplicated, not imported, per this
    module's own docstring. Resolves ``raw_path`` (this module's own
    derived ``"<filePath>.md"``) against ``working_directory`` and
    returns a verified-safe relative path — or raises
    :class:`DocumentationInstructionError`. Does not require the target
    to already exist, unlike :func:`_resolve_existing_file` above: this
    path is about to be created, not read."""
    stripped = raw_path.strip()
    if not stripped:
        raise DocumentationInstructionError("the documentation path must not be blank")

    resolved_root = working_directory.resolve()
    resolved_target = (working_directory / stripped).resolve()
    if not resolved_target.is_relative_to(resolved_root):
        raise DocumentationInstructionError(
            f"documentation path {raw_path!r} resolves outside the sandbox working directory"
        )
    return resolved_target.relative_to(resolved_root)


async def _build_real_service() -> PromptedCompletionService:
    """The real, production composition — identical to
    :func:`ai_os_pack_software_engineering.agents.architecture._build_real_service`/
    :func:`ai_os_pack_software_engineering.agents.build._build_real_service`.
    Not shared as a common helper — see either module's own docstring
    for the ADR-0004 reasoning this module also relies on.
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


class DocumentationAgentEntrypoint:
    """The manifest's own ``agents[].entrypoint`` for the Documentation
    Agent — zero-argument-constructible, lazily building a real
    ``PromptedAgent`` on first :meth:`execute` call, the identical
    pattern ``ArchitectureAgentEntrypoint``/``BuildAgentEntrypoint``
    already establish. Unlike ``BuildAgentEntrypoint``, this agent
    creates no working directory of its own — see this module's own
    docstring for why it always reuses the caller-supplied one.

    ``service_factory``/``sandbox`` are optional constructor overrides
    — always their defaults in production (``EntrypointLoader`` only
    ever calls ``cls()``), and how a test substitutes a deterministic
    completion service or a fake/inspectable sandbox.
    """

    output_schema: dict[str, Any] = _OUTPUT_SCHEMA

    def __init__(
        self,
        *,
        service_factory: Callable[[], Awaitable[PromptedCompletionService]] | None = None,
        sandbox: SandboxExecutor | None = None,
    ) -> None:
        self._service_factory = service_factory or _build_real_service
        self.sandbox = sandbox or build_default_sandbox_executor()
        self._agent: PromptedAgent | None = None
        self._setup_lock = asyncio.Lock()

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        payload = _extract_payload(inputs)

        working_directory = Path(payload.working_directory)
        # Filesystem checks run off the event loop thread (ASYNC240),
        # the same fix already applied throughout this codebase's own
        # sandbox/agent modules, not a suppression.
        if not await asyncio.to_thread(working_directory.is_dir):
            raise DocumentationInstructionError(
                f"workingDirectory {payload.working_directory!r} does not exist or is not a "
                "directory"
            )
        await asyncio.to_thread(_resolve_existing_file, working_directory, payload.file_path)
        doc_relative_path = await asyncio.to_thread(
            _resolve_safe_relative_path, working_directory, f"{payload.file_path}.md"
        )

        agent = await self._ensure_ready()
        prompted_inputs = dict(inputs)
        prompted_inputs.pop("context", None)
        prompted_inputs["variables"] = {
            "filePath": payload.file_path,
            "instruction": payload.instruction,
            "passed": "true" if payload.passed else "false",
            "exitCode": "none" if payload.exit_code is None else str(payload.exit_code),
            "output": payload.output,
        }
        completion_outputs = await agent.execute(prompted_inputs)
        content = completion_outputs["content"]

        writer = SandboxedCommandTool(
            self.sandbox,
            command=[
                *self.sandbox.python_command,
                "-c",
                _WRITE_FILE_SCRIPT,
                str(doc_relative_path),
            ],
            working_directory=working_directory,
            timeout_seconds=_WRITE_TIMEOUT_SECONDS,
            max_output_bytes=_WRITE_MAX_OUTPUT_BYTES,
            stdin=content.encode("utf-8"),
        )
        write_outputs = await writer.execute({})

        return {
            "workingDirectory": str(working_directory),
            "documentationPath": str(doc_relative_path),
            "written": write_outputs["exitCode"] == 0 and not write_outputs["timedOut"],
            "exitCode": write_outputs["exitCode"],
            "content": content,
        }

    async def _ensure_ready(self) -> PromptedAgent:
        async with self._setup_lock:
            if self._agent is None:
                service = await self._service_factory()
                self._agent = PromptedAgent(service=service, max_output_tokens=_MAX_OUTPUT_TOKENS)
        return self._agent
