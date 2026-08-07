"""The `build.run` Tool — `agent_specifications.md`'s own already-
documented, not-yet-built name — the second real, manifest-declared,
registry-resolvable Tool this pack declares (`P03-S04-M31-T02`).

**Genuinely parameterized per invocation, unlike
`ai_os_kernel.workflow_engine.sandboxed_tool.SandboxedCommandTool`.**
That Kernel-native Tool takes its command at *construction* time
because `workflow_architecture.md`'s Step Contract gives a `tool`-type
WorkflowStep no per-invocation input fields (`ToolStepExecutor` always
calls `execute({})`) — and because it is not zero-argument
constructible, it could never be a manifest-declared entrypoint at all
(`EntrypointLoader` only ever calls `cls()`). This Tool is invoked the
other real way instead — an agent's own
`context.tools.invoke("build.run", inputs)` — which
`ToolInvokerAdapter._invoke_registered_tool` genuinely forwards `inputs`
into, unlike the `tool`-step path. Command, working directory, timeout,
and output cap are therefore real per-invocation fields here, not
fixed at construction — the first tool in this pack to be genuinely
reusable across arbitrarily many different real commands, mirroring
the shape `ai_os_sdk.contracts.tool_invoker.PLATFORM_SANDBOX_RUN_COMMAND`
already establishes for the platform-level shim, but now proving a
*second*, pack-owned, catalog-resolved `tool_id` reaches a real sandbox
end to end — the real, new capability this ticket exists to prove.

**Not yet wired into any agent.** Every existing agent that needs to
run a command still goes through the shim
(`PLATFORM_SANDBOX_RUN_COMMAND`) unchanged — adopting this Tool in
place of that call is a real, separate, deferred step (the identical
"prove standalone first, wire in later" precedent every agent in this
pack has already followed for its own first real slice).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ai_os_sdk.models.tool import TrustTier

_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "exitCode": {"type": ["integer", "null"]},
        "stdout": {"type": "string"},
        "stderr": {"type": "string"},
        "timedOut": {"type": "boolean"},
        "truncated": {"type": "boolean"},
        "durationSeconds": {"type": "number"},
    },
    "required": ["exitCode", "stdout", "stderr", "timedOut", "truncated", "durationSeconds"],
    "additionalProperties": False,
}

_REQUIRED_INVOCATION_FIELDS = ("command", "workingDirectory", "timeoutSeconds", "maxOutputBytes")


class BuildRunToolInputError(ValueError):
    """This tool's inputs were missing a required field, or a real
    sandbox had not yet been injected — the same real-input-validation
    contract every agent in this pack already enforces for its own
    inputs."""


class BuildRunInput(BaseModel):
    """Documents this Tool's own manifest-declared `inputSchema`
    reference target — mirrors `SandboxExecutor.execute`'s own real
    parameters exactly (`env`/`stdin` excluded from this first real
    slice — no real caller needs them yet; adding them later is
    additive, not a redesign)."""

    command: list[str]
    working_directory: str = Field(..., alias="workingDirectory")
    timeout_seconds: float = Field(..., alias="timeoutSeconds")
    max_output_bytes: int = Field(..., alias="maxOutputBytes")

    model_config = {"populate_by_name": True}


class BuildRunOutput(BaseModel):
    """Documents this Tool's own manifest-declared `outputSchema`
    reference target — mirrors `_OUTPUT_SCHEMA` exactly, the identical
    real shape `SandboxedCommandTool` already establishes."""

    exit_code: int | None = Field(..., alias="exitCode")
    stdout: str
    stderr: str
    timed_out: bool = Field(..., alias="timedOut")
    truncated: bool
    duration_seconds: float = Field(..., alias="durationSeconds")

    model_config = {"populate_by_name": True}


class BuildRunToolEntrypoint:
    """The manifest's own `tools[].entrypoint` for `build.run` —
    zero-argument-constructible, no `PackContextReceiver` needed (see
    `fs_read.py`'s own docstring for why: only a directly-injected
    `sandbox` is required, never `llm`/`prompts`/`tools`)."""

    trust_tier: TrustTier = TrustTier.TIER1_SANDBOXED
    output_schema: dict[str, Any] = _OUTPUT_SCHEMA

    def __init__(self) -> None:
        self.sandbox: Any = None

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        command = inputs.get("command")
        working_directory = inputs.get("workingDirectory")
        timeout_seconds = inputs.get("timeoutSeconds")
        max_output_bytes = inputs.get("maxOutputBytes")
        missing = [
            name
            for name, value in zip(
                _REQUIRED_INVOCATION_FIELDS,
                (command, working_directory, timeout_seconds, max_output_bytes),
                strict=True,
            )
            if value is None
        ]
        if missing:
            raise BuildRunToolInputError(
                f"BuildRunToolEntrypoint requires {', '.join(_REQUIRED_INVOCATION_FIELDS)} in "
                f"its inputs — missing: {', '.join(missing)}"
            )
        if (
            not isinstance(command, list)
            or not command
            or not all(isinstance(part, str) for part in command)
        ):
            raise BuildRunToolInputError(
                "BuildRunToolEntrypoint requires 'command' to be a non-empty list of strings"
            )
        if self.sandbox is None:
            raise BuildRunToolInputError(
                "BuildRunToolEntrypoint.execute() called before a real sandbox was injected — "
                "a real caller (SqlToolRegistry.resolve_tool) always injects one for a "
                "tier1_sandboxed tool before returning it"
            )
        assert (  # noqa: S101
            isinstance(working_directory, str)
            and isinstance(timeout_seconds, (int, float))
            and isinstance(max_output_bytes, int)
        )

        result = await self.sandbox.execute(
            command=command,
            working_directory=Path(working_directory),
            timeout_seconds=timeout_seconds,
            max_output_bytes=max_output_bytes,
        )
        return {
            "exitCode": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "timedOut": result.timed_out,
            "truncated": result.truncated,
            "durationSeconds": result.duration_seconds,
        }
