"""The first real ``tier1_sandboxed`` :class:`~ai_os_kernel.workflow_engine.
tool.Tool`: one that genuinely executes a command through an injected
:class:`~ai_os_kernel.sandbox.executor.SandboxExecutor`, rather than
declaring the tier and doing nothing about it
(:class:`~ai_os_kernel.workflow_engine.tool.EchoTool`'s own honest
``tier2_trusted`` default exists precisely because it *cannot* make
this tier's claim truthfully).

**A fixed command, configured at construction, not per invocation.**
workflow_architecture.md's Step Contract gives a tool step no
per-invocation input fields, and this step's own approved framing
explicitly keeps that deferral on record — "no new input_schema
mechanism." :meth:`SandboxedCommandTool.execute` is therefore called
with whatever :class:`~ai_os_kernel.workflow_engine.step_executor.
ToolStepExecutor` already calls every tool with (``{}``, currently) and
ignores it, exactly like :class:`~ai_os_kernel.workflow_engine.tool.
EchoTool`. The command, working directory, timeout, output cap, any
explicit environment, and any ``stdin`` bytes are all supplied at
construction time instead — the same shape a Capability Pack's own
manifest-declared, per-tool configuration would eventually supply, not
a workaround.

**``stdin`` (optional, defaulted ``None``) is how a caller hands the
command real data without an argv or environment-variable size limit
or shell-quoting risk** — the Software Engineering pack's Build Agent
uses this to deliver LLM-produced file content to a small write-file
script, rather than passing content as a command-line argument.
Forwarded unchanged to :meth:`~ai_os_kernel.sandbox.executor.
SandboxExecutor.execute`'s own identically-named, identically-optional
parameter — see that Protocol's own docstring for what "delivered
concurrently, best-effort" means.

**Declaring ``tier1_sandboxed`` here is not a paperwork exercise — it
is what the Tool actually does**, and it is exactly why
:class:`ToolStepExecutor` needs a way to tell this Tool apart from one
that merely claims the tier without a sandbox behind it: see
:class:`~ai_os_kernel.workflow_engine.tool.SandboxBackedTool` for that
structural marker, which this class satisfies by exposing its injected
``sandbox`` as a plain, readable attribute.

**No new architectural claim about ADR-0016 compliance.** Whatever
:class:`~ai_os_kernel.sandbox.executor.SandboxExecutor` this Tool is
constructed with is what actually runs the command — today, in
practice, :class:`~ai_os_kernel.sandbox.executor.LocalSubprocessSandbox`,
which its own ``guarantees`` honestly declares does *not* provide
network isolation or filesystem containment. This Tool does not
upgrade, hide, or work around that; it only proves the dispatch path
end to end. Running this Tool against genuinely untrusted/hostile
content remains gated on a real container/OCI backend, exactly as the
Sandbox Executor's own docstring already states.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ai_os_kernel.sandbox.executor import SandboxExecutor
from ai_os_kernel.workflow_engine.tool import TrustTier

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


class SandboxedCommandTool:
    """Executes one fixed, constructor-supplied command through
    ``sandbox`` and returns its :class:`~ai_os_kernel.sandbox.models.
    SandboxResult`, mapped onto this Tool's own declared
    ``output_schema``. ``trust_tier`` is always
    :attr:`~ai_os_kernel.workflow_engine.tool.TrustTier.TIER1_SANDBOXED`
    — unlike :class:`~ai_os_kernel.workflow_engine.tool.EchoTool`, it is
    not constructor-settable, since this Tool's entire behaviour is the
    thing that tier exists to describe.
    """

    trust_tier: TrustTier = TrustTier.TIER1_SANDBOXED
    output_schema: dict[str, Any] = _OUTPUT_SCHEMA

    def __init__(
        self,
        sandbox: SandboxExecutor,
        *,
        command: Sequence[str],
        working_directory: Path,
        timeout_seconds: float,
        max_output_bytes: int,
        env: Mapping[str, str] | None = None,
        stdin: bytes | None = None,
    ) -> None:
        self.sandbox = sandbox
        self._command = command
        self._working_directory = working_directory
        self._timeout_seconds = timeout_seconds
        self._max_output_bytes = max_output_bytes
        self._env = env
        self._stdin = stdin

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        result = await self.sandbox.execute(
            command=self._command,
            working_directory=self._working_directory,
            timeout_seconds=self._timeout_seconds,
            max_output_bytes=self._max_output_bytes,
            env=self._env,
            stdin=self._stdin,
        )
        return {
            "exitCode": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "timedOut": result.timed_out,
            "truncated": result.truncated,
            "durationSeconds": result.duration_seconds,
        }
