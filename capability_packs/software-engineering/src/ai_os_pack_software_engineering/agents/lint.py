"""The Lint Agent — this pack's sixth agent, and the first added since
the Capability Pack growth gate lifted (2026-07-29,
`docs/process/standing_rules.md`). Given a file the Build Agent wrote,
genuinely run a real static-analysis tool against it inside the
sandbox and report the real pass/fail outcome, derived only from the
tool's own exit code — never from an LLM's opinion.

**Deliberately near-identical to `verification.py`'s own
`TestAgentEntrypoint` — not accidental duplication, the same
"no shared module needed for a single real caller each" reasoning that
module's own docstring already applies to a different pair of
duplicated functions in this pack.** This agent exists specifically to
answer this feature step's own question — does the Quality Gate
Engine's `gate_sources`/`success_field`/retry-target mechanism
genuinely generalize to a second, distinct gate category (Static
Analysis, `quality_gates_framework.md` §5.2) — and the honest answer is
almost entirely yes, via configuration alone: this agent, once it
exists, is wired into `se.delivery_pipeline` exactly the way `qa-test`
already is (an `agent` step producing a `passed` field, followed by a
`quality_gate` step reading it via `gate_sources`, retried via
`gate_retry_targets`) — zero changes to `QualityGateStepExecutor`,
`DispatchingStepExecutor`, or `WorkflowAdvanceRunner`. The one thing
that could not be pure configuration is this agent itself: nothing in
this pipeline previously ran a static-analysis tool at all, so
*something* has to. Building it as a small agent mirroring the
already-proven Test Agent shape — not a new Kernel/gate mechanism, not
new tool infrastructure (the exact same `platform.sandbox.run_command`
tool every sandboxed agent in this pack already uses) — is the
smallest real answer.

**The tool: `python -m py_compile <file>`, not `ruff` — a real, discovered
constraint, not the first choice.** `ruff` (this workspace's own real,
established linter) was tried first, and genuinely works against the
deterministic tier's `LocalSubprocessSandbox` (this repo's own venv,
which has `ruff` as a `[dependency-groups] dev` dependency). It
genuinely fails against `DockerSandbox`'s own default image
(`python:3.12-slim`, `ai_os_kernel.sandbox.docker_executor._DEFAULT_IMAGE`)
— a bare Python image with no `ruff`, and no dependency-install step
exists anywhere in this codebase to put it there (ADR-0016's own
documented, still-unbuilt egress-proxy dependency-install step;
`feature_inventory.md` module 20). Since `se.delivery_pipeline`'s own
step *sequence* is one shared `WorkflowDefinition` every sandbox
backend runs identically, a lint tool that only works on one backend is
a genuine correctness gap, not a cosmetic one — a workflow author has
no way to know a gate would silently behave differently depending on
which backend happens to be configured. `python -m py_compile` is the
real, honest fix: a stdlib module, present in every Python installation
this codebase could possibly run against, regardless of sandbox
backend or dev-dependency installation state. **The real, recorded
trade-off**: `py_compile` only catches genuine syntax errors — a
narrower slice of "Static Analysis" (`quality_gates_framework.md` §5.2)
than `ruff`'s own style/unused-import/import-order findings. This is
the honest boundary of "no new tool infrastructure": the smallest real
answer that works identically everywhere this pipeline can actually
run, not the most thorough one.

**Input/output contract mirrors the Test Agent's own exactly, field for
field, except `runCommand` -> `lintCommand`** (a deliberately different
name — this agent's own command is `[*python_command, "-m",
"py_compile", filePath]`, a different shape from Test's
`[*python_command, filePath]`, so reusing the same field name would
blur two genuinely different composition-level transforms in
`ai_os_kernel.workflow_engine.delivery_pipeline`). Out: ``passed``
(``exitCode == 0`` — ``py_compile`` exits non-zero the moment the file
fails to parse, never from any judgment about ``output``'s own
content), ``exitCode``, ``output`` (stdout then stderr, concatenated —
a real `SyntaxError` traceback on failure).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ai_os_sdk.contracts.tool_invoker import PLATFORM_SANDBOX_RUN_COMMAND

# Named, documented first-cut values — the identical "placeholder
# safety limit, not yet tuned" carve-out `verification.py` already
# uses for the same reason. A py_compile check against one
# already-written file is not expected to exceed these.
_LINT_TIMEOUT_SECONDS = 10.0
_LINT_MAX_OUTPUT_BYTES = 65536

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


class LintInstructionError(Exception):
    """This agent's input could not be turned into a safe, real run —
    a required field was missing or malformed, or ``filePath`` does not
    resolve to a real, existing file inside ``workingDirectory``.
    Raised clearly, before any sandbox call is attempted."""


class LintAgentInput(BaseModel):
    """Documents this agent's Agent Contract "Required Inputs"
    (capability_pack_contract.md). **Not yet validated at runtime** —
    the identical, still unchanged "no per-step input-mapping mechanism
    exists" scope every agent in this pack already documents. Field
    names deliberately match ``BuildAgentOutput``'s own
    ``workingDirectory``/``filePath`` — this agent is meant to consume
    a Build Agent result directly.
    """

    working_directory: str = Field(..., alias="workingDirectory")
    file_path: str = Field(..., alias="filePath")
    lint_command: list[str] = Field(
        ...,
        alias="lintCommand",
        description="The exact argv to execute, e.g. ['python', '-m', 'py_compile', 'a.py'].",
    )

    model_config = {"populate_by_name": True}


class LintAgentOutput(BaseModel):
    """Documents this agent's Agent Contract "Produced Outputs." Mirrors
    the real fields :meth:`LintAgentEntrypoint.execute` returns —
    ``passed`` is derived only from ``exitCode``, never from any
    judgment about ``output``'s own content.
    """

    passed: bool
    exit_code: int | None = Field(..., alias="exitCode")
    output: str

    model_config = {"populate_by_name": True}


def _resolve_existing_file(working_directory: Path, raw_path: str) -> Path:
    """Resolves ``raw_path`` against ``working_directory``, verifies it
    remains inside it, and verifies the resulting file genuinely
    exists. Raises :class:`LintInstructionError` otherwise — the
    identical check :mod:`~ai_os_pack_software_engineering.agents.
    verification`'s own ``_resolve_existing_file`` already establishes,
    duplicated here for the same "no shared module needed for a single
    real caller each" reason."""
    stripped = raw_path.strip()
    if not stripped:
        raise LintInstructionError("filePath must not be blank")

    resolved_root = working_directory.resolve()
    resolved_target = (working_directory / stripped).resolve()
    if not resolved_target.is_relative_to(resolved_root):
        raise LintInstructionError(f"filePath {raw_path!r} resolves outside {working_directory}")
    if not resolved_target.is_file():
        raise LintInstructionError(
            f"filePath {raw_path!r} does not exist inside {working_directory}"
        )
    return resolved_target


_REQUIRED_FIELDS = ("workingDirectory", "filePath", "lintCommand")


def _extract_payload(inputs: dict[str, Any]) -> tuple[str, str, list[str]]:
    """Returns ``(workingDirectory, filePath, lintCommand)`` from
    ``inputs`` directly, or, when absent, parsed as JSON from the
    Context Manager's own assembled ``context`` — the identical
    fallback :mod:`~ai_os_pack_software_engineering.agents.verification`'s
    own ``_extract_payload`` already establishes. Raises
    :class:`LintInstructionError` with a clear reason if neither yields
    a complete, well-typed payload."""
    if all(field in inputs for field in _REQUIRED_FIELDS):
        payload = {field: inputs[field] for field in _REQUIRED_FIELDS}
    else:
        context = inputs.get("context")
        items = getattr(context, "items", None)
        if not items:
            raise LintInstructionError(
                "LintAgentEntrypoint requires 'workingDirectory', 'filePath', and "
                "'lintCommand' — either directly in inputs, or as a JSON object in "
                "the assembled context"
            )
        raw = "\n\n".join(item.content for item in items)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LintInstructionError(
                f"the assembled context is not a valid JSON object: {exc}"
            ) from exc
        if not isinstance(payload, dict) or not all(field in payload for field in _REQUIRED_FIELDS):
            raise LintInstructionError(
                "the assembled context's JSON object is missing 'workingDirectory', "
                "'filePath', or 'lintCommand'"
            )

    working_directory, file_path, lint_command = (payload[field] for field in _REQUIRED_FIELDS)
    if not isinstance(working_directory, str) or not isinstance(file_path, str):
        raise LintInstructionError("workingDirectory and filePath must both be strings")
    if not isinstance(lint_command, list) or not all(isinstance(x, str) for x in lint_command):
        raise LintInstructionError("lintCommand must be a list of strings")
    return working_directory, file_path, lint_command


class LintAgentEntrypoint:
    """The manifest's own ``agents[].entrypoint`` for the Lint Agent —
    zero-argument-constructible like every other agent in this pack,
    trivially so here: nothing is built lazily, since this agent needs
    no LLM composition at all (the identical shape
    ``TestAgentEntrypoint`` already establishes for the same reason).
    Implements :class:`~ai_os_sdk.contracts.Agent` +
    :class:`~ai_os_sdk.contracts.entrypoint_context.PackContextReceiver`
    directly — no ``ai_os_kernel`` import anywhere, satisfying check 7
    from the start rather than needing a later migration step.

    ``timeout_seconds``/``max_output_bytes`` are optional constructor
    overrides — always their defaults in production, and how a test
    tightens the limits.
    """

    output_schema: dict[str, Any] = _OUTPUT_SCHEMA

    def __init__(
        self,
        *,
        timeout_seconds: float = _LINT_TIMEOUT_SECONDS,
        max_output_bytes: int = _LINT_MAX_OUTPUT_BYTES,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._max_output_bytes = max_output_bytes
        self._context: Any | None = None

    def bind_pack_context(self, context: Any) -> None:
        self._context = context

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        if self._context is None or self._context.tools is None:
            raise LintInstructionError(
                "LintAgentEntrypoint.execute() called before bind_pack_context() bound a "
                "PackContext granting the sandbox:execute permission (context.tools) — a "
                "real caller must inject one before first use"
            )

        working_directory_raw, file_path_raw, lint_command = _extract_payload(inputs)

        working_directory = Path(working_directory_raw)
        # Off the event loop thread (ASYNC240) — the same fix already
        # applied throughout this codebase's own sandbox/agent modules.
        if not await asyncio.to_thread(working_directory.is_dir):
            raise LintInstructionError(
                f"workingDirectory {working_directory_raw!r} does not exist or is not a directory"
            )
        await asyncio.to_thread(_resolve_existing_file, working_directory, file_path_raw)

        result = await self._context.tools.invoke(
            PLATFORM_SANDBOX_RUN_COMMAND,
            {
                "command": lint_command,
                "working_directory": str(working_directory),
                "timeout_seconds": self._timeout_seconds,
                "max_output_bytes": self._max_output_bytes,
            },
        )

        return {
            "passed": result.exit_code == 0,
            "exitCode": result.exit_code,
            "output": result.stdout + result.stderr,
        }
