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

**Step 12a (inserted, 2026-07-29): resolves ``PLATFORM_PYTHON_INTERPRETER``
tokens in ``inputs["command"]`` into this instance's own real
``sandbox.python_command``, before dispatch.** Step 12 (``build`` agent
migration) found a real regression: a migrated agent no longer holds the
``SandboxExecutor`` directly, so it can no longer ask it for its own
backend-specific interpreter invocation the way pre-migration code
always could, and worked around it with a static constructor default
that only happened to match the real system-wide default backend. This
adapter is the one place that still holds the real sandbox object, so
it is the correct, general place to resolve the token — not the pack
agent, and not a caller-side constructor default. See
:data:`~ai_os_sdk.contracts.tool_invoker.PLATFORM_PYTHON_INTERPRETER`'s
own docstring for the full history and reasoning, and
``platform_sdk_v1_scope.md`` §6p for this step's own record.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from ai_os_kernel.git_integration.errors import (
    GitOperationFailedError,
    ProtectedBranchPushRefusedError,
)
from ai_os_kernel.git_integration.service import GitIntegrationService
from ai_os_kernel.observability.trace import generate_trace_id
from ai_os_kernel.sandbox.executor import SandboxExecutor
from ai_os_kernel.sandbox.models import SandboxResult
from ai_os_kernel.workflow_engine.errors import (
    PackNotActivatedError,
    ToolNotRegisteredError,
    ToolRegistryError,
    ToolSandboxRequiredError,
)
from ai_os_kernel.workflow_engine.registry import ToolRegistry
from ai_os_kernel.workflow_engine.tool import SandboxBackedTool
from ai_os_kernel.workflow_engine.tool import TrustTier as KernelTrustTier
from ai_os_sdk.contracts.tool_invoker import (
    PLATFORM_GIT_COMMIT,
    PLATFORM_GIT_COMMIT_DESCRIPTOR,
    PLATFORM_GIT_CREATE_BRANCH,
    PLATFORM_GIT_CREATE_BRANCH_DESCRIPTOR,
    PLATFORM_GIT_PUSH,
    PLATFORM_GIT_PUSH_DESCRIPTOR,
    PLATFORM_PYTHON_INTERPRETER,
    PLATFORM_SANDBOX_RUN_COMMAND,
    PLATFORM_SANDBOX_RUN_COMMAND_DESCRIPTOR,
)
from ai_os_sdk.errors import PermanentError, TransientError
from ai_os_sdk.models.common import TraceContext
from ai_os_sdk.models.tool import ToolDescriptor, ToolResult, ToolStatus

_GIT_TOOL_IDS = frozenset({PLATFORM_GIT_COMMIT, PLATFORM_GIT_CREATE_BRANCH, PLATFORM_GIT_PUSH})


class UnknownToolError(ValueError):
    """Raised by :meth:`ToolInvokerAdapter.invoke` for a ``tool_id``
    that is neither :data:`~ai_os_sdk.contracts.tool_invoker.PLATFORM_SANDBOX_RUN_COMMAND`
    nor genuinely resolvable through this adapter's own injected
    :class:`~ai_os_kernel.workflow_engine.registry.ToolRegistry`
    (``P02-S05-M18-T03``) — including when no registry was supplied at
    construction at all, the identical "not known to this adapter"
    outcome as an unresolvable id."""


def _generate_trace_context() -> TraceContext:
    """A fresh, real, per-invocation trace — see this module's own
    docstring for why it cannot be the caller's own trace context."""
    return TraceContext(trace_id=generate_trace_id(), span_id=generate_trace_id())


def _resolve_python_interpreter(command: list[str], sandbox: SandboxExecutor) -> list[str]:
    """Expands every occurrence of
    :data:`~ai_os_sdk.contracts.tool_invoker.PLATFORM_PYTHON_INTERPRETER`
    in ``command`` into ``sandbox.python_command``'s own real tokens —
    the fix closing the real regression step 12 found and recorded (see
    :data:`~ai_os_sdk.contracts.tool_invoker.PLATFORM_PYTHON_INTERPRETER`'s
    own docstring for the full history). Expands rather than 1:1
    substitutes, since ``python_command`` may be more than one token."""
    resolved: list[str] = []
    for token in command:
        if token == PLATFORM_PYTHON_INTERPRETER:
            resolved.extend(sandbox.python_command)
        else:
            resolved.append(token)
    return resolved


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


def _failure_tool_result(error: PermanentError | TransientError, *, duration_ms: int) -> ToolResult:
    """A real execution-time failure — the tool resolved and ran, but
    either its own code raised or its output did not satisfy its
    declared ``output_schema``. Distinct from the resolution-time
    failures :meth:`ToolInvokerAdapter.invoke` raises directly
    (:class:`UnknownToolError`, a genuine sandboxing refusal): those are
    "this call could never have been dispatched," not "the call ran and
    failed," the same distinction the sandbox shim path already draws
    between a raised :class:`ValueError` (bad ``inputs``) and a returned
    ``ToolResult(status=FAILURE)`` (the sandboxed command itself failed).
    """
    return ToolResult(
        status=ToolStatus.FAILURE,
        outputs=None,
        error=error.to_structured_error(trace=_generate_trace_context()),
        exit_code=None,
        stdout="",
        stderr="",
        timed_out=False,
        truncated=False,
        duration_ms=duration_ms,
    )


class ToolInvokerAdapter:
    """Satisfies :class:`ai_os_sdk.contracts.ToolInvoker` by delegating
    ``platform.sandbox.run_command`` to a real, injected
    :class:`SandboxExecutor`, and — when constructed with a real
    :class:`~ai_os_kernel.workflow_engine.registry.ToolRegistry`
    (``P02-S05-M18-T03``) — any other ``tool_id`` to that registry's
    own real resolution path, never an internal shim: the same
    ``catalog.tools`` lookup, pack-activation gate, and
    ``P02-S05-M13-T08`` permission-grant check
    :class:`~ai_os_kernel.workflow_engine.step_executor.ToolStepExecutor`
    already uses for a Tool-type workflow step, reused here rather than
    re-implemented for this second caller.

    **``registry`` is optional, defaulting to ``None`` — unchanged
    behaviour for every existing caller.** Every construction site
    before this step passes only ``sandbox``; with no registry, any
    ``tool_id`` other than :data:`PLATFORM_SANDBOX_RUN_COMMAND` still
    raises :class:`UnknownToolError`, byte-for-byte the prior behaviour.

    **``git_service`` is optional too, the identical shape
    (``P03-S01-M24-T02``).** With no real
    :class:`~ai_os_kernel.git_integration.service.GitIntegrationService`
    injected, :data:`~ai_os_sdk.contracts.tool_invoker.
    PLATFORM_GIT_COMMIT`/:data:`PLATFORM_GIT_CREATE_BRANCH`/
    :data:`PLATFORM_GIT_PUSH` fall through to the registry path exactly
    like any other unresolved ``tool_id`` — this adapter never
    fabricates Git behaviour it was not given a real service for.

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
    ``min()``, never a ``max()`` or an equality requirement. **A
    registry-resolved tool has no such ceiling to apply**:
    :class:`~ai_os_kernel.workflow_engine.tool.Tool` (unlike the
    sandbox shim's own declared input schema) has no timeout parameter
    of its own — ``timeout_seconds`` is accepted for Protocol
    uniformity but has no real effect on that path, a disclosed gap,
    not a silent no-op dressed up as enforcement.
    """

    def __init__(
        self,
        sandbox: SandboxExecutor,
        *,
        registry: ToolRegistry | None = None,
        git_service: GitIntegrationService | None = None,
    ) -> None:
        self._sandbox = sandbox
        self._registry = registry
        self._git_service = git_service

    def available_tools(self) -> tuple[ToolDescriptor, ...]:
        """Unchanged by this step for the registry path:
        :class:`~ai_os_kernel.workflow_engine.registry.ToolRegistry`
        exposes only ``resolve_tool(tool_id) -> Tool`` — a single-id
        lookup, with no "list every currently resolvable id" capability
        to draw from. Extending this to include real, pack-declared
        tools needs that capability built first (a real, disclosed gap,
        not an oversight). The three Git tool descriptors are included
        only when a real ``git_service`` was actually injected — an
        honest answer, not a standing claim this adapter cannot back."""
        descriptors: tuple[ToolDescriptor, ...] = (PLATFORM_SANDBOX_RUN_COMMAND_DESCRIPTOR,)
        if self._git_service is not None:
            descriptors += (
                PLATFORM_GIT_COMMIT_DESCRIPTOR,
                PLATFORM_GIT_CREATE_BRANCH_DESCRIPTOR,
                PLATFORM_GIT_PUSH_DESCRIPTOR,
            )
        return descriptors

    async def invoke(
        self, tool_id: str, inputs: dict[str, Any], *, timeout_seconds: float | None = None
    ) -> ToolResult:
        git_service = self._git_service
        if tool_id in _GIT_TOOL_IDS and git_service is not None:
            return await self._invoke_git_tool(tool_id, inputs, git_service)
        if tool_id != PLATFORM_SANDBOX_RUN_COMMAND:
            return await self._invoke_registered_tool(tool_id, inputs)

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
        command = _resolve_python_interpreter(inputs["command"], self._sandbox)
        result = await self._sandbox.execute(
            command=command,
            working_directory=Path(inputs["working_directory"]),
            timeout_seconds=effective_timeout_seconds,
            max_output_bytes=inputs["max_output_bytes"],
            env=inputs.get("env"),
            stdin=stdin_str.encode() if stdin_str is not None else None,
        )
        return _sandbox_result_to_tool_result(result)

    async def _invoke_git_tool(
        self, tool_id: str, inputs: dict[str, Any], service: GitIntegrationService
    ) -> ToolResult:
        """Dispatches one of the three real Git tool ids to ``service``
        (already narrowed non-``None`` by :meth:`invoke`) — the full
        stack this Tool exists to prove: an agent's
        ``context.tools.invoke(tool_id, ...)`` call
        reaches this adapter, which reaches the real
        :class:`~ai_os_kernel.git_integration.service.
        GitIntegrationService`, which reaches the real
        :class:`~ai_os_kernel.sandbox.executor.SandboxExecutor`, which
        runs a real ``git`` subprocess — never a shortcut that bypasses
        the service's own policy/audit logic.

        **Resolution-time validation raises, matching the sandbox shim
        path exactly** — malformed ``inputs`` is a call that could never
        have been dispatched, not an execution-time failure."""
        descriptor = {
            PLATFORM_GIT_COMMIT: PLATFORM_GIT_COMMIT_DESCRIPTOR,
            PLATFORM_GIT_CREATE_BRANCH: PLATFORM_GIT_CREATE_BRANCH_DESCRIPTOR,
            PLATFORM_GIT_PUSH: PLATFORM_GIT_PUSH_DESCRIPTOR,
        }[tool_id]
        errors = sorted(
            Draft202012Validator(descriptor.input_schema).iter_errors(inputs),
            key=lambda e: list(map(str, e.path)),
        )
        if errors:
            lines = [f"  - {'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors]
            raise ValueError(
                f"inputs for tool_id {tool_id!r} do not satisfy its declared input_schema:\n"
                + "\n".join(lines)
            )

        started = time.monotonic()
        try:
            if tool_id == PLATFORM_GIT_COMMIT:
                commit_result = await service.commit(
                    workspace=Path(inputs["workspace"]),
                    message=inputs["message"],
                    actor_id=inputs["actor_id"],
                    actor_type=inputs["actor_type"],
                    trace_id=inputs.get("trace_id"),
                )
                outputs: dict[str, Any] = {
                    "commit_sha": commit_result.commit_sha,
                    "branch": commit_result.branch,
                }
            elif tool_id == PLATFORM_GIT_CREATE_BRANCH:
                branch_result = await service.create_branch(
                    workspace=Path(inputs["workspace"]),
                    branch_name=inputs["branch_name"],
                    actor_id=inputs["actor_id"],
                    actor_type=inputs["actor_type"],
                    trace_id=inputs.get("trace_id"),
                )
                outputs = {"branch": branch_result.branch, "created": branch_result.created}
            else:
                push_kwargs: dict[str, Any] = {
                    "workspace": Path(inputs["workspace"]),
                    "branch": inputs["branch"],
                    "remote_url": inputs["remote_url"],
                    "actor_id": inputs["actor_id"],
                    "actor_type": inputs["actor_type"],
                    "trace_id": inputs.get("trace_id"),
                }
                remote_name = inputs.get("remote_name")
                if remote_name is not None:
                    push_kwargs["remote_name"] = remote_name
                push_result = await service.push(**push_kwargs)
                outputs = {"remote": push_result.remote, "branch": push_result.branch}
        except ProtectedBranchPushRefusedError as exc:
            return _failure_tool_result(
                PermanentError("git.protected_branch_refused", str(exc)),
                duration_ms=round((time.monotonic() - started) * 1000),
            )
        except GitOperationFailedError as exc:
            return _failure_tool_result(
                PermanentError("git.operation_failed", str(exc)),
                duration_ms=round((time.monotonic() - started) * 1000),
            )

        return ToolResult(
            status=ToolStatus.SUCCESS,
            outputs=outputs,
            error=None,
            exit_code=None,
            stdout="",
            stderr="",
            timed_out=False,
            truncated=False,
            duration_ms=round((time.monotonic() - started) * 1000),
        )

    async def _invoke_registered_tool(self, tool_id: str, inputs: dict[str, Any]) -> ToolResult:
        """Resolves ``tool_id`` through the real, injected
        :class:`~ai_os_kernel.workflow_engine.registry.ToolRegistry`
        and invokes the result — this ticket's own real deliverable, in
        place of the ``UnknownToolError`` every non-shim ``tool_id``
        raised before it.

        **Resolution failures raise, matching this adapter's own
        existing convention for the shim path** (an unknown ``tool_id``
        or malformed ``inputs`` already raised directly, never returned
        as a ``ToolResult`` failure) — a pack whose tool is not
        registered, or whose pack is not activated, or that declares
        `tier1_sandboxed` without a real sandbox behind it
        (:class:`~ai_os_kernel.workflow_engine.errors.ToolSandboxRequiredError`,
        left to propagate unchanged — the identical real, named Kernel
        error :class:`~ai_os_kernel.workflow_engine.step_executor.
        ToolStepExecutor` already raises for the identical condition)
        could never have been dispatched at all. Only a genuine
        execution-time failure — the resolved tool's own ``execute()``
        raising, or its output failing its declared ``output_schema`` —
        becomes a real ``ToolResult(status=FAILURE)``, the same
        "resolution errors raise, execution errors return" split the
        shim path already draws between a bad-``inputs`` ``ValueError``
        and a failed sandboxed command.
        """
        if self._registry is None:
            raise UnknownToolError(
                f"tool_id {tool_id!r} is not known to this adapter — no ToolRegistry was "
                f"supplied at construction, so only {PLATFORM_SANDBOX_RUN_COMMAND!r} is "
                f"invokable (see {type(self).__name__}.available_tools())"
            )

        try:
            tool = await self._registry.resolve_tool(tool_id)
        except (ToolNotRegisteredError, PackNotActivatedError, ToolRegistryError) as exc:
            raise UnknownToolError(f"tool_id {tool_id!r} could not be resolved: {exc}") from exc

        if tool.trust_tier is KernelTrustTier.TIER1_SANDBOXED:
            is_sandbox_backed = isinstance(tool, SandboxBackedTool) and tool.sandbox is not None
            if not is_sandbox_backed:
                raise ToolSandboxRequiredError(
                    f"tool_id {tool_id!r} declares trust_tier='tier1_sandboxed' but is not "
                    "genuinely backed by a real SandboxExecutor (ADR-0016) — a "
                    "tier1_sandboxed tool must expose a real, working `sandbox` attribute "
                    "to be dispatched"
                )

        started = time.monotonic()
        try:
            outputs = await tool.execute(inputs)
        except Exception as exc:  # a resolved tool's own code, not this adapter's
            return _failure_tool_result(
                TransientError("tool.execution_failed", f"tool_id {tool_id!r}: {exc}"),
                duration_ms=round((time.monotonic() - started) * 1000),
            )

        errors = sorted(
            Draft202012Validator(tool.output_schema).iter_errors(outputs),
            key=lambda e: list(map(str, e.path)),
        )
        if errors:
            lines = [f"  - {'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors]
            return _failure_tool_result(
                PermanentError(
                    "tool.output_invalid",
                    f"tool_id {tool_id!r} output does not satisfy its declared "
                    "output_schema:\n" + "\n".join(lines),
                ),
                duration_ms=round((time.monotonic() - started) * 1000),
            )

        return ToolResult(
            status=ToolStatus.SUCCESS,
            outputs=outputs,
            error=None,
            exit_code=None,
            stdout="",
            stderr="",
            timed_out=False,
            truncated=False,
            duration_ms=round((time.monotonic() - started) * 1000),
        )
