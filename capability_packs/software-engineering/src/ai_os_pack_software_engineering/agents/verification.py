"""The Test Agent — agent_architecture.md's "Agent Categories (Initial
Target)" #10 (QA / Test), reduced to the smallest real slice this step
approves: given a file the Build Agent wrote and the command that runs
it, genuinely execute that command inside the sandbox and report the
real outcome. No Documentation Agent, no automatic Build -> Test
pipeline, no test-framework detection — exactly this step's own
approved scope.

**Migrated onto the real Platform SDK (``platform_sdk_v1_scope.md``
step 9) — the first of the six migration steps, chosen first for
exactly the reason it has no LLM call and only one real Kernel
dependency (the sandbox) to replace.** This entrypoint now implements
:class:`~ai_os_sdk.contracts.Agent` and
:class:`~ai_os_sdk.contracts.entrypoint_context.PackContextReceiver`
only — it imports nothing from ``ai_os_kernel`` at all. Where it used to
construct a real :class:`~ai_os_kernel.workflow_engine.sandboxed_tool.
SandboxedCommandTool` directly over a Kernel ``SandboxExecutor``, it now
calls :meth:`~ai_os_sdk.contracts.ToolInvoker.invoke` on
``self._context.tools`` — the real
:class:`~ai_os_kernel.sdk_adapters.tool_invoker_adapter.ToolInvokerAdapter`
a caller injects via :meth:`bind_pack_context`, per the step 6b
mechanism this migration is the first real (non-test-entrypoint) user
of. See ``platform_sdk_v1_scope.md`` §6k for two real, discovered
findings from being that first real user — neither a defect in the
mechanism itself, both resolved here:

1. **The mechanism itself needed no change.** Zero-arg construction,
   then a caller-side ``bind_pack_context()`` call before first
   ``execute()``, worked exactly as step 6b's test entrypoint proved —
   the only real-world addition is that *this* entrypoint now raises a
   clear, named error (:class:`TestInstructionError`) if ``execute()``
   is ever called before binding, since a real caller forgetting to
   bind is a real mistake worth a clear message, not an ``AttributeError``
   two frames deep.
2. **The real ``inputs["context"]`` object is not, and cannot yet be,
   an instance of :class:`ai_os_sdk.models.context.AssembledContext`.**
   ``AgentStepExecutor`` (unmigrated Kernel code, out of this step's own
   scope) still constructs and passes through a real
   :class:`ai_os_kernel.context_manager.models.AssembledContext` — a
   different, unrelated Python class from the SDK's own boundary model,
   even though step 7 narrowed the two to identical fields. A migrated
   agent cannot import the Kernel class to ``isinstance``-check against
   it (that import is exactly what this migration removes), and
   ``isinstance`` against the SDK's own model would always be ``False``
   against the real object the Workflow Engine actually sends. This
   module therefore duck-types the context object (checks for a real,
   non-empty ``.items`` attribute, then reads each item's own
   ``.content``) instead of a nominal ``isinstance`` check — not a
   workaround, but the correct, real answer given the SDK's own
   ``Agent`` Protocol already documents ``inputs`` as carrying "rich
   objects, not only strings" without naming their concrete types.

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

from ai_os_sdk.contracts.tool_invoker import PLATFORM_SANDBOX_RUN_COMMAND

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
        # Duck-typed, not `isinstance(context, AssembledContext)` — the
        # real object the Workflow Engine sends here is still
        # ai_os_kernel.context_manager.models.AssembledContext (unmigrated
        # Kernel code, out of this step's scope), a different Python
        # class from the SDK's own boundary model even though step 7
        # narrowed the two to identical fields. This agent no longer
        # imports ai_os_kernel at all, so a nominal isinstance check
        # against either class is unavailable or always false — see this
        # module's own docstring for the full reasoning.
        items = getattr(context, "items", None)
        if not items:
            raise TestInstructionError(
                "TestAgentEntrypoint requires 'workingDirectory', 'filePath', and "
                "'runCommand' — either directly in inputs, or as a JSON object in "
                "the assembled context"
            )
        raw = "\n\n".join(item.content for item in items)
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
    for the full reasoning, including the step 9 migration onto
    :class:`~ai_os_sdk.contracts.Agent` +
    :class:`~ai_os_sdk.contracts.entrypoint_context.PackContextReceiver`.

    ``timeout_seconds``/``max_output_bytes`` are optional constructor
    overrides — always their defaults in production (``EntrypointLoader``
    only ever calls ``cls()``), and how a test tightens the limits. There
    is no ``sandbox`` constructor override any more: the real sandbox now
    arrives exclusively through :meth:`bind_pack_context`'s own
    ``context.tools`` (a real :class:`~ai_os_sdk.contracts.ToolInvoker`),
    per the step 6b injection mechanism — a test substitutes a
    fake/inspectable sandbox by binding a ``PackContext`` built over one,
    not by passing it to this constructor.
    """

    output_schema: dict[str, Any] = _OUTPUT_SCHEMA

    def __init__(
        self,
        *,
        timeout_seconds: float = _RUN_TIMEOUT_SECONDS,
        max_output_bytes: int = _RUN_MAX_OUTPUT_BYTES,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._max_output_bytes = max_output_bytes
        self._context: Any | None = None

    def bind_pack_context(self, context: Any) -> None:
        self._context = context

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        if self._context is None or self._context.tools is None:
            raise TestInstructionError(
                "TestAgentEntrypoint.execute() called before bind_pack_context() bound a "
                "PackContext granting the sandbox:execute permission (context.tools) — a "
                "real caller must inject one before first use"
            )

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

        result = await self._context.tools.invoke(
            PLATFORM_SANDBOX_RUN_COMMAND,
            {
                "command": run_command,
                "working_directory": str(working_directory),
                "timeout_seconds": self._timeout_seconds,
                "max_output_bytes": self._max_output_bytes,
            },
        )

        return {
            "passed": result.exit_code == 0 and not result.timed_out,
            "exitCode": result.exit_code,
            "output": result.stdout + result.stderr,
        }
