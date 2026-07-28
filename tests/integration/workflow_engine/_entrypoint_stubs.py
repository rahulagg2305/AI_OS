"""Small local stub Agent/Tool classes used only as real, importable
``entrypoint`` targets for ``SqlAgentRegistry``/``SqlToolRegistry``
integration tests (``tests/integration/workflow_engine/test_registry.py``).

Not a test module itself (no ``test_*`` functions) — this exists purely
to be a genuinely importable module, so its classes are valid
``module.path:ClassName`` entrypoints, proving entrypoint loading works
against something other than the production ``EchoAgent``/``EchoTool``
classes.
"""

from typing import Any

from ai_os_kernel.workflow_engine.tool import TrustTier


class NamedStubAgent:
    """Returns its own name in the output, so a test can prove which
    registered agent's entrypoint actually loaded and ran."""

    output_schema: dict[str, Any] = {
        "type": "object",
        "properties": {"ranAs": {"type": "string"}},
        "required": ["ranAs"],
        "additionalProperties": False,
    }

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"ranAs": "NamedStubAgent"}


class SandboxedStubTool:
    """A tool whose own code honestly declares ``tier1_sandboxed`` as a
    fixed default — proving a catalog row can declare the same tier and
    have it agree, without needing constructor arguments (the loader
    always constructs with none)."""

    trust_tier: TrustTier = TrustTier.TIER1_SANDBOXED
    output_schema: dict[str, Any] = {"type": "object"}

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return {}


class MismatchedTrustTierStubTool:
    """A tool whose own code declares ``tier1_sandboxed`` — used to seed
    a catalog row that declares the *other* tier, proving
    ``SqlToolRegistry`` rejects the disagreement rather than trusting
    either side silently."""

    trust_tier: TrustTier = TrustTier.TIER1_SANDBOXED
    output_schema: dict[str, Any] = {"type": "object"}

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return {}


class NotAnAgentOrTool:
    """A real, importable class that satisfies neither the Agent nor
    the Tool Protocol — used to prove an entrypoint resolving to
    something structurally unrelated is rejected clearly."""

    def __init__(self) -> None:
        self.nothing_relevant = True
