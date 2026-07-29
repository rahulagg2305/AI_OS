"""The ``CapabilityPack`` entry-point contract (``platform_sdk.md`` §6,
§7, ``platform_sdk_v1_scope.md`` step 7) — ``PackContext``,
``PackRegistration``, ``HealthReport``, and the ``CapabilityPack``
Protocol itself, formally landed in the SDK.

**Relocated from ``ai_os_kernel.capability_manager.pack_contract``,
additively, not redesigned — exactly as that module's own docstring
promised before this step touched it, and exactly as step 6b's own
record (``platform_sdk_v1_scope.md`` §6h) already announced this step
would do.** The Kernel-side module now re-exports these same classes
rather than defining its own — see its own docstring for the
compatibility-shim shape this leaves behind, and why real pack source
(``ai_os_pack_software_engineering.pack``) is deliberately left
importing the Kernel path unchanged (migrating that import onto this
module directly is step 14's own explicitly scoped job, not this one's).

**A real, discovered layering correction, made here rather than
silently — these four types live in ``contracts/``, not ``models/``,
reversing what this package's own ``models/__init__.py`` docstring
speculatively planned before this step was ever built.** Every other
real "boundary model" in this SDK (``LLMRequest``, ``ToolResult``,
``RenderedPrompt``, ...) is pure data — no field ever types itself
against another Protocol in this package, so ``models/`` never needs to
import ``contracts/``, and every real ``contracts/*.py`` module imports
*from* ``models/``, never the reverse. ``PackContext``/``PackRegistration``
are not that kind of model: by definition, they exist to carry *other
Protocol instances* — ``PackContext.llm: LLMGateway``,
``PackContext.prompts: PromptRegistry``, ``PackContext.tools:
ToolInvoker``, ``PackRegistration.agents: dict[str, Agent]``,
``PackRegistration.tools: dict[str, Tool]``. Placing them in ``models/``
would force ``models/`` to import ``contracts/``, inverting every real
dependency direction this package has established so far. Landing them
in ``contracts/`` instead — alongside the ``CapabilityPack`` Protocol
that already needs ``PackContext``/``PackRegistration`` as its own
method's parameter/return types — costs nothing extra and creates no
new cycle. ``ai_os_sdk.models.__init__``'s own docstring is corrected in
the same step that discovered this, not left describing a file this
package will never actually add.

**``PackRegistration.agents``/``tools`` are typed against *this SDK's
own* ``Agent``/``Tool`` Protocols (:mod:`ai_os_sdk.contracts.agent`/
:mod:`ai_os_sdk.contracts.tool`), not the Kernel's internal ones.** Step
3 narrowed both to the identical dict-based shape the Kernel's own
``workflow_engine.agent.Agent``/``workflow_engine.tool.Tool`` already
use, and proved every real pack agent/tool satisfies the SDK's version
by ``isinstance`` — so a real Kernel agent/tool instance placed in this
model's dict fields validates against the SDK Protocol exactly as it
already did against the Kernel's own internal one. This module's own
tests prove that real substitution still holds, not merely assume it
carries over unchanged.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict

from ai_os_sdk.contracts.agent import Agent
from ai_os_sdk.contracts.llm_gateway import LLMGateway
from ai_os_sdk.contracts.prompt_registry import PromptRegistry
from ai_os_sdk.contracts.tool import Tool
from ai_os_sdk.contracts.tool_invoker import ToolInvoker


class PackContext(BaseModel):
    """What a pack's ``activate()`` — or, as of
    ``platform_sdk_v1_scope.md`` step 6b, a
    :class:`~ai_os_sdk.contracts.entrypoint_context.PackContextReceiver`
    -implementing entrypoint's ``bind_pack_context`` — receives. Identity
    plus the three service attributes step 6a made real
    (``llm``/``prompts``/``tools``); present only when the entrypoint's
    own declared permissions actually grant them
    (:func:`~ai_os_kernel.sdk_adapters.pack_context.build_pack_context`
    enforces this on the Kernel side, since this SDK package has no
    permission-evaluation logic of its own to enforce it here).

    The other eleven attributes ``platform_sdk.md`` §6 documents
    (``context``/``retrieval``/``memory``/``events``/``config``/
    ``secrets``/``storage``/``workspace``/``telemetry``/
    ``traceability``/``gates``/``speech``) remain absent — not merely
    ``None`` typed, not present on this model at all — because nothing
    real backs any of them yet. A future step adds fields as each
    underlying service becomes real, additively, not a redesign of this
    model's own shape — the identical precedent this class's own prior
    Kernel-side home already established.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    pack_id: str
    pack_version: str
    llm: LLMGateway | None = None
    prompts: PromptRegistry | None = None
    tools: ToolInvoker | None = None


class PackRegistration(BaseModel):
    """What a pack's ``activate()`` returns. Reduced to ``agents``/
    ``tools`` only — the one real pack declares no workflows, gates, or
    commands of its own; those dict fields are added the same additive
    way once a pack that actually provides one exists, mirroring how
    ``tools``/``workflows`` were absent from ``WorkflowStep`` until a
    step type needed them."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    agents: dict[str, Agent]
    tools: dict[str, Tool] = {}


class HealthReport(BaseModel):
    """A pack's own self-reported health (``platform_sdk.md`` §7).
    Reduced to a status only — ``capability_pack_contract.md``'s own
    "Health Contract" also names loaded components/dependency status/
    configuration status/startup validation as things health *should*
    include, none of which the one real pack's agents have anything
    real to report yet (no eagerly-loaded dependencies to check — see
    ``ai_os_pack_software_engineering.agents.architecture``'s own
    lazy-construction docstring)."""

    model_config = ConfigDict(frozen=True)

    status: Literal["healthy", "degraded", "unhealthy"]
    details: dict[str, Any] = {}


class CapabilityPack(Protocol):
    """The entry point every pack manifest's ``entryPoint`` names
    (``platform_sdk.md`` §7). Not ``@runtime_checkable`` — unlike
    ``Agent``/``Tool``, nothing in this codebase yet loads and
    ``isinstance``-checks an ``entryPoint`` at runtime (see this
    module's own docstring), so there is no real caller this step needs
    a structural check for."""

    pack_id: str
    version: str

    async def activate(self, context: PackContext) -> PackRegistration: ...

    async def deactivate(self) -> None: ...

    async def health(self) -> HealthReport: ...
