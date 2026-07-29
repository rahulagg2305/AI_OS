"""Wraps a real :class:`~ai_os_kernel.sandbox.executor.SandboxExecutor`
to satisfy :class:`ai_os_sdk.contracts.ToolInvoker`
(``platform_sdk_v1_scope.md`` step 6a).

**Built directly over the sandbox, never over the dict-based**
:class:`ai_os_sdk.contracts.tool.Tool` — exactly as §5.6's decision
block requires, so a typed :class:`~ai_os_kernel.sandbox.models.
SandboxResult` is never flattened into a dict and re-parsed, preserving
the ``timed_out``/``truncated`` distinctions step 6 extended
``ToolResult`` to carry.

**The ``ToolResult`` conversion below is the same logic step 6's own
cross-boundary test proved against real, actually-executed sandbox
runs** (``tests/unit/platform_sdk/test_tool_invoker_sandbox_conversion.py``)
— branching on ``exit_code is None`` first, not on ``timed_out`` first,
because a cap-breach-triggered kill can *also* leave ``exit_code`` a
``None`` with ``timed_out=False``, which step 6 discovered by running
the real sandbox, not by assumption.

**A real, documented gap this step surfaced: v1.0.0's ``ToolInvoker``
Protocol carries no trace or security context parameter at all**
(``invoke(tool_id, inputs, *, timeout_seconds)`` — contrast §4.3's fuller
``ToolRequest``, which does carry ``trace: TraceContext``, but is
deferred in v1.0.0 for having no consumer). Yet a failing
:class:`~ai_os_sdk.models.tool.ToolResult` requires a
:class:`~ai_os_sdk.errors.StructuredError`, which itself requires a
``TraceContext`` (§4.4, required, not optional). This adapter resolves
that by generating a fresh, real, per-invocation
:class:`~ai_os_sdk.models.common.TraceContext` using the Kernel's own
existing :func:`~ai_os_kernel.observability.trace.generate_trace_id`
utility for both ``trace_id`` and ``span_id`` — a real, valid
correlation id, but **not** correlated with whatever workflow or step
actually invoked this tool, since the Protocol gives this adapter
nothing to correlate against. Threading a real caller-supplied trace
through requires widening ``ToolInvoker.invoke``'s own signature, which
is out of this step's scope (SDK-side only) — recorded here as a
concrete, evidenced input to whichever future step revisits §5.6.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from ai_os_kernel.observability.trace import generate_trace_id
from ai_os_kernel.sandbox.executor import SandboxExecutor
from ai_os_kernel.sandbox.models import SandboxResult
from ai_os_sdk.contracts.tool_invoker import (
    PLATFORM_SANDBOX_RUN_COMMAND,
    PLATFORM_SANDBOX_RUN_COMMAND_DESCRIPTOR,
)
from ai_os_sdk.errors import PermanentError, TransientError
from ai_os_sdk.models.common import TraceContext
from ai_os_sdk.models.tool import ToolDescriptor, ToolResult, ToolStatus


class UnknownToolError(ValueError):
    """Raised by :meth:`ToolInvokerAdapter.invoke` for any ``tool_id``
    other than :data:`~ai_os_sdk.contracts.tool_invoker.PLATFORM_SANDBOX_RUN_COMMAND`
    — the only tool this v1.0.0 adapter knows about. A pack-declared
    tool registry would extend this adapter's ``available_tools()``
    and this check, not replace either."""


def _generate_trace_context() -> TraceContext:
    """A fresh, real, per-invocation trace — see this module's own
    docstring for why it cannot be the caller's own trace context."""
    return TraceContext(trace_id=generate_trace_id(), span_id=generate_trace_id())


def _sandbox_result_to_tool_result(result: SandboxResult) -> ToolResult:
    """Real production version of the reference conversion step 6's own
    test proved against actually-executed sandbox runs
    (``tests/unit/platform_sdk/test_tool_invoker_sandbox_conversion.py``).
    See this module's own docstring for why ``exit_code is None`` is
    checked before ``timed_out``.
    """
    duration_ms = round(result.duration_seconds * 1000)
    trace = _generate_trace_context()

    if result.exit_code is None:
        error = (
            TransientError("sandbox.timed_out", "command exceeded its timeout")
            if result.timed_out
            else TransientError(
                "sandbox.killed_on_output_cap",
                "command was killed after exceeding its output cap, before it "
                "could exit on its own — no confirmed outcome is available",
            )
        ).to_structured_error(trace=trace)
        return ToolResult(
            status=ToolStatus.FAILURE,
            outputs=None,
            error=error,
            exit_code=None,
            stdout=result.stdout,
            stderr=result.stderr,
            timed_out=result.timed_out,
            truncated=result.truncated,
            duration_ms=duration_ms,
        )
    if result.exit_code != 0:
        return ToolResult(
            status=ToolStatus.FAILURE,
            outputs=None,
            error=PermanentError(
                "sandbox.nonzero_exit", f"command exited {result.exit_code}"
            ).to_structured_error(trace=trace),
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            timed_out=False,
            truncated=result.truncated,
            duration_ms=duration_ms,
        )
    return ToolResult(
        status=ToolStatus.SUCCESS,
        outputs={"stdout": result.stdout, "stderr": result.stderr},
        error=None,
        exit_code=result.exit_code,
        stdout=result.stdout,
        stderr=result.stderr,
        timed_out=False,
        truncated=result.truncated,
        duration_ms=duration_ms,
    )


class ToolInvokerAdapter:
    """Satisfies :class:`ai_os_sdk.contracts.ToolInvoker` by delegating
    ``platform.sandbox.run_command`` to a real, injected
    :class:`SandboxExecutor`.

    **Timeout precedence — a deliberate, tested decision, recorded here
    because §5.6's own decision block left it explicitly open.**
    ``invoke()``'s own ``timeout_seconds`` and
    ``inputs["timeout_seconds"]`` (required by this tool's own input
    schema) can both be supplied for the same call. **The more
    restrictive of the two always wins**: the effective timeout passed
    to the real sandbox is ``min(timeout_seconds, inputs["timeout_seconds"])``
    when the caller supplies an outer ``timeout_seconds``, or simply
    ``inputs["timeout_seconds"]`` when it does not (``None`` is "no
    outer ceiling," not "no timeout at all" — the tool's own timeout is
    always required and always real).

    This is chosen over "one is authoritative, reject the other on
    conflict" for two reasons: it never rejects a call outright over a
    disagreement that has an obvious, safe resolution (whichever bound
    is tighter is always the one a cautious caller would want honoured);
    and it composes correctly with the Protocol's own stated intent for
    the outer parameter — "a generic, tool-agnostic ceiling the invoker
    itself may enforce on the whole call"
    (:mod:`ai_os_sdk.contracts.tool_invoker`) — a ceiling is exactly a
    ``min()``, never a ``max()`` or an equality requirement.
    """

    def __init__(self, sandbox: SandboxExecutor) -> None:
        self._sandbox = sandbox

    def available_tools(self) -> tuple[ToolDescriptor, ...]:
        return (PLATFORM_SANDBOX_RUN_COMMAND_DESCRIPTOR,)

    async def invoke(
        self, tool_id: str, inputs: dict[str, Any], *, timeout_seconds: float | None = None
    ) -> ToolResult:
        if tool_id != PLATFORM_SANDBOX_RUN_COMMAND:
            raise UnknownToolError(
                f"tool_id {tool_id!r} is not known to this adapter — the only tool "
                f"registered in v1.0.0 is {PLATFORM_SANDBOX_RUN_COMMAND!r} "
                f"(see {type(self).__name__}.available_tools())"
            )

        errors = sorted(
            Draft202012Validator(PLATFORM_SANDBOX_RUN_COMMAND_DESCRIPTOR.input_schema).iter_errors(
                inputs
            ),
            key=lambda e: list(map(str, e.path)),
        )
        if errors:
            lines = [f"  - {'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors]
            raise ValueError(
                f"inputs for tool_id {tool_id!r} do not satisfy its declared input_schema:\n"
                + "\n".join(lines)
            )

        inputs_timeout_seconds: float = inputs["timeout_seconds"]
        effective_timeout_seconds = (
            min(timeout_seconds, inputs_timeout_seconds)
            if timeout_seconds is not None
            else inputs_timeout_seconds
        )

        stdin_str: str | None = inputs.get("stdin")
        result = await self._sandbox.execute(
            command=inputs["command"],
            working_directory=Path(inputs["working_directory"]),
            timeout_seconds=effective_timeout_seconds,
            max_output_bytes=inputs["max_output_bytes"],
            env=inputs.get("env"),
            stdin=stdin_str.encode() if stdin_str is not None else None,
        )
        return _sandbox_result_to_tool_result(result)
