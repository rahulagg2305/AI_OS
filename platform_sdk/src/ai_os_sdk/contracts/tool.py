"""The ``Tool`` Protocol and its ``TrustTier`` vocabulary
(``platform_sdk.md`` §4.3).

**This is the narrowed v1.0.0 shape**, per that section's dated
*v1.0.0 Reconciliation Decision* block (recorded 2026-07-29,
``platform_sdk_v1_scope.md`` step 2a). §4.3's prose specifies
``invoke(request: ToolRequest) -> ToolResult``; the real, working Kernel
contract is ``execute(inputs: dict) -> dict``. Note that this is a
difference of **method name**, not merely of signature, so the two are
not interchangeable at all — which is precisely why this had to be
decided before any Protocol was written.

``ToolRequest`` is **not defined in v1.0.0** (no consumer under this
shape). ``ToolResult`` *is* needed, but it belongs to step 6 alongside
``ToolInvoker`` (§5.6), which is its only consumer — not here.

**Two distinct paths, kept deliberately separate.** This ``Tool``
Protocol is the contract for a *pack-declared tool executed by the
Workflow Engine as a ``tool``-type step*. It is **not** how an agent
causes a side effect — that is ``ToolInvoker`` (§5.6), whose v1.0.0
adapter is built directly over the sandbox rather than over this
Protocol, so that a typed sandbox result is never flattened into a dict
and re-parsed. See §5.6's decision block.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol, runtime_checkable


class TrustTier(StrEnum):
    """The two-value closed vocabulary from
    ``platform_sdk/schemas/manifest.schema.json``'s own
    ``tools[].trustTier`` enum — the authoritative artifact, which is
    also what ``ai_os_kernel.workflow_engine.tool.TrustTier`` mirrors.

    **Defined here rather than imported.** ``platform_sdk.md`` §2 rule 1
    makes this SDK the dependency floor: it depends on no other AI_OS
    distribution, so it cannot import the Kernel's equivalent enum. Both
    enums independently mirror the same JSON Schema, which is what keeps
    them in agreement; the schema is the single source of truth, not
    either class.

    A consequence worth stating plainly: because these are two distinct
    Python types, a Kernel-typed tool is **not statically assignable**
    to this SDK ``Tool`` Protocol, even though it satisfies it at
    runtime. Bridging that is the Kernel-side adapter's job (step 6a),
    and it is expected rather than a defect.
    """

    TIER1_SANDBOXED = "tier1_sandboxed"
    """Untrusted execution. **Mandatory** for any tool that executes a
    command, compiles, runs tests, installs dependencies, or processes
    untrusted repository content (ADR-0016, tool execution sandboxing)."""

    TIER2_TRUSTED = "tier2_trusted"
    """In-process platform operations only, under canonical-path
    allowlisting. Never for executing generated or untrusted code."""


@runtime_checkable
class Tool(Protocol):
    """One unit of side-effecting work declared by a Capability Pack.

    ``@runtime_checkable`` for the same reason, and with the same
    limitation, as :class:`~ai_os_sdk.contracts.agent.Agent`: the
    ``isinstance`` check proves *member presence only*, never signatures.

    **A tool's own ``trust_tier`` is not self-certifying.** The declaring
    manifest records a tier too, and a loader is expected to require the
    two to agree rather than trusting either alone — a divergence between
    what a tool's code claims and what its registration claims is exactly
    the inconsistency ADR-0016's sandbox guard exists to catch.
    """

    trust_tier: TrustTier
    """Which execution tier this tool requires. Validated at pack load
    (``platform_sdk.md`` §4.3)."""

    output_schema: dict[str, Any]
    """JSON Schema the tool's returned mapping is validated against by
    its caller."""

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Perform this tool's work and return its structured output."""
        ...
