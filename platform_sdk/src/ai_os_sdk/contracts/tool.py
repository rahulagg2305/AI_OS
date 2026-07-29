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

``TrustTier`` itself now lives in :mod:`ai_os_sdk.models.tool`, moved
there in step 6 once ``ToolDescriptor`` needed it too — a model cannot
depend on a contract without inverting this package's own layering.
Re-exported here unchanged, so nothing built against
``ai_os_sdk.contracts.tool.TrustTier`` in steps 3–5 breaks.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ai_os_sdk.models.tool import TrustTier

__all__ = ["Tool", "TrustTier"]


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
