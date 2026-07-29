"""The ``CapabilityPack`` entry point contract every pack manifest with
a non-empty ``agents``/``workflows`` array must satisfy
(platform_sdk.md §7, and the manifest schema's own ``allOf`` rule:
``entryPoint`` is required the moment a manifest declares any agent or
workflow).

**A deliberately reduced slice of platform_sdk.md §6/§7 — recorded
explicitly, not silently narrowed.** The full ``PackContext`` documented
there carries fourteen optional service attributes (``llm``, ``prompts``,
``context``, ``retrieval``, ``memory``, ``tools`` (a real Tool
Invoker), ``events``, ``config``, ``secrets``, ``storage``,
``workspace``, ``telemetry``, ``traceability``, ``gates``, ``speech``)
— most of which still do not exist as real Kernel services (there is no
Event Bus consumer, no Workspace Service, no Traceability Engine writer,
no Quality Gate Registry, no Speech Gateway). Building a fully faithful
``PackContext`` remains Platform SDK v1.0.0's own explicitly-scoped,
still-unfinished initiative (see ``implementation_status.md``) —
inventing stand-in types for services this codebase does not have would
itself be "invented architecture," not a reduced slice of a real one.

**Extended additively, exactly as this docstring already anticipated,
the moment the underlying services became real
(``platform_sdk_v1_scope.md`` step 6b, following step 6a's real Kernel
adapters):** ``llm``/``prompts``/``tools`` now carry real
:class:`~ai_os_sdk.contracts.LLMGateway`/:class:`~ai_os_sdk.contracts.PromptRegistry`/
:class:`~ai_os_sdk.contracts.ToolInvoker`-satisfying instances (the
step-6a adapters, via :func:`~ai_os_kernel.sdk_adapters.pack_context.build_pack_context`)
— present **only** when the entrypoint's own declared permissions
actually grant them (``llm``/``prompts`` together, gated on
``llm:invoke``; ``tools``, gated on ``sandbox:execute`` — see that
builder's own docstring for the full reasoning and the one simplification
still open: a Pydantic field defaulting to ``None`` is not quite §6's own
literal "the attribute is absent from the object," a distinction
deliberately left for whichever future step gives ``PackContext`` its
real, final home). The other eleven attributes remain absent — not
merely ``None`` typed, not present on this model at all — for the
identical "nothing real to back it yet" reason as before.

**Still Kernel-side, not yet relocated into ``ai_os_sdk`` — a deliberate,
documented sequencing, not an oversight.** ``platform_sdk.md`` §7 and
``platform_sdk_v1_scope.md``'s own step table assign *landing the
entry-point contract* (``PackContext``/``CapabilityPack``/
``PackRegistration``/``HealthReport``, formally, in ``ai_os_sdk``) to
step 7 — moving this class, now three fields richer, into the SDK so a
real pack's ``activate()`` can reference it without importing the Kernel
is that step's job, not this one's. Nothing in this codebase calls
``CapabilityPack.activate()`` yet (see below), and step 6b deliberately
proves its own injection mechanism against a **test** entrypoint, not a
real migrated pack agent — test code is not subject to the "a pack may
only import ``ai_os_sdk``" rule, so this class living here in the
meantime blocks nothing step 6b needs to prove. A future Platform SDK
step adds any further fields to ``PackContext``/``PackRegistration`` as
each remaining underlying service becomes real — additive, not a
redesign of this module's own shape, the identical "reduced slice now,
additive later" precedent already used throughout this codebase
(``TraceContext``, ``ContextRequest``, ``ProviderCapabilities``).

**Nothing in this codebase calls ``CapabilityPack.activate()`` yet —
a real, discovered, and recorded gap, not simulated here.**
:class:`~ai_os_kernel.capability_manager.repository.SqlPackLifecycleRepository`
only ever flips ``catalog.packs.state`` and records a transition; it
does not parse a manifest's ``agents``/``tools``/``workflows`` arrays
into ``catalog.agents``/``catalog.tools`` rows, and nothing calls a
pack's own ``entryPoint`` class at all. That automated "Manifest Loader
discovers a pack -> writes catalog rows -> calls
``CapabilityPack.activate(context)``" pipeline is a distinct, larger,
future Capability Manager increment (a real pack installer). Until it
exists, ``catalog.agents``/``catalog.tools`` rows are written directly
by whatever process needs them real today (a test, or eventually that
installer) — the identical situation already true for every other
catalog table's own writer-less history in this project.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict

from ai_os_kernel.workflow_engine.agent import Agent
from ai_os_kernel.workflow_engine.tool import Tool
from ai_os_sdk.contracts import LLMGateway, PromptRegistry, ToolInvoker


class PackContext(BaseModel):
    """What a pack's ``activate()`` — or, as of step 6b, a
    :class:`~ai_os_sdk.contracts.PackContextReceiver`-implementing
    entrypoint's ``bind_pack_context`` — receives. Identity plus the
    three service attributes step 6a made real; see this module's own
    docstring for exactly which of platform_sdk.md §6's remaining eleven
    optional service attributes are still deferred, and why none of them
    are faked here."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    pack_id: str
    pack_version: str
    llm: LLMGateway | None = None
    prompts: PromptRegistry | None = None
    tools: ToolInvoker | None = None


class PackRegistration(BaseModel):
    """What a pack's ``activate()`` returns. Reduced to ``agents``
    only — this pack declares no tools, workflows, gates, or commands;
    those dict fields are added the same additive way once a pack that
    actually provides one exists, mirroring how ``tools``/``workflows``
    were absent from ``WorkflowStep`` until a step type needed them."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    agents: dict[str, Agent]
    tools: dict[str, Tool] = {}


class HealthReport(BaseModel):
    """A pack's own self-reported health (platform_sdk.md §7). Reduced
    to a status only — capability_pack_contract.md's own "Health
    Contract" also names loaded components/dependency status/
    configuration status/startup validation as things health *should*
    include, none of which this pack's one agent has anything real to
    report yet (it has no eagerly-loaded dependencies to check — see
    :mod:`ai_os_pack_software_engineering.agents.architecture`'s own
    lazy-construction docstring)."""

    model_config = ConfigDict(frozen=True)

    status: Literal["healthy", "degraded", "unhealthy"]
    details: dict[str, Any] = {}


class CapabilityPack(Protocol):
    """The entry point every pack manifest's ``entryPoint`` names
    (platform_sdk.md §7). Not ``@runtime_checkable`` — unlike
    ``Agent``/``Tool``, nothing in this codebase yet loads and
    ``isinstance``-checks an ``entryPoint`` at runtime (see this
    module's own docstring), so there is no real caller this step needs
    a structural check for."""

    pack_id: str
    version: str

    async def activate(self, context: PackContext) -> PackRegistration: ...

    async def deactivate(self) -> None: ...

    async def health(self) -> HealthReport: ...
