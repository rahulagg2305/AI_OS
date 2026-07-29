"""Minimal in-process registry resolving a declared ``agentId``/
``toolId`` (workflow_architecture.md's Step Contract) to a real,
already-constructed :class:`~ai_os_kernel.workflow_engine.agent.Agent`
or :class:`~ai_os_kernel.workflow_engine.tool.Tool` instance — the seam
that lets :class:`~ai_os_kernel.workflow_engine.step_executor.
AgentStepExecutor`/:class:`~ai_os_kernel.workflow_engine.step_executor.
ToolStepExecutor` dispatch to the *specific* agent/tool a step names,
instead of always the one instance a step executor used to be
constructed with.

Deliberately **not** the Capability Manager (kernel_architecture.md:
"Controls installation, activation, deactivation, upgrades and health
of Capability Packs"). There is no pack install/upgrade lifecycle, no
health monitoring, and no permissions enforcement here — only a lookup
from a declared id to an already-constructed instance, now gated by one
single fact about the owning pack (its ``catalog.packs.state`` must be
``activated``, capability_manager.md §4's one sentence about what
``activated`` actually means: "components available to the Workflow
Engine"). Building the rest is explicitly out of scope for this step; a
real Capability-Manager-backed registry is the natural second
implementation of these same two Protocols later (Stage C).

Two separate Protocols, not one combined "capability" Protocol,
mirroring the existing separation between
:class:`~ai_os_kernel.workflow_engine.agent.Agent` and
:class:`~ai_os_kernel.workflow_engine.tool.Tool` themselves —
:class:`~ai_os_kernel.workflow_engine.step_executor.AgentStepExecutor`
only ever needs to resolve agents, never tools, and
:class:`~ai_os_kernel.workflow_engine.step_executor.ToolStepExecutor`
only ever needs the reverse (Interface Segregation).

Both Protocol methods are ``async`` — even the in-memory implementation
below does no I/O, but :class:`SqlAgentRegistry`/:class:`SqlToolRegistry`
genuinely need it, the same forward-looking shape already used for
:class:`~ai_os_kernel.prompt_engine.renderer.PromptEngine`/
:class:`~ai_os_kernel.llm_gateway.gateway.LLMGateway`.

**`SqlAgentRegistry`/`SqlToolRegistry`** are a second implementation of
each Protocol, backed by ``catalog.agents``/``catalog.tools`` —
mirroring :class:`~ai_os_kernel.prompt_engine.catalog.SqlPromptCatalog`'s
own shape as closely as this domain allows: look up one row by its
natural key, fail cleanly if it is missing or the query itself fails.
They confirm a declared id is a *real, registered catalog row*, then
check that its declared ``pack_id`` names a real ``catalog.packs`` row
whose ``state`` is
:attr:`~ai_os_kernel.workflow_engine.pack_state.PackState.ACTIVATED`
(one ``LEFT JOIN`` per lookup, not a second round trip) — a missing
pack row or a non-``activated`` state raises
:class:`~ai_os_kernel.workflow_engine.errors.PackNotActivatedError`
*before* anything is imported. Only once that gate passes do they use
:class:`~ai_os_kernel.workflow_engine.entrypoint_loader.
EntrypointLoader` to load and construct the row's own declared
``entrypoint`` — a real implementation now, not always the trivial
:class:`~ai_os_kernel.workflow_engine.agent.EchoAgent`/
:class:`~ai_os_kernel.workflow_engine.tool.EchoTool` stand-ins
:class:`InMemoryAgentRegistry`/:class:`InMemoryToolRegistry` still use
(those two never check pack state at all — there is no pack for a
caller-supplied mapping entry to belong to). The loaded object is
validated against the ``Agent``/``Tool`` Protocol via ``isinstance``
(both are ``@runtime_checkable``) before being returned — an entrypoint
resolving to something structurally unrelated is a clear registry
error, not a confusing failure the first time something calls
``.execute()``. For tools, the loaded object's own ``trust_tier`` must
agree with what ``catalog.tools`` records for it — this registry trusts
neither value alone, since a divergence between what a tool's own code
declares and what its catalog registration declares is exactly the
kind of inconsistency ADR-0016's sandbox guard exists to catch, not
paper over.

**Real as of ``platform_sdk_v1_scope.md`` step 9a: the ``PackContextReceiver``
injection this Kernel module owes every migrated entrypoint.** Step 9
migrated ``qa-test`` onto the Platform SDK and discovered, via a real,
unconditionally-run integration test, that nothing in this class ever
called :meth:`~ai_os_sdk.contracts.entrypoint_context.PackContextReceiver.
bind_pack_context` — every migrated agent was only ever usable because
its own test bound one by hand. This step closes that gap for real,
here, once, rather than five more times in steps 10–13: once a loaded
entrypoint passes its ``Agent``/``Tool`` structural check, it is also
checked against ``PackContextReceiver``, and if it implements that too,
:func:`~ai_os_kernel.sdk_adapters.pack_context.build_pack_context` builds
it a real ``PackContext`` from *that row's own* ``required_permissions``
(never the pack's aggregate — the identical "no over-provisioning" rule
``build_pack_context`` itself already enforces) and injects it before
the entrypoint is ever returned to a caller. ``EntrypointLoader`` itself
is untouched — this is purely additional, caller-side logic in
``resolve_agent``/``resolve_tool``, exactly the seam step 6b's own
design always expected some real caller to fill.

No pack install/upgrade lifecycle, no health monitoring, no permissions
enforcement (only per-agent *provisioning* by declared permission, not
runtime enforcement against a grant), no sandboxing, no network or code
download — an activated pack owning the declared id is the only
additional thing checked before loading exactly the one ``entrypoint``
string the row declares; see
:mod:`ai_os_kernel.workflow_engine.entrypoint_loader` for the loader's
own, deliberately narrow boundary and
:mod:`ai_os_kernel.workflow_engine.pack_state` for the lifecycle this
module now reads one value from.
"""

import asyncio
from collections.abc import Collection, Mapping
from typing import Any, Protocol

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.llm_gateway.gateway import LLMGateway as KernelLLMGatewayProtocol
from ai_os_kernel.persistence.catalog_schema import agents as agents_table
from ai_os_kernel.persistence.catalog_schema import packs as packs_table
from ai_os_kernel.persistence.catalog_schema import tools as tools_table
from ai_os_kernel.prompt_engine.renderer import PromptEngine
from ai_os_kernel.sandbox.default_executor import build_default_sandbox_executor
from ai_os_kernel.sandbox.executor import SandboxExecutor
from ai_os_kernel.sdk_adapters.pack_context import build_pack_context
from ai_os_kernel.workflow_engine.agent import Agent
from ai_os_kernel.workflow_engine.entrypoint_loader import EntrypointLoader
from ai_os_kernel.workflow_engine.errors import (
    AgentNotRegisteredError,
    AgentRegistryError,
    PackNotActivatedError,
    ToolNotRegisteredError,
    ToolRegistryError,
)
from ai_os_kernel.workflow_engine.pack_state import PackState
from ai_os_kernel.workflow_engine.tool import Tool, TrustTier
from ai_os_sdk.contracts.entrypoint_context import PackContextReceiver


def _require_activated_pack(
    *, kind: str, declared_id: str, pack_id: str, state: str | None
) -> None:
    """Shared by :class:`SqlAgentRegistry`/:class:`SqlToolRegistry`:
    raise :class:`~ai_os_kernel.workflow_engine.errors.
    PackNotActivatedError` unless ``pack_id`` names a real
    ``catalog.packs`` row whose ``state`` is
    :attr:`~ai_os_kernel.workflow_engine.pack_state.PackState.ACTIVATED`.
    ``state`` is ``None`` when the ``LEFT JOIN`` against ``catalog.packs``
    found no matching row — ``pack_id`` is not FK-enforced against
    ``catalog.packs`` (see ``catalog_schema.py``'s own docstring), so a
    genuinely unregistered pack is a real, reachable case, not a
    defensive-only branch.
    """

    if state is None:
        raise PackNotActivatedError(
            f"{kind} '{declared_id}' declares pack_id={pack_id!r}, but no such pack is "
            "registered in catalog.packs"
        )

    if PackState(state) is not PackState.ACTIVATED:
        raise PackNotActivatedError(
            f"{kind} '{declared_id}' declares pack_id={pack_id!r}, whose state is "
            f"{state!r}, not {PackState.ACTIVATED.value!r}"
        )


def _bind_pack_context_if_receiver(
    loaded: Any,
    *,
    kind: str,
    declared_id: str,
    pack_id: str,
    pack_version: str,
    required_permissions: Collection[str],
    llm_gateway: KernelLLMGatewayProtocol | None,
    prompt_engine: PromptEngine | None,
    sandbox: SandboxExecutor | None,
) -> None:
    """Shared by :class:`SqlAgentRegistry`/:class:`SqlToolRegistry`: if
    ``loaded`` implements
    :class:`~ai_os_sdk.contracts.entrypoint_context.PackContextReceiver`,
    build it a real, permission-gated ``PackContext`` from *its own row's*
    ``required_permissions`` and inject it before ``loaded`` is ever
    returned to a caller. A no-op for anything that does not implement
    the Protocol (every not-yet-migrated entrypoint, today).

    Raises :class:`AgentRegistryError`/:class:`ToolRegistryError` (via
    ``kind``) if ``required_permissions`` declares a capability this
    registry was not itself given a real backing object for —
    :func:`~ai_os_kernel.sdk_adapters.pack_context.build_pack_context`'s
    own ``ValueError``, wrapped so every failure this class raises shares
    one error family.
    """
    if not isinstance(loaded, PackContextReceiver):
        return

    try:
        context = build_pack_context(
            pack_id=pack_id,
            pack_version=pack_version,
            permissions=required_permissions,
            llm_gateway=llm_gateway,
            prompt_engine=prompt_engine,
            sandbox=sandbox,
        )
    except ValueError as exc:
        error_type = AgentRegistryError if kind == "agent" else ToolRegistryError
        raise error_type(
            f"{kind} '{declared_id}' could not be granted its own declared "
            f"required_permissions {list(required_permissions)!r}: {exc}"
        ) from exc

    loaded.bind_pack_context(context)


class AgentRegistry(Protocol):
    """Resolves a declared ``agentId`` to a real :class:`Agent` instance
    — the seam a Capability-Manager-backed registry substitutes once one
    exists (ADR-0004: interface-driven, configuration over code)."""

    async def resolve_agent(self, agent_id: str) -> Agent: ...


class ToolRegistry(Protocol):
    """Resolves a declared ``toolId`` to a real :class:`Tool` instance —
    the seam a Capability-Manager-backed registry substitutes once one
    exists (ADR-0004: interface-driven, configuration over code)."""

    async def resolve_tool(self, tool_id: str) -> Tool: ...


class InMemoryAgentRegistry:
    """The simplest implementation: a plain mapping handed in at
    construction by the composition root — no pack discovery, no
    activation state, no permissions. A registered agent may itself be
    an :class:`~ai_os_kernel.workflow_engine.agent.EchoAgent`; this
    registry does not care what an ``Agent`` actually does."""

    def __init__(self, agents: Mapping[str, Agent]) -> None:
        self._agents = dict(agents)

    async def resolve_agent(self, agent_id: str) -> Agent:
        try:
            return self._agents[agent_id]
        except KeyError:
            raise AgentNotRegisteredError(f"no agent registered for agentId={agent_id!r}") from None


class InMemoryToolRegistry:
    """The simplest implementation — see :class:`InMemoryAgentRegistry`;
    the identical shape, for tools."""

    def __init__(self, tools: Mapping[str, Tool]) -> None:
        self._tools = dict(tools)

    async def resolve_tool(self, tool_id: str) -> Tool:
        try:
            return self._tools[tool_id]
        except KeyError:
            raise ToolNotRegisteredError(f"no tool registered for toolId={tool_id!r}") from None


class SqlAgentRegistry:
    """The ``catalog.agents``-backed implementation of
    :class:`AgentRegistry`: SQLAlchemy 2.0 Core against Postgres
    (ADR-0011). Confirms ``agent_id`` is a real, registered row, confirms
    its declared ``pack_id`` names an ``activated`` ``catalog.packs``
    row, then loads and constructs its declared ``entrypoint`` via
    :class:`~ai_os_kernel.workflow_engine.entrypoint_loader.
    EntrypointLoader` — see this module's own docstring for the
    validation applied to the result.
    """

    def __init__(
        self,
        engine: AsyncEngine,
        loader: EntrypointLoader | None = None,
        *,
        llm_gateway: KernelLLMGatewayProtocol | None = None,
        prompt_engine: PromptEngine | None = None,
        sandbox: SandboxExecutor | None = None,
    ) -> None:
        self._engine = engine
        self._loader = loader or EntrypointLoader()
        # llm_gateway/prompt_engine have no equivalent real-default
        # builder (unlike sandbox) -- each currently needs config-file
        # and secret composition no caller of this class does today
        # (bootstrap.py does not construct this class at all yet). Left
        # None until a real caller supplies them; build_pack_context
        # raises a clear error if a resolved entrypoint's own permissions
        # actually need one that is missing, rather than silently
        # proceeding.
        self._llm_gateway = llm_gateway
        self._prompt_engine = prompt_engine
        self._sandbox = sandbox or build_default_sandbox_executor()

    async def resolve_agent(self, agent_id: str) -> Agent:
        try:
            async with self._engine.connect() as connection:
                result = await connection.execute(
                    sa.select(
                        agents_table.c.pack_id,
                        agents_table.c.entrypoint,
                        agents_table.c.required_permissions,
                        packs_table.c.state,
                        packs_table.c.version,
                    )
                    .select_from(
                        agents_table.outerjoin(
                            packs_table, agents_table.c.pack_id == packs_table.c.pack_id
                        )
                    )
                    .where(agents_table.c.agent_id == agent_id)
                )
                row = result.one_or_none()
        except sa.exc.SQLAlchemyError as exc:
            raise AgentRegistryError(f"failed to look up agent '{agent_id}': {exc}") from exc

        if row is None:
            raise AgentNotRegisteredError(f"no agent registered for agentId={agent_id!r}")

        _require_activated_pack(
            kind="agent", declared_id=agent_id, pack_id=row.pack_id, state=row.state
        )

        loaded = await asyncio.to_thread(self._loader.load, row.entrypoint)

        if not isinstance(loaded, Agent):
            raise AgentRegistryError(
                f"agent '{agent_id}' entrypoint {row.entrypoint!r} did not resolve to a "
                "valid Agent (missing output_schema/execute)"
            )

        _bind_pack_context_if_receiver(
            loaded,
            kind="agent",
            declared_id=agent_id,
            pack_id=row.pack_id,
            pack_version=row.version,
            required_permissions=row.required_permissions,
            llm_gateway=self._llm_gateway,
            prompt_engine=self._prompt_engine,
            sandbox=self._sandbox,
        )

        return loaded


class SqlToolRegistry:
    """The ``catalog.tools``-backed implementation of
    :class:`ToolRegistry`: SQLAlchemy 2.0 Core against Postgres
    (ADR-0011). Confirms ``tool_id`` is a real, registered row, confirms
    its declared ``pack_id`` names an ``activated`` ``catalog.packs``
    row, then loads and constructs its declared ``entrypoint`` via
    :class:`~ai_os_kernel.workflow_engine.entrypoint_loader.
    EntrypointLoader` — see this module's own docstring for the
    validation applied to the result, including the ``trust_tier``
    agreement check.
    """

    def __init__(
        self,
        engine: AsyncEngine,
        loader: EntrypointLoader | None = None,
        *,
        llm_gateway: KernelLLMGatewayProtocol | None = None,
        prompt_engine: PromptEngine | None = None,
        sandbox: SandboxExecutor | None = None,
    ) -> None:
        self._engine = engine
        self._loader = loader or EntrypointLoader()
        # See SqlAgentRegistry.__init__'s own comment for why llm_gateway/
        # prompt_engine default to None rather than a real-default builder.
        self._llm_gateway = llm_gateway
        self._prompt_engine = prompt_engine
        self._sandbox = sandbox or build_default_sandbox_executor()

    async def resolve_tool(self, tool_id: str) -> Tool:
        try:
            async with self._engine.connect() as connection:
                result = await connection.execute(
                    sa.select(
                        tools_table.c.pack_id,
                        tools_table.c.entrypoint,
                        tools_table.c.trust_tier,
                        tools_table.c.required_permissions,
                        packs_table.c.state,
                        packs_table.c.version,
                    )
                    .select_from(
                        tools_table.outerjoin(
                            packs_table, tools_table.c.pack_id == packs_table.c.pack_id
                        )
                    )
                    .where(tools_table.c.tool_id == tool_id)
                )
                row = result.one_or_none()
        except sa.exc.SQLAlchemyError as exc:
            raise ToolRegistryError(f"failed to look up tool '{tool_id}': {exc}") from exc

        if row is None:
            raise ToolNotRegisteredError(f"no tool registered for toolId={tool_id!r}")

        _require_activated_pack(
            kind="tool", declared_id=tool_id, pack_id=row.pack_id, state=row.state
        )

        loaded = await asyncio.to_thread(self._loader.load, row.entrypoint)

        if not isinstance(loaded, Tool):
            raise ToolRegistryError(
                f"tool '{tool_id}' entrypoint {row.entrypoint!r} did not resolve to a "
                "valid Tool (missing trust_tier/output_schema/execute)"
            )

        declared_trust_tier = TrustTier(row.trust_tier)
        if loaded.trust_tier is not declared_trust_tier:
            raise ToolRegistryError(
                f"tool '{tool_id}' entrypoint {row.entrypoint!r} declares trust_tier="
                f"{loaded.trust_tier.value!r}, but catalog.tools records "
                f"{declared_trust_tier.value!r} for it — refusing to trust either value alone"
            )

        _bind_pack_context_if_receiver(
            loaded,
            kind="tool",
            declared_id=tool_id,
            pack_id=row.pack_id,
            pack_version=row.version,
            required_permissions=row.required_permissions,
            llm_gateway=self._llm_gateway,
            prompt_engine=self._prompt_engine,
            sandbox=self._sandbox,
        )

        return loaded
