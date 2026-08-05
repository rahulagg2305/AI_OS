"""The Documentation Agent — agent_architecture.md's "Agent Categories
(Initial Target)" #12 (Documentation), reduced to the smallest real
slice this step approves: given a Build Agent result and its Test
Agent outcome, genuinely call an LLM to produce a Markdown record and
write it through the sandbox — the pipeline's fourth and, for this
phase, final named role.

**Migrated onto the real Platform SDK (``platform_sdk_v1_scope.md``
step 13) — the fifth and final agent migration.** This entrypoint now
implements :class:`~ai_os_sdk.contracts.Agent` and
:class:`~ai_os_sdk.contracts.entrypoint_context.PackContextReceiver`
only. It imports nothing from ``ai_os_kernel`` at all. Its LLM call is
the identical render-then-complete replication
``requirements_analyst.py``/``architecture.py``/``build.py`` already
use; its write now calls
``self._context.tools.invoke(PLATFORM_SANDBOX_RUN_COMMAND, ...)`` with
:data:`~ai_os_sdk.contracts.tool_invoker.PLATFORM_PYTHON_INTERPRETER`
as the interpreter token — the step 12a fix, used here from the start
rather than repeating step 12's own now-closed regression (a
constructor-time ``python_command`` default this module never needed to
invent in the first place).

**No lock at all — a real, further data point on the lock-obsolescence
finding, not a new one.** Unlike ``BuildAgentEntrypoint`` (which kept a
narrower lock guarding lazy working-directory creation, a concern
unrelated to LLM composition), this agent lazily builds and creates
nothing: it reuses the caller-supplied ``workingDirectory`` directly
(see below) and, post-migration, has no ``PromptedAgent``/service to
lazily construct either. There is genuinely nothing left for a lock to
guard, confirming steps 10/11's own finding generalizes fully to the
one agent in this pack with the least internal state.

**No completion-text parsing at all — simpler than Build, and
deliberately so.** This agent's own target path is never the model's to
choose — it is derived deterministically from the Build Agent's own
``filePath`` (``"<filePath>.md"``, written alongside the source file,
inside the same ``workingDirectory``). The model's entire completion is
therefore used verbatim as the documentation file's content.

**Reuses the caller-supplied ``workingDirectory`` directly — like the
Test Agent, unlike the Build Agent.** This agent writes *into* the same
directory the Build Agent's own file already lives in (so the resulting
``<filePath>.md`` sits beside it), not a private temporary directory of
its own.

**The same real, discovered need to duck-type the assembled context as
every other migrated agent in this pack.** :func:`_extract_payload`
recovers this agent's own six required fields directly from ``inputs``
or, when absent, from JSON-encoded ``context`` — the identical
resolution :mod:`~ai_os_pack_software_engineering.agents.verification`
already established for its own three-field payload. The real object
``AgentStepExecutor`` sends is still Kernel-typed
(``ai_os_kernel.context_manager.models.AssembledContext``), a different
class from the SDK's own boundary model even after step 7's narrowing —
resolved by duck-typing (``getattr(context, "items", None)``) instead of
an ``isinstance`` check that would always be ``False`` against the real
object, exactly as ``requirements_analyst.py``/``verification.py``
already document.

**The identical, already-recorded ``evaluation.llm_calls`` capability
loss applies here too — the fourth and final occurrence, closing out
the full set of LLM-calling agents this pack has.** No new finding —
see ``requirements_analyst.py``'s own docstring for the full reasoning.

**``filePath`` is independently checked before any sandbox call or LLM
call, the same defensive discipline Test's own ``_resolve_existing_file``
and Build's own ``_resolve_safe_relative_path`` already establish —
both duplicated here, not imported from either.** Checking before the
LLM call specifically also avoids spending a real model call on an
input this agent cannot safely act on regardless of what the model
returns.
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

# Named, documented first-cut values — the same "placeholder safety
# limit, not yet tuned" carve-out already used throughout this
# codebase. A concise Markdown record of one file is not expected to
# exceed these; a future step can make either configurable once a real
# need to tune them arises.
_MAX_OUTPUT_TOKENS = 2048
_WRITE_TIMEOUT_SECONDS = 10.0
_WRITE_MAX_OUTPUT_BYTES = 65536

_REQUIRED_INVOCATION_FIELDS = ("promptId", "promptVersion", "modelAlias")

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
    """Either this entrypoint's own invocation contract was violated
    (called before :meth:`bind_pack_context`, or missing a required
    ``promptId``/``promptVersion``/``modelAlias`` field), or this
    agent's input could not be turned into a safe documentation write —
    a required field was missing or malformed, or ``filePath`` does not
    resolve to a real, existing file inside ``workingDirectory``. Raised
    clearly, before any LLM or sandbox call is attempted."""


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
    exist. Duck-typed rather than ``isinstance(context, AssembledContext)``
    — see this module's own docstring for why: the real object the
    Workflow Engine sends here is still Kernel-typed, a different
    Python class from the SDK's own boundary model, so a nominal check
    would always be ``False`` against it. Raises
    :class:`DocumentationInstructionError` with a clear reason if
    neither yields a complete, well-typed payload."""
    if all(field in inputs for field in _REQUIRED_FIELDS):
        payload = {field: inputs[field] for field in _REQUIRED_FIELDS}
    else:
        context = inputs.get("context")
        items = getattr(context, "items", None)
        if not items:
            raise DocumentationInstructionError(
                "DocumentationAgentEntrypoint requires 'workingDirectory', 'filePath', "
                "'instruction', 'passed', 'exitCode', and 'output' — either directly in "
                "inputs, or as a JSON object in the assembled context"
            )
        raw = "\n\n".join(item.content for item in items)
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


class DocumentationAgentEntrypoint:
    """The manifest's own ``agents[].entrypoint`` for the Documentation
    Agent — zero-argument-constructible. See this module's own
    docstring for why it needs no lock at all: unlike every other
    LLM-calling agent in this pack, it lazily builds or creates nothing.
    """

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
            raise DocumentationInstructionError(
                "DocumentationAgentEntrypoint.execute() called before bind_pack_context() "
                "bound a PackContext granting both the llm:invoke and sandbox:execute "
                "permissions (context.llm/context.prompts/context.tools) — a real caller "
                "must inject one before first use"
            )

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
            raise DocumentationInstructionError(
                "DocumentationAgentEntrypoint requires 'promptId', 'promptVersion', and "
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
                    str(doc_relative_path),
                ],
                "working_directory": str(working_directory),
                "timeout_seconds": _WRITE_TIMEOUT_SECONDS,
                "max_output_bytes": _WRITE_MAX_OUTPUT_BYTES,
                "stdin": content,
            },
        )

        return {
            "workingDirectory": str(working_directory),
            "documentationPath": str(doc_relative_path),
            "written": result.exit_code == 0 and not result.timed_out,
            "exitCode": result.exit_code,
            "content": content,
        }
