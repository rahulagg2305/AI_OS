"""SqlAgentRegistry/SqlToolRegistry against a real Postgres container
(ADR-0015 — no mocking the database). Proves: a real, registered
``catalog.agents``/``catalog.tools`` row's declared ``entrypoint`` is
actually loaded and constructed (not always ``EchoAgent``/``EchoTool``),
an unregistered id raises the documented error rather than a bare
``None``/``KeyError``, the safety checks (``Agent``/``Tool`` Protocol
conformance, ``trust_tier`` agreement) reject a bad entrypoint clearly
instead of silently trusting it, the Capability Manager minimal slice
that gates on pack activation — an agent/tool whose declared ``pack_id``
names a pack that is missing from ``catalog.packs`` or not
``activated`` is refused before its entrypoint is ever loaded — and,
``P02-S05-M13-T08``, the permission-grant slice: an agent/tool whose
own declared permissions exceed its pack's own manifest grant is
refused the identical way, before its entrypoint is ever loaded.
"""

import asyncio
import json
import os
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.workflow_engine.agent import EchoAgent
from ai_os_kernel.workflow_engine.errors import (
    AgentNotRegisteredError,
    AgentRegistryError,
    EntrypointLoadError,
    PackNotActivatedError,
    ToolNotRegisteredError,
    ToolRegistryError,
)
from ai_os_kernel.workflow_engine.registry import SqlAgentRegistry, SqlToolRegistry
from ai_os_kernel.workflow_engine.tool import EchoTool, TrustTier
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

_ECHO_AGENT_ENTRYPOINT = "ai_os_kernel.workflow_engine.agent:EchoAgent"
_ECHO_TOOL_ENTRYPOINT = "ai_os_kernel.workflow_engine.tool:EchoTool"
_STUBS_MODULE = "tests.integration.workflow_engine._entrypoint_stubs"
_DEFAULT_PACK_ID = "se.software_engineering"


@pytest.fixture(scope="module")
def database_url() -> Generator[str, None, None]:
    with postgres_container() as postgres:
        url = postgres.get_connection_url()
        previous = os.environ.get("AIOS_DATABASE_URL")
        os.environ["AIOS_DATABASE_URL"] = url
        try:
            command.upgrade(Config(str(ALEMBIC_INI)), "head")
            yield url
        finally:
            if previous is None:
                os.environ.pop("AIOS_DATABASE_URL", None)
            else:
                os.environ["AIOS_DATABASE_URL"] = previous


async def _seed_agent(
    database_url: str,
    *,
    agent_id: str,
    entrypoint: str,
    pack_id: str = _DEFAULT_PACK_ID,
    required_permissions: list[str] | None = None,
) -> None:
    engine = build_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                sa.text(
                    "INSERT INTO catalog.agents "
                    "(agent_id, pack_id, version, entrypoint, input_schema, output_schema, "
                    " required_permissions, required_tools) "
                    "VALUES (:agent_id, :pack_id, '1.0.0', :entrypoint, "
                    " '{}'::jsonb, '{}'::jsonb, CAST(:required_permissions AS jsonb), '[]'::jsonb)"
                ),
                {
                    "agent_id": agent_id,
                    "pack_id": pack_id,
                    "entrypoint": entrypoint,
                    "required_permissions": json.dumps(required_permissions or []),
                },
            )
    finally:
        await engine.dispose()


async def _seed_tool(
    database_url: str,
    *,
    tool_id: str,
    entrypoint: str,
    trust_tier: str,
    pack_id: str = _DEFAULT_PACK_ID,
    required_permissions: list[str] | None = None,
) -> None:
    engine = build_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                sa.text(
                    "INSERT INTO catalog.tools "
                    "(tool_id, pack_id, version, entrypoint, trust_tier, input_schema, "
                    " output_schema, required_permissions) "
                    "VALUES (:tool_id, :pack_id, '1.0.0', :entrypoint, "
                    " :trust_tier, '{}'::jsonb, '{}'::jsonb, CAST(:required_permissions AS jsonb))"
                ),
                {
                    "tool_id": tool_id,
                    "pack_id": pack_id,
                    "entrypoint": entrypoint,
                    "trust_tier": trust_tier,
                    "required_permissions": json.dumps(required_permissions or []),
                },
            )
    finally:
        await engine.dispose()


async def _seed_pack(
    database_url: str, *, pack_id: str, state: str, manifest: dict[str, Any] | None = None
) -> None:
    engine = build_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                sa.text(
                    "INSERT INTO catalog.packs "
                    "(pack_id, version, state, manifest, sdk_version, min_kernel_version) "
                    "VALUES (:pack_id, '1.0.0', :state, CAST(:manifest AS jsonb), "
                    " '1.0.0', '1.0.0') "
                    "ON CONFLICT (pack_id) DO NOTHING"
                ),
                {"pack_id": pack_id, "state": state, "manifest": json.dumps(manifest or {})},
            )
    finally:
        await engine.dispose()


@pytest.fixture(autouse=True)
def _default_pack_is_activated(database_url: str) -> None:
    """Every test in this module that does not care about pack-activation
    gating itself seeds an agent/tool under ``_DEFAULT_PACK_ID`` — this
    keeps that pack ``activated`` so those tests exercise entrypoint
    loading, not this step's own gate. Idempotent (``ON CONFLICT DO
    NOTHING``): safe to run once per test in a module-scoped container.
    """

    asyncio.run(_seed_pack(database_url, pack_id=_DEFAULT_PACK_ID, state="activated"))


def test_resolve_agent_loads_the_declared_entrypoint(database_url: str) -> None:
    async def _run() -> None:
        await _seed_agent(
            database_url,
            agent_id="se.software_engineering/analyst",
            entrypoint=_ECHO_AGENT_ENTRYPOINT,
        )
        engine = build_engine(database_url)
        try:
            registry = SqlAgentRegistry(engine)

            resolved = await registry.resolve_agent("se.software_engineering/analyst")

            assert isinstance(resolved, EchoAgent)
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_resolve_agent_loads_a_real_custom_entrypoint_not_just_echo_agent(
    database_url: str,
) -> None:
    async def _run() -> None:
        await _seed_agent(
            database_url,
            agent_id="se.software_engineering/named-stub",
            entrypoint=f"{_STUBS_MODULE}:NamedStubAgent",
        )
        engine = build_engine(database_url)
        try:
            registry = SqlAgentRegistry(engine)

            resolved = await registry.resolve_agent("se.software_engineering/named-stub")
            outputs = await resolved.execute({})

            assert type(resolved).__name__ == "NamedStubAgent"
            assert outputs == {"ranAs": "NamedStubAgent"}
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_resolve_agent_raises_for_an_unregistered_id(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            registry = SqlAgentRegistry(engine)

            with pytest.raises(AgentNotRegisteredError, match="does-not-exist"):
                await registry.resolve_agent("se.software_engineering/does-not-exist")
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_resolve_agent_raises_clearly_for_a_malformed_entrypoint(database_url: str) -> None:
    async def _run() -> None:
        await _seed_agent(
            database_url,
            agent_id="se.software_engineering/bad-entrypoint",
            entrypoint="this_module_does_not_exist_anywhere:SomeClass",
        )
        engine = build_engine(database_url)
        try:
            registry = SqlAgentRegistry(engine)

            with pytest.raises(EntrypointLoadError, match="could not import module"):
                await registry.resolve_agent("se.software_engineering/bad-entrypoint")
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_resolve_agent_rejects_an_entrypoint_that_is_not_a_valid_agent(
    database_url: str,
) -> None:
    async def _run() -> None:
        await _seed_agent(
            database_url,
            agent_id="se.software_engineering/not-an-agent",
            entrypoint=f"{_STUBS_MODULE}:NotAnAgentOrTool",
        )
        engine = build_engine(database_url)
        try:
            registry = SqlAgentRegistry(engine)

            with pytest.raises(
                AgentRegistryError, match="did not resolve to a valid Agent"
            ) as exc_info:
                await registry.resolve_agent("se.software_engineering/not-an-agent")
            # A structural, permanent cause — never retriable (the
            # retriable-split step, 2026-07-31): retrying would
            # reconstruct the identical, still-incomplete object.
            assert exc_info.value.retriable is False
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_resolve_tool_loads_the_declared_entrypoint(database_url: str) -> None:
    async def _run() -> None:
        await _seed_tool(
            database_url,
            tool_id="se.build",
            entrypoint=_ECHO_TOOL_ENTRYPOINT,
            trust_tier="tier2_trusted",
        )
        engine = build_engine(database_url)
        try:
            registry = SqlToolRegistry(engine)

            resolved = await registry.resolve_tool("se.build")

            assert isinstance(resolved, EchoTool)
            assert resolved.trust_tier == TrustTier.TIER2_TRUSTED
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_resolve_tool_loads_a_real_custom_entrypoint_declaring_tier1_sandboxed(
    database_url: str,
) -> None:
    async def _run() -> None:
        await _seed_tool(
            database_url,
            tool_id="se.run_untrusted_script",
            entrypoint=f"{_STUBS_MODULE}:SandboxedStubTool",
            trust_tier="tier1_sandboxed",
        )
        engine = build_engine(database_url)
        try:
            registry = SqlToolRegistry(engine)

            resolved = await registry.resolve_tool("se.run_untrusted_script")

            # A real, custom entrypoint whose own code and whose catalog
            # row agree on tier1_sandboxed — accepted, not laundered
            # into a more-trusted-looking stand-in.
            assert type(resolved).__name__ == "SandboxedStubTool"
            assert resolved.trust_tier == TrustTier.TIER1_SANDBOXED
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_resolve_tool_rejects_a_trust_tier_disagreement(database_url: str) -> None:
    async def _run() -> None:
        # The entrypoint's own code declares tier1_sandboxed, but the
        # catalog row (as if a manifest were edited without updating
        # the code, or vice versa) declares tier2_trusted.
        await _seed_tool(
            database_url,
            tool_id="se.mismatched_tool",
            entrypoint=f"{_STUBS_MODULE}:MismatchedTrustTierStubTool",
            trust_tier="tier2_trusted",
        )
        engine = build_engine(database_url)
        try:
            registry = SqlToolRegistry(engine)

            with pytest.raises(
                ToolRegistryError, match="refusing to trust either value alone"
            ) as exc_info:
                await registry.resolve_tool("se.mismatched_tool")
            # A structural, permanent cause — never retriable (the
            # retriable-split step, 2026-07-31): neither the entrypoint's
            # own code nor the catalog row changes between attempts.
            assert exc_info.value.retriable is False
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_resolve_tool_raises_for_an_unregistered_id(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            registry = SqlToolRegistry(engine)

            with pytest.raises(ToolNotRegisteredError, match="does_not_exist"):
                await registry.resolve_tool("se.does_not_exist")
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_resolve_tool_rejects_an_entrypoint_that_is_not_a_valid_tool(
    database_url: str,
) -> None:
    async def _run() -> None:
        await _seed_tool(
            database_url,
            tool_id="se.not_a_tool",
            entrypoint=f"{_STUBS_MODULE}:NotAnAgentOrTool",
            trust_tier="tier2_trusted",
        )
        engine = build_engine(database_url)
        try:
            registry = SqlToolRegistry(engine)

            with pytest.raises(
                ToolRegistryError, match="did not resolve to a valid Tool"
            ) as exc_info:
                await registry.resolve_tool("se.not_a_tool")
            # A structural, permanent cause — never retriable (the
            # retriable-split step, 2026-07-31).
            assert exc_info.value.retriable is False
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_resolve_agent_succeeds_when_its_pack_is_activated(database_url: str) -> None:
    async def _run() -> None:
        await _seed_pack(database_url, pack_id="se.active_pack", state="activated")
        await _seed_agent(
            database_url,
            agent_id="se.active_pack/analyst",
            entrypoint=_ECHO_AGENT_ENTRYPOINT,
            pack_id="se.active_pack",
        )
        engine = build_engine(database_url)
        try:
            registry = SqlAgentRegistry(engine)

            resolved = await registry.resolve_agent("se.active_pack/analyst")

            assert isinstance(resolved, EchoAgent)
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_resolve_agent_rejects_a_non_activated_pack(database_url: str) -> None:
    async def _run() -> None:
        await _seed_pack(database_url, pack_id="se.deactivated_pack", state="deactivated")
        await _seed_agent(
            database_url,
            agent_id="se.deactivated_pack/analyst",
            entrypoint=_ECHO_AGENT_ENTRYPOINT,
            pack_id="se.deactivated_pack",
        )
        engine = build_engine(database_url)
        try:
            registry = SqlAgentRegistry(engine)

            with pytest.raises(PackNotActivatedError, match="not 'activated'"):
                await registry.resolve_agent("se.deactivated_pack/analyst")
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_resolve_agent_rejects_a_pack_missing_from_catalog_packs(database_url: str) -> None:
    async def _run() -> None:
        # No catalog.packs row is ever seeded for this pack_id.
        await _seed_agent(
            database_url,
            agent_id="se.no_such_pack/analyst",
            entrypoint=_ECHO_AGENT_ENTRYPOINT,
            pack_id="se.no_such_pack",
        )
        engine = build_engine(database_url)
        try:
            registry = SqlAgentRegistry(engine)

            with pytest.raises(PackNotActivatedError, match="no such pack is registered"):
                await registry.resolve_agent("se.no_such_pack/analyst")
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_resolve_tool_succeeds_when_its_pack_is_activated(database_url: str) -> None:
    async def _run() -> None:
        await _seed_pack(database_url, pack_id="se.active_pack", state="activated")
        await _seed_tool(
            database_url,
            tool_id="se.active_pack_tool",
            entrypoint=_ECHO_TOOL_ENTRYPOINT,
            trust_tier="tier2_trusted",
            pack_id="se.active_pack",
        )
        engine = build_engine(database_url)
        try:
            registry = SqlToolRegistry(engine)

            resolved = await registry.resolve_tool("se.active_pack_tool")

            assert isinstance(resolved, EchoTool)
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_resolve_tool_rejects_a_non_activated_pack(database_url: str) -> None:
    async def _run() -> None:
        await _seed_pack(database_url, pack_id="se.deactivated_pack", state="deactivated")
        await _seed_tool(
            database_url,
            tool_id="se.deactivated_pack_tool",
            entrypoint=_ECHO_TOOL_ENTRYPOINT,
            trust_tier="tier2_trusted",
            pack_id="se.deactivated_pack",
        )
        engine = build_engine(database_url)
        try:
            registry = SqlToolRegistry(engine)

            with pytest.raises(PackNotActivatedError, match="not 'activated'"):
                await registry.resolve_tool("se.deactivated_pack_tool")
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_resolve_tool_rejects_a_pack_missing_from_catalog_packs(database_url: str) -> None:
    async def _run() -> None:
        # No catalog.packs row is ever seeded for this pack_id.
        await _seed_tool(
            database_url,
            tool_id="se.no_such_pack_tool",
            entrypoint=_ECHO_TOOL_ENTRYPOINT,
            trust_tier="tier2_trusted",
            pack_id="se.no_such_pack",
        )
        engine = build_engine(database_url)
        try:
            registry = SqlToolRegistry(engine)

            with pytest.raises(PackNotActivatedError, match="no such pack is registered"):
                await registry.resolve_tool("se.no_such_pack_tool")
        finally:
            await engine.dispose()

    asyncio.run(_run())


# A well-formed URL with nothing listening on the given port — the
# identical technique test_health_database_check.py already uses for a
# genuinely unreachable database, not a mock.
_UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://user:pass@127.0.0.1:1/nonexistent"


def test_resolve_agent_raises_a_retriable_error_for_a_genuine_connection_failure() -> None:
    """The one genuinely transient real cause `AgentRegistryError` covers
    (the retriable-split step, 2026-07-31): a real, unreachable database
    — not a mock, not a simulated exception — raises with `retriable is
    True`, unlike the structural causes above."""

    async def _run() -> None:
        engine = build_engine(_UNREACHABLE_DATABASE_URL)
        try:
            registry = SqlAgentRegistry(engine)

            with pytest.raises(AgentRegistryError, match="failed to look up agent") as exc_info:
                await registry.resolve_agent("se.software_engineering/anything")
            assert exc_info.value.retriable is True
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_resolve_tool_raises_a_retriable_error_for_a_genuine_connection_failure() -> None:
    """The identical real, transient cause for `ToolRegistryError`."""

    async def _run() -> None:
        engine = build_engine(_UNREACHABLE_DATABASE_URL)
        try:
            registry = SqlToolRegistry(engine)

            with pytest.raises(ToolRegistryError, match="failed to look up tool") as exc_info:
                await registry.resolve_tool("se.anything")
            assert exc_info.value.retriable is True
        finally:
            await engine.dispose()

    asyncio.run(_run())


# --- Permission-grant enforcement (P02-S05-M13-T08) ---


def test_resolve_agent_succeeds_when_its_permissions_are_within_its_packs_grant(
    database_url: str,
) -> None:
    async def _run() -> None:
        await _seed_pack(
            database_url,
            pack_id="se.scoped_pack",
            state="activated",
            manifest={"permissions": ["llm:invoke", "sandbox:execute"]},
        )
        await _seed_agent(
            database_url,
            agent_id="se.scoped_pack/legit-agent",
            entrypoint=_ECHO_AGENT_ENTRYPOINT,
            pack_id="se.scoped_pack",
            required_permissions=["llm:invoke"],
        )
        engine = build_engine(database_url)
        try:
            registry = SqlAgentRegistry(engine)

            resolved = await registry.resolve_agent("se.scoped_pack/legit-agent")

            assert isinstance(resolved, EchoAgent)
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_resolve_agent_is_refused_when_its_permissions_exceed_its_packs_grant(
    database_url: str,
) -> None:
    async def _run() -> None:
        await _seed_pack(
            database_url,
            pack_id="se.narrow_pack",
            state="activated",
            manifest={"permissions": ["sandbox:execute"]},
        )
        await _seed_agent(
            database_url,
            agent_id="se.narrow_pack/over_grant_agent",
            entrypoint=_ECHO_AGENT_ENTRYPOINT,
            pack_id="se.narrow_pack",
            # llm:invoke was never in the pack's own manifest grant above.
            required_permissions=["sandbox:execute", "llm:invoke"],
        )
        engine = build_engine(database_url)
        try:
            registry = SqlAgentRegistry(engine)

            with pytest.raises(
                AgentRegistryError, match="pack's own manifest never grants"
            ) as exc_info:
                await registry.resolve_agent("se.narrow_pack/over_grant_agent")

            assert "llm:invoke" in str(exc_info.value)
            # A structural, permanent cause: retrying reconstructs the
            # identical, still-over-granted row.
            assert exc_info.value.retriable is False
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_resolve_agent_over_grant_refusal_happens_before_the_entrypoint_is_ever_loaded(
    database_url: str,
) -> None:
    """A stronger property than "the caller gets an error": an
    over-granted agent's own entrypoint is never even imported — the
    identical "refuse before importing pack code" guarantee
    `PackNotActivatedError` already provides, extended to this new
    check."""

    async def _run() -> None:
        await _seed_pack(
            database_url,
            pack_id="se.narrow_pack_2",
            state="activated",
            manifest={"permissions": []},
        )
        await _seed_agent(
            database_url,
            agent_id="se.narrow_pack_2/over_grant_agent",
            entrypoint="this_module_does_not_exist_anywhere:SomeClass",
            pack_id="se.narrow_pack_2",
            required_permissions=["secret:access"],
        )
        engine = build_engine(database_url)
        try:
            registry = SqlAgentRegistry(engine)

            # If the over-grant check did not fire first, this would
            # raise EntrypointLoadError instead (the malformed entrypoint
            # string) — the over-grant refusal must win the race.
            with pytest.raises(AgentRegistryError, match="pack's own manifest never grants"):
                await registry.resolve_agent("se.narrow_pack_2/over_grant_agent")
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_resolve_tool_succeeds_when_its_permissions_are_within_its_packs_grant(
    database_url: str,
) -> None:
    async def _run() -> None:
        await _seed_pack(
            database_url,
            pack_id="se.scoped_tool_pack",
            state="activated",
            manifest={"permissions": ["sandbox:execute"]},
        )
        await _seed_tool(
            database_url,
            tool_id="se.scoped_tool_pack.legit_tool",
            entrypoint=_ECHO_TOOL_ENTRYPOINT,
            trust_tier="tier2_trusted",
            pack_id="se.scoped_tool_pack",
            required_permissions=["sandbox:execute"],
        )
        engine = build_engine(database_url)
        try:
            registry = SqlToolRegistry(engine)

            resolved = await registry.resolve_tool("se.scoped_tool_pack.legit_tool")

            assert isinstance(resolved, EchoTool)
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_resolve_tool_is_refused_when_its_permissions_exceed_its_packs_grant(
    database_url: str,
) -> None:
    async def _run() -> None:
        await _seed_pack(
            database_url,
            pack_id="se.narrow_tool_pack",
            state="activated",
            manifest={"permissions": ["sandbox:execute"]},
        )
        await _seed_tool(
            database_url,
            tool_id="se.narrow_tool_pack.over_grant_tool",
            entrypoint=_ECHO_TOOL_ENTRYPOINT,
            trust_tier="tier2_trusted",
            pack_id="se.narrow_tool_pack",
            # secret:access was never in the pack's own manifest grant above.
            required_permissions=["sandbox:execute", "secret:access"],
        )
        engine = build_engine(database_url)
        try:
            registry = SqlToolRegistry(engine)

            with pytest.raises(
                ToolRegistryError, match="pack's own manifest never grants"
            ) as exc_info:
                await registry.resolve_tool("se.narrow_tool_pack.over_grant_tool")

            assert "secret:access" in str(exc_info.value)
            assert exc_info.value.retriable is False
        finally:
            await engine.dispose()

    asyncio.run(_run())
