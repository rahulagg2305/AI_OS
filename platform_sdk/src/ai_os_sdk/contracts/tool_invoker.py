"""The ``ToolInvoker`` Protocol and the ``platform.sandbox.run_command``
tool concept (``platform_sdk.md`` §5.6).

**This is a from-scratch design, not a narrowing or extension** — per
§5.6's dated *v1.0.0 Reconciliation Decision* block (recorded
2026-07-29, ``platform_sdk_v1_scope.md`` step 2a). Nothing in the
Kernel implements a pack-facing tool registry today, so there is
nothing to reconcile against; there is a real problem to solve instead.

**The problem, verified against real source:**

1. The one real pack declares **zero** tools
   (``capability_packs/software-engineering/manifest.yaml`` lines
   71-73: ``permissions: [llm:invoke, sandbox:execute]``, no ``tools:``
   entries) — a pack-tool registry has nothing to resolve, so
   :func:`available_tools` would answer with an empty tuple.
2. The one real tool **ignores its own inputs**:
   ``ai_os_kernel.workflow_engine.sandboxed_tool.SandboxedCommandTool.execute(inputs)``
   never reads ``inputs`` at all — the command, working directory,
   timeout, and output cap are all baked in at construction, which is
   why the three sandbox-using agents construct a fresh tool per call
   instead of invoking a registered one.

**The resolution kept in this Protocol's design:** the sandbox runner
becomes a *platform-provided* tool with the well-known id
:data:`PLATFORM_SANDBOX_RUN_COMMAND`, and the command moves from the
constructor into ``inputs`` — fixing the ignored-``inputs`` wart rather
than propagating it, and giving :func:`available_tools` a real,
non-empty answer.

**What step 6a's adapter builds, not this step.** The real Kernel-side
implementation of this Protocol is constructed **directly over**
``ai_os_kernel.sandbox.executor.SandboxExecutor``, never over the
dict-based :class:`~ai_os_sdk.contracts.tool.Tool` Protocol — routing
through a dict-returning ``Tool`` would mean serialising a typed
``SandboxResult`` into a dict and re-parsing it, losing exactly the
``timed_out``/``truncated`` distinctions :class:`~ai_os_sdk.models.tool.ToolResult`
exists to preserve. This step defines the contract those adapters must
satisfy; it builds none of them.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ai_os_sdk.models.tool import ToolDescriptor, ToolResult, TrustTier

PLATFORM_SANDBOX_RUN_COMMAND = "platform.sandbox.run_command"
"""The one real tool id v1.0.0 defines — a platform-provided sandboxed
command runner, not a pack-declared tool. Grounds
:class:`ToolInvoker.available_tools` in a real, concrete answer."""

PLATFORM_PYTHON_INTERPRETER = "{platform.python}"
"""A well-known placeholder token a caller may use as any element of
``inputs["command"]`` in place of a literal Python interpreter path
(``platform_sdk_v1_scope.md``'s inserted step 12a, closing a real
regression step 12 found and recorded).

**The problem this restores.** Before the Platform SDK existed, an agent
that needed to run a Python script inside its own injected
``SandboxExecutor`` asked that object for its own
``python_command`` property (``sys.executable`` for
``LocalSubprocessSandbox``, ``python3`` for ``DockerSandbox`` — a real
fact that genuinely differs by backend). Once migrated onto
``ToolInvoker``, an agent no longer holds a ``SandboxExecutor`` at all —
only this deliberately backend-agnostic Protocol, which has no
``python_command`` concept and cannot answer the question. Step 12
(``build`` agent) worked around this with a constructor-time default
(``("python3",)``) — correct for ``DockerSandbox``, the real system-wide
default, but silently wrong the moment ``AIOS_SANDBOX_BACKEND=local`` is
set without also updating that default: a real, documented regression
from the pre-migration behaviour, which was always automatically
correct because it asked the real, active sandbox directly.

**The fix.** A conforming :class:`ToolInvoker` implementation
substitutes every occurrence of this token in ``inputs["command"]`` with
the real, current backend's own portable interpreter invocation
*before* dispatching — restoring the "always automatically correct,
no caller-side guessing" guarantee at the one layer that actually still
holds the real ``SandboxExecutor`` object (the adapter, never the pack
agent). A caller writes ``[PLATFORM_PYTHON_INTERPRETER, "-c", script]``
exactly once and it is correct against *every* backend, present or
future, with zero backend-specific knowledge and no constructor default
of its own to keep in sync. ``python_command`` may be more than one
token (e.g. a future ``("py", "-3")``); a conforming implementation
expands the placeholder into every token, not a strict 1:1 replacement.

**Deliberately not a general-purpose templating mechanism.** This is
one specific, named, documented substitution for one specific, real,
recurring need (every ``PromptedAgent``-descended write-a-file agent in
this pack needs a portable interpreter invocation) — not a precedent
for arbitrary ``{...}`` interpolation in tool commands, which would
reopen exactly the "agent reaching for a side effect by any means other
than the declared Protocol" risk :class:`ToolInvoker`'s own docstring
already warns against.
"""

_RUN_COMMAND_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "command": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "working_directory": {"type": "string"},
        "timeout_seconds": {"type": "number", "exclusiveMinimum": 0},
        "max_output_bytes": {"type": "integer", "exclusiveMinimum": 0},
        "env": {"type": ["object", "null"]},
        "stdin": {"type": ["string", "null"]},
    },
    "required": ["command", "working_directory", "timeout_seconds", "max_output_bytes"],
    "additionalProperties": False,
}
"""Mirrors ``SandboxExecutor.execute``'s own real keyword arguments
exactly (``sandbox/executor.py:151-160``) — every field this schema
requires is a field that real method already requires. This is what
moving the command into ``inputs`` (rather than the constructor) looks
like as a declared contract."""

_RUN_COMMAND_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "stdout": {"type": "string"},
        "stderr": {"type": "string"},
    },
    "required": ["stdout", "stderr"],
    "additionalProperties": False,
}
"""The ``outputs`` shape on a successful :class:`~ai_os_sdk.models.tool.ToolResult`
for this tool — everything else a real invocation reports
(``exit_code``, ``timed_out``, ``truncated``, ``duration_ms``) already
has its own named field on ``ToolResult`` itself, so it does not need
to be duplicated inside ``outputs`` too."""

PLATFORM_SANDBOX_RUN_COMMAND_DESCRIPTOR = ToolDescriptor(
    tool_id=PLATFORM_SANDBOX_RUN_COMMAND,
    trust_tier=TrustTier.TIER1_SANDBOXED,
    input_schema=_RUN_COMMAND_INPUT_SCHEMA,
    output_schema=_RUN_COMMAND_OUTPUT_SCHEMA,
)
"""The one real, concrete :class:`~ai_os_sdk.models.tool.ToolDescriptor`
v1.0.0 defines. A conforming :class:`ToolInvoker` implementation's
:func:`available_tools` is expected to include this entry."""


@runtime_checkable
class ToolInvoker(Protocol):
    """The only way an agent may cause a side effect
    (``platform_sdk.md`` §5.6). Enforces permissions, applies the trust
    tier, and records the invocation — an agent reaching for a side
    effect by any other means is exactly what this Protocol exists to
    prevent.

    ``@runtime_checkable`` for the same reason, and with the same
    limitation, as every other Protocol in this package: the
    ``isinstance`` check proves member presence only, never signatures.
    """

    async def invoke(
        self, tool_id: str, inputs: dict[str, Any], *, timeout_seconds: float | None = None
    ) -> ToolResult:
        """Invoke the tool named by ``tool_id`` with ``inputs``.

        **A deliberate, documented double timeout, not an oversight.**
        This ``timeout_seconds`` is a generic, tool-agnostic ceiling the
        invoker itself may enforce on the whole call — meaningful for a
        future tool whose own ``inputs`` declares no timeout of its
        own. :data:`PLATFORM_SANDBOX_RUN_COMMAND` also requires its own
        ``inputs["timeout_seconds"]`` (mirroring ``SandboxExecutor.
        execute``'s own required parameter), because *that* value is
        what the sandboxed command's own execution is bounded by, not
        merely the outer call. §5.6's own documented signature carries
        both; how a step 6a adapter reconciles the two when both are
        supplied for the same call (an outer ceiling tighter than the
        tool's own requested timeout, most likely) is left to that
        step, not decided here.
        """
        ...

    def available_tools(self) -> tuple[ToolDescriptor, ...]:
        """Every tool this invoker can currently dispatch to.

        Synchronous and side-effect-free — a fact lookup, unlike
        :meth:`invoke`. In v1.0.0 this includes at least
        :data:`PLATFORM_SANDBOX_RUN_COMMAND_DESCRIPTOR`; a pack-declared
        tool registry (empty today — the one real pack declares none)
        would extend this, not replace it.
        """
        ...
