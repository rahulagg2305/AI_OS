"""The `fs.read` Tool — `agent_specifications.md`'s own already-
documented, not-yet-built name (its "Not built" paragraph names it
first among the Tools no pack has ever declared) — the first real,
manifest-declared, registry-resolvable Tool this codebase has ever had
(`P03-S04-M31-T02`, FR unnamed but scoped by the Agent Catalog's own
Tools column).

**Two real, previously-undiscovered Kernel bugs found and fixed before
this Tool could resolve at all** — see
`ai_os_kernel.workflow_engine.registry.SqlToolRegistry.resolve_tool`'s
own comments for the full account. In short: (1) its trust-tier
consistency check compared object *identity* (`is not`) against
`ai_os_kernel.workflow_engine.tool.TrustTier`, which a real pack (
forbidden from importing `ai_os_kernel` at all) can never be identical
to — every test entrypoint this check had ever run against before this
ticket imported that exact Kernel enum directly, so the bug was never
exercised; (2) `PackContext` (`llm`/`prompts`/`tools` only) gave a
zero-argument-constructible, `PackContextReceiver`-based Tool no way
to receive a real `SandboxExecutor`, so no such Tool could ever
satisfy `SandboxBackedTool` — `SqlToolRegistry` now injects it
directly, bypassing `PackContext` for this one Kernel-side structural
need.

**No `PackContextReceiver`/`bind_pack_context` needed at all.** Unlike
every agent in this pack, this Tool needs no `llm`/`prompts`/`tools`
capability — only a real sandbox, which `SqlToolRegistry` now injects
directly onto this class's own `sandbox` attribute, the exact
structural shape `SandboxBackedTool` requires. `self.sandbox: Any`,
not a real `SandboxExecutor` type — this pack cannot import
`ai_os_kernel` at all, the identical constraint every agent's own
`bind_pack_context(context: Any)` already carries.

**Reuses `ai_os_pack_software_engineering.agents.code_review`'s own
`_READ_FILE_SCRIPT` convention exactly** (a tiny, real
`python -c` script reading the whole file as bytes and writing it to
stdout) — the identical, already-proven pattern, just now run through
this Tool's own, directly-injected `sandbox` rather than through
`context.tools.invoke(PLATFORM_SANDBOX_RUN_COMMAND, ...)` (the shim
path every agent is limited to, having no direct sandbox access of its
own).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ai_os_sdk.models.tool import TrustTier

_READ_FILE_SCRIPT = (
    "import pathlib, sys\nsys.stdout.buffer.write(pathlib.Path(sys.argv[1]).read_bytes())\n"
)

# Named, documented first-cut values — the identical "placeholder
# safety limit" carve-out every sandboxed operation in this pack
# already uses (`code_review.py`'s own `_READ_TIMEOUT_SECONDS`/
# `_READ_MAX_OUTPUT_BYTES`, mirrored here since this Tool now performs
# the identical real operation through its own, directly-injected
# sandbox instead).
_READ_TIMEOUT_SECONDS = 10.0
_READ_MAX_OUTPUT_BYTES = 10_000_000

_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"content": {"type": "string"}},
    "required": ["content"],
    "additionalProperties": False,
}


class FsReadToolInputError(ValueError):
    """This tool's inputs were missing a required field
    (`filePath`/`workingDirectory`) or named a file that could not be
    read — the same real-input-validation contract every agent in this
    pack already enforces for its own inputs, since
    `ToolInvokerAdapter._invoke_registered_tool` performs no schema
    validation of its own before calling `execute()`."""


class FsReadInput(BaseModel):
    """Documents this Tool's own manifest-declared `inputSchema`
    reference target — mirrors `workflows/models.py`'s own established
    "documents the contract, not yet a second real validation path"
    convention (`execute()` validates for real at runtime)."""

    file_path: str = Field(..., alias="filePath")
    working_directory: str = Field(..., alias="workingDirectory")

    model_config = {"populate_by_name": True}


class FsReadOutput(BaseModel):
    """Documents this Tool's own manifest-declared `outputSchema`
    reference target — mirrors `_OUTPUT_SCHEMA` exactly."""

    content: str


class FsReadToolEntrypoint:
    """The manifest's own `tools[].entrypoint` for `fs.read` —
    zero-argument-constructible
    (`ai_os_kernel.workflow_engine.entrypoint_loader.EntrypointLoader`,
    `ai_os_kernel.workflow_engine.registry.SqlToolRegistry`)."""

    trust_tier: TrustTier = TrustTier.TIER1_SANDBOXED
    output_schema: dict[str, Any] = _OUTPUT_SCHEMA

    def __init__(self) -> None:
        self.sandbox: Any = None

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        file_path = inputs.get("filePath")
        working_directory = inputs.get("workingDirectory")
        missing = [
            name
            for name, value in (("filePath", file_path), ("workingDirectory", working_directory))
            if not isinstance(value, str) or not value
        ]
        if missing:
            raise FsReadToolInputError(
                f"FsReadToolEntrypoint requires 'filePath' and 'workingDirectory' in its "
                f"inputs — missing: {', '.join(missing)}"
            )
        if self.sandbox is None:
            raise FsReadToolInputError(
                "FsReadToolEntrypoint.execute() called before a real sandbox was injected — "
                "a real caller (SqlToolRegistry.resolve_tool) always injects one for a "
                "tier1_sandboxed tool before returning it"
            )
        assert isinstance(file_path, str) and isinstance(working_directory, str)  # noqa: S101

        result = await self.sandbox.execute(
            command=[*self.sandbox.python_command, "-c", _READ_FILE_SCRIPT, file_path],
            working_directory=Path(working_directory),
            timeout_seconds=_READ_TIMEOUT_SECONDS,
            max_output_bytes=_READ_MAX_OUTPUT_BYTES,
        )
        if result.exit_code != 0:
            raise FsReadToolInputError(
                f"FsReadToolEntrypoint could not read {file_path!r}: exit code "
                f"{result.exit_code}, stderr: {result.stderr.strip()}"
            )
        return {"content": result.stdout}
