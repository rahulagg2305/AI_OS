"""The minimal Tool contract the Workflow Engine needs to invoke a
Tool-type step.

Grounded in ``platform_sdk/schemas/manifest.schema.json`` ``tools[]``
— the authoritative Tool Contract — which requires ``id``, ``name``,
``version``, ``description``, ``entrypoint``, ``inputSchema``,
``outputSchema``, and ``trustTier``. Of these, only what an in-process
*invocation* actually needs is modelled here: ``output_schema`` (the
required ``outputSchema``) and ``trust_tier`` (the required
``trustTier``, exactly the two enum values the schema defines). The
rest — ``id``, ``name``, ``version``, ``description``, ``entrypoint``
— are pack manifest registration metadata, not part of calling a tool
that is already resolved to a Python object; inventing them here would
duplicate the Manifest Loader's job, not extend the invocation
contract.

``input_schema`` is excluded for the same reason it was excluded from
the Agent contract (:mod:`ai_os_kernel.workflow_engine.agent`): no
per-step input-mapping mechanism exists yet, so there is nothing real
to validate — the executor always invokes a tool with no inputs.

**A real Sandbox Executor now exists** (:mod:`ai_os_kernel.sandbox`), so
``trust_tier`` is no longer declared-but-unenforceable for every tool —
:class:`~ai_os_kernel.workflow_engine.step_executor.ToolStepExecutor`
now dispatches a ``tier1_sandboxed`` tool when, and only when, it is
genuinely backed by one (:class:`SandboxBackedTool` below). A
``tier1_sandboxed`` tool that is *not* genuinely sandbox-backed is
still refused outright — the guard is narrowed for tools that earn it,
not weakened in general.
"""

from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from ai_os_kernel.sandbox.executor import SandboxExecutor


class TrustTier(StrEnum):
    """Exactly the two values in
    ``manifest.schema.json`` ``tools[].trustTier``."""

    TIER1_SANDBOXED = "tier1_sandboxed"
    TIER2_TRUSTED = "tier2_trusted"


@runtime_checkable
class Tool(Protocol):
    """One unit of work invoked by a Tool-type step. Trivial and
    in-process by default (:class:`EchoTool`); a ``tier1_sandboxed``
    implementation may genuinely execute an external command through a
    :class:`SandboxExecutor <ai_os_kernel.sandbox.executor.SandboxExecutor>`
    (:class:`SandboxBackedTool` below, :class:`~ai_os_kernel.
    workflow_engine.sandboxed_tool.SandboxedCommandTool`).

    ``@runtime_checkable`` so
    :class:`~ai_os_kernel.workflow_engine.registry.SqlToolRegistry` can
    ``isinstance``-check a dynamically loaded entrypoint before handing
    it back — a structural presence check only (does it have
    ``trust_tier``/``output_schema``/``execute``), not a signature or
    type check, but enough to turn "an entrypoint resolved to something
    unrelated" into a clear error instead of a confusing failure the
    first time something calls ``.execute()``.
    """

    trust_tier: TrustTier
    output_schema: dict[str, Any]

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]: ...


@runtime_checkable
class SandboxBackedTool(Protocol):
    """A :class:`Tool` that genuinely delegates its execution to an
    injected :class:`~ai_os_kernel.sandbox.executor.SandboxExecutor` —
    the structural marker :class:`~ai_os_kernel.workflow_engine.
    step_executor.ToolStepExecutor` checks before dispatching a
    ``tier1_sandboxed`` tool, instead of refusing it outright.

    ``@runtime_checkable`` for the identical reason :class:`Tool`
    itself is: a structural presence check only (does it expose a
    ``sandbox`` attribute), not proof that the attribute genuinely
    holds a working sandbox — :class:`ToolStepExecutor` additionally
    checks it is not ``None`` before trusting it. A ``tier1_sandboxed``
    tool that does not satisfy this Protocol is still refused outright;
    this narrows the existing ADR-0016 guard for tools that earn it, it
    does not weaken it for any other tool.
    """

    sandbox: SandboxExecutor


class EchoTool:
    """The one trivial in-process tool implementation for this step.

    Does no real work and never will need to — it exists to prove the
    invocation path (call, validate, return) works end to end.

    ``trust_tier`` defaults to ``tier2_trusted`` because a directly
    constructed ``EchoTool()`` genuinely is: it executes no command,
    compiles nothing, and processes no untrusted content (the ADR-0016
    conditions that would require ``tier1_sandboxed``). It is
    constructor-settable, not a fixed class attribute, so a test (or an
    entrypoint pointing at this same class) can honestly declare either
    tier — :class:`~ai_os_kernel.workflow_engine.registry.SqlToolRegistry`
    checks that a loaded tool's own ``trust_tier`` agrees with what
    ``catalog.tools`` records for it, rather than trusting either value
    alone; an ``EchoTool`` used as a real entrypoint must be constructed
    with the tier the catalog actually declares.
    """

    output_schema: dict[str, Any] = {
        "type": "object",
        "properties": {"result": {"const": "ok"}},
        "required": ["result"],
        "additionalProperties": False,
    }

    def __init__(self, trust_tier: TrustTier = TrustTier.TIER2_TRUSTED) -> None:
        self.trust_tier = trust_tier

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"result": "ok"}
