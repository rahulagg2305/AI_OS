"""The Test Agent — agent_architecture.md's "Agent Categories (Initial
Target)" #10 (QA / Test), reduced to the smallest real slice this step
approves: given a file the Build Agent wrote and the command that runs
it, genuinely execute that command inside the sandbox and report the
real outcome. No Documentation Agent, no automatic Build -> Test
pipeline, no test-framework detection — exactly this step's own
approved scope.

**Deliberately not ``PromptedAgent``-backed — this agent makes no LLM
call at all, and that is the point, not an oversight.** This step's own
approved framing states the constraint plainly: "pass/fail must come
from real sandboxed execution outcome, never from LLM judgment."
Architecture and Build both genuinely need a completion (a design, a
file's content); verifying whether an already-written file's own run
command exits zero needs no model call whatsoever — asking one anyway
would manufacture a dependency (and a cost, and a place for the "LLM's
opinion" this step explicitly forbids to creep back in) this agent's
own job has no use for. ``TestAgentEntrypoint`` is therefore simpler
than ``ArchitectureAgentEntrypoint``/``BuildAgentEntrypoint``: no
``service_factory``, no lazily-built ``PromptedAgent``, no lock —
zero-argument construction here is not merely satisfied, it is trivial,
since there is nothing this class needs to build lazily at all. It
still follows the same entrypoint shape those two establish
(zero-arg-constructible, optional constructor overrides for tests) for
consistency, not because laziness applies here too.

**Resolved (2026-07-28) — the manifest schema originally required
``modelAlias`` on every agent, including this one; it no longer does.**
``platform_sdk/schemas/manifest.schema.json``'s ``agents[]`` entry
originally listed ``modelAlias`` as unconditionally required, with no
"agents that call no model" escape hatch, forcing this agent's own
manifest entry to declare a syntactically-valid but genuinely-unused
value purely to pass validation. A documentation-reconciliation step
fixed the schema itself (a conditional `if`/`then` requiring
``modelAlias`` only when an agent's own ``permissions`` declare
``llm:invoke``) — this agent's manifest entry no longer declares
``modelAlias`` at all, since it genuinely makes no LLM call.
``permissions`` has always genuinely reflected reality: ``sandbox:execute``
only, no ``llm:invoke``.

**Input/output contract, kept minimal and structured, per this step's
own explicit requirement.** In: ``workingDirectory`` (the Build Agent's
own working directory — this agent runs *inside* it, not a directory
of its own choosing), ``filePath`` (relative to it, expected to already
exist — this agent does not write anything), ``runCommand`` (the exact
argv to execute, e.g. ``["python", "hello.py"]`` — no shell, no
test-framework auto-discovery; the caller decides how the file is run).
Out: ``passed`` (``exitCode == 0`` and not timed out — never an LLM's
opinion), ``exitCode``, ``output`` (stdout then stderr, concatenated).

**A genuine, discovered gap in how a real ``WorkflowStep`` can hand
this agent that structured input at all — reported and resolved, not
silently worked around.** :class:`~ai_os_kernel.workflow_engine.
step_executor.AgentStepExecutor`'s own ``_invocation_inputs()`` only
ever populates ``promptId``/``promptVersion``/``modelAlias`` (from a
step's own declared fields) and ``context`` (from the Context Manager)
— there is no per-step mechanism to hand an agent arbitrary named
fields like ``workingDirectory``. Architecture and Build both sidestep
this because their real data already flows through prompt rendering;
this agent has no prompt to render. Resolution: :func:`_extract_payload`
accepts the three fields directly in ``inputs`` (the primary,
documented contract — what a test, or a future real per-step input
mechanism, would supply) **or**, when absent, as a JSON object inside
the Context Manager's own assembled ``context`` (flattened the same way
:meth:`~ai_os_kernel.workflow_engine.prompted_agent.PromptedAgent.
_build_variables` already flattens it) — the identical "``context`` is
the one real channel for external per-step data" principle already
established for this pack's other two agents, applied here with a JSON
payload instead of free text, since this agent's payload is structured.
This is not a second, invented input-mapping mechanism; it is the one
that already exists, used the only way it can carry more than one
named value.

**``filePath`` is independently checked before any sandbox call, the
same defensive discipline ``build.py``'s own ``_resolve_safe_relative_path``
already established — duplicated here, not imported from it.** Both
functions are small, and each module already owns its own,
independently-testable code (the identical "no shared module needed
for a single real caller each" reasoning ``build.py``'s own
``_build_real_service`` docstring already applies to a different pair
of duplicated functions in this same pack). ``filePath`` here is, in
practice, less adversarial than Build's own LLM-controlled one (it
names a file *this pack's own* Build Agent already wrote inside its own
validated working directory) — but checking again costs little and
assumes nothing about who actually calls this agent.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ai_os_kernel.context_manager.models import AssembledContext
from ai_os_kernel.sandbox.default_executor import build_default_sandbox_executor
from ai_os_kernel.sandbox.executor import SandboxExecutor
from ai_os_kernel.workflow_engine.sandboxed_tool import SandboxedCommandTool

# Named, documented first-cut values — the same "placeholder safety
# limit, not yet tuned" carve-out already used throughout this
# codebase. Running one already-written file is not expected to
# exceed these; a future step can make either configurable once a
# real need to tune them arises.
_RUN_TIMEOUT_SECONDS = 10.0
_RUN_MAX_OUTPUT_BYTES = 65536

_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "passed": {"type": "boolean"},
        "exitCode": {"type": ["integer", "null"]},
        "output": {"type": "string"},
    },
    "required": ["passed", "exitCode", "output"],
    "additionalProperties": False,
}


class TestInstructionError(Exception):
    """This agent's input could not be turned into a safe, real run —
    a required field was missing or malformed, or ``filePath`` does not
    resolve to a real, existing file inside ``workingDirectory``.
    Raised clearly, before any sandbox call is attempted."""


class TestAgentInput(BaseModel):
    """Documents this agent's Agent Contract "Required Inputs"
    (capability_pack_contract.md). **Not yet validated at runtime** —
    the identical, still unchanged "no per-step input-mapping mechanism
    exists" scope every agent in this pack already documents. Field
    names deliberately match ``BuildAgentOutput``'s own
    ``workingDirectory``/``filePath`` — this agent is meant to consume
    a Build Agent result directly, even though no automatic pipeline
    wires that hand-off yet (a distinct, later step).
    """

    working_directory: str = Field(..., alias="workingDirectory")
    file_path: str = Field(..., alias="filePath")
    run_command: list[str] = Field(
        ..., alias="runCommand", description="The exact argv to execute, e.g. ['python', 'a.py']."
    )

    model_config = {"populate_by_name": True}


class TestAgentOutput(BaseModel):
    """Documents this agent's Agent Contract "Produced Outputs." Mirrors
    the real fields :meth:`TestAgentEntrypoint.execute` returns —
    ``passed`` is derived only from ``exitCode``/timeout, never from
    any judgment about ``output``'s own content.
    """

    passed: bool
    exit_code: int | None = Field(..., alias="exitCode")
    output: str

    model_config = {"populate_by_name": True}


def _resolve_existing_file(working_directory: Path, raw_path: str) -> Path:
    """Resolves ``raw_path`` against ``working_directory``, verifies it
    remains inside it (containment checked by resolving and comparing
    — see :mod:`ai_os_pack_software_engineering.agents.build`'s own
    docstring for why a syntactic ``is_absolute()``-only check is not
    enough), and verifies the resulting file genuinely exists. Raises
    :class:`TestInstructionError` otherwise."""
    stripped = raw_path.strip()
    if not stripped:
        raise TestInstructionError("filePath must not be blank")

    resolved_root = working_directory.resolve()
    resolved_target = (working_directory / stripped).resolve()
    if not resolved_target.is_relative_to(resolved_root):
        raise TestInstructionError(f"filePath {raw_path!r} resolves outside {working_directory}")
    if not resolved_target.is_file():
        raise TestInstructionError(
            f"filePath {raw_path!r} does not exist inside {working_directory}"
        )
    return resolved_target


_REQUIRED_FIELDS = ("workingDirectory", "filePath", "runCommand")


def _extract_payload(inputs: dict[str, Any]) -> tuple[str, str, list[str]]:
    """Returns ``(workingDirectory, filePath, runCommand)`` from
    ``inputs`` directly, or, when absent, parsed as JSON from the
    Context Manager's own assembled ``context`` — see this module's own
    docstring's "genuine, discovered gap" section for why both paths
    exist. Raises :class:`TestInstructionError` with a clear reason if
    neither yields a complete, well-typed payload."""
    if all(field in inputs for field in _REQUIRED_FIELDS):
        payload = {field: inputs[field] for field in _REQUIRED_FIELDS}
    else:
        context = inputs.get("context")
        if not isinstance(context, AssembledContext) or not context.items:
            raise TestInstructionError(
                "TestAgentEntrypoint requires 'workingDirectory', 'filePath', and "
                "'runCommand' — either directly in inputs, or as a JSON object in "
                "the assembled context"
            )
        raw = "\n\n".join(item.content for item in context.items)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TestInstructionError(
                f"the assembled context is not a valid JSON object: {exc}"
            ) from exc
        if not isinstance(payload, dict) or not all(field in payload for field in _REQUIRED_FIELDS):
            raise TestInstructionError(
                "the assembled context's JSON object is missing 'workingDirectory', "
                "'filePath', or 'runCommand'"
            )

    working_directory, file_path, run_command = (payload[field] for field in _REQUIRED_FIELDS)
    if not isinstance(working_directory, str) or not isinstance(file_path, str):
        raise TestInstructionError("workingDirectory and filePath must both be strings")
    if not isinstance(run_command, list) or not all(isinstance(x, str) for x in run_command):
        raise TestInstructionError("runCommand must be a list of strings")
    return working_directory, file_path, run_command


class TestAgentEntrypoint:
    """The manifest's own ``agents[].entrypoint`` for the Test Agent —
    zero-argument-constructible like every other agent in this pack,
    though trivially so here: nothing is built lazily, since this agent
    needs no LLM composition at all. See this module's own docstring
    for the full reasoning.

    ``sandbox``/``timeout_seconds``/``max_output_bytes`` are optional
    constructor overrides — always their defaults in production
    (``EntrypointLoader`` only ever calls ``cls()``), and how a test
    substitutes a fake/inspectable sandbox or tighter limits.
    """

    output_schema: dict[str, Any] = _OUTPUT_SCHEMA

    def __init__(
        self,
        *,
        sandbox: SandboxExecutor | None = None,
        timeout_seconds: float = _RUN_TIMEOUT_SECONDS,
        max_output_bytes: int = _RUN_MAX_OUTPUT_BYTES,
    ) -> None:
        self.sandbox = sandbox or build_default_sandbox_executor()
        self._timeout_seconds = timeout_seconds
        self._max_output_bytes = max_output_bytes

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        working_directory_raw, file_path_raw, run_command = _extract_payload(inputs)

        working_directory = Path(working_directory_raw)
        # Both checks touch the filesystem — run off the event loop
        # thread (ASYNC240), the same fix already applied throughout
        # this codebase's own sandbox/agent modules, not a suppression.
        if not await asyncio.to_thread(working_directory.is_dir):
            raise TestInstructionError(
                f"workingDirectory {working_directory_raw!r} does not exist or is not a directory"
            )
        await asyncio.to_thread(_resolve_existing_file, working_directory, file_path_raw)

        runner = SandboxedCommandTool(
            self.sandbox,
            command=run_command,
            working_directory=working_directory,
            timeout_seconds=self._timeout_seconds,
            max_output_bytes=self._max_output_bytes,
        )
        run_outputs = await runner.execute({})

        return {
            "passed": run_outputs["exitCode"] == 0 and not run_outputs["timedOut"],
            "exitCode": run_outputs["exitCode"],
            "output": run_outputs["stdout"] + run_outputs["stderr"],
        }
