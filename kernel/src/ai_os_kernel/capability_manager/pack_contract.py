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
— almost none of which exist as real Kernel services yet (there is no
Tool Invoker, no Event Bus consumer, no Workspace Service, no
Traceability Engine writer, no Quality Gate Registry, no Speech
Gateway). Building a faithful ``PackContext`` is Platform SDK v1.0.0's
own explicitly-scoped, large, still-unbuilt initiative (see
``implementation_status.md``) — inventing stand-in types for a dozen
services this codebase does not have would itself be "invented
architecture," not a reduced slice of a real one. This module
implements only what the first real pack's own agent genuinely needs:
identity (``pack_id: str``, ``pack_version: str`` on ``PackContext``)
and nothing else. A future Platform SDK step adds fields to
``PackContext``/``PackRegistration`` as each underlying service becomes
real — additive, not a redesign of this module's own shape, the
identical "reduced slice now, additive later" precedent already used
throughout this codebase (``TraceContext``, ``ContextRequest``,
``ProviderCapabilities``).

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


class PackContext(BaseModel):
    """What a pack's ``activate()`` receives. Reduced to identity only
    — see this module's own docstring for exactly which of
    platform_sdk.md §6's fourteen optional service attributes are
    deferred, and why none of them are faked here."""

    model_config = ConfigDict(frozen=True)

    pack_id: str
    pack_version: str


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
