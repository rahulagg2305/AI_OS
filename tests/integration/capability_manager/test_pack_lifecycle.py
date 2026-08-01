"""``SqlPackLifecycleRepository`` against a real Postgres container
(ADR-0015 — no mocking the database). Proves: register/install creates
a real ``catalog.packs`` row and records its first transition, activate/
deactivate transition it correctly (including re-activation after
deactivation), invalid transitions and unregistered packs are rejected
clearly, — the specific integration point this step's own approved
framing calls out ("keep agent/tool resolution gated on activated
state") — a pack activated through this new writer gates
``SqlAgentRegistry``/``SqlToolRegistry`` exactly the same way a
hand-seeded row already did, and (``P02-S05-M13-T07``) ``upgrade()``
genuinely migrates an activated pack's catalog rows to a new manifest
version — updating what changed, deleting what the new version no
longer declares, adding what it newly declares — while refusing a
same-or-older version outright, before any row is touched.
"""

import asyncio
import os
from collections.abc import Generator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from pydantic import BaseModel

from ai_os_kernel.capability_manager.errors import (
    InvalidPackTransitionError,
    InvalidPackUpgradeError,
    PackAlreadyRegisteredError,
    PackNotFoundError,
)
from ai_os_kernel.capability_manager.repository import SqlPackLifecycleRepository
from ai_os_kernel.persistence.catalog_schema import agents as agents_table
from ai_os_kernel.persistence.catalog_schema import pack_state_transitions
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.workflow_engine.agent import EchoAgent
from ai_os_kernel.workflow_engine.errors import AgentNotRegisteredError, PackNotActivatedError
from ai_os_kernel.workflow_engine.pack_state import PackState
from ai_os_kernel.workflow_engine.registry import SqlAgentRegistry
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
_ECHO_AGENT_ENTRYPOINT = "ai_os_kernel.workflow_engine.agent:EchoAgent"
_MANIFEST = {"name": "test-pack"}


class _TestAgentIO(BaseModel):
    """A real, importable Pydantic model — used as this file's own
    ``inputSchema``/``outputSchema`` reference for synthetic upgrade-test
    manifests, so :func:`~ai_os_kernel.capability_manager.
    manifest_catalog_installer.derive_agent_rows` resolves a real class
    and calls a real ``model_json_schema()``, not a mock."""

    status: str


_TEST_AGENT_IO_REF = "tests.integration.capability_manager.test_pack_lifecycle:_TestAgentIO"


def _agent_entry(agent_id: str, *, version: str, permissions: list[str]) -> dict[str, object]:
    return {
        "id": agent_id,
        "version": version,
        "entrypoint": _ECHO_AGENT_ENTRYPOINT,
        "inputSchema": _TEST_AGENT_IO_REF,
        "outputSchema": _TEST_AGENT_IO_REF,
        "permissions": permissions,
    }


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


async def _transitions_for(database_url: str, pack_id: str) -> list[tuple[str, str]]:
    engine = build_engine(database_url)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                sa.select(pack_state_transitions.c.from_state, pack_state_transitions.c.to_state)
                .where(pack_state_transitions.c.pack_id == pack_id)
                .order_by(pack_state_transitions.c.occurred_at)
            )
            return [(row.from_state, row.to_state) for row in result.all()]
    finally:
        await engine.dispose()


def test_register_creates_an_installed_pack_and_records_the_transition(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            repository = SqlPackLifecycleRepository(engine)

            record = await repository.register(
                pack_id="test.register_creates",
                version="1.0.0",
                manifest=_MANIFEST,
                sdk_version="1.0.0",
                min_kernel_version="1.0.0",
                actor="test-actor",
                reason="initial install",
            )

            assert record.pack_id == "test.register_creates"
            assert record.state is PackState.INSTALLED
            assert record.installed_at is not None
            assert record.activated_at is None
            assert record.manifest == _MANIFEST

            fetched = await repository.get_pack("test.register_creates")
            assert fetched == record
        finally:
            await engine.dispose()

    asyncio.run(_run())
    assert asyncio.run(_transitions_for(database_url, "test.register_creates")) == [
        ("discovered", "installed")
    ]


def test_register_rejects_a_duplicate_pack_id(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            repository = SqlPackLifecycleRepository(engine)
            await repository.register(
                pack_id="test.duplicate",
                version="1.0.0",
                manifest=_MANIFEST,
                sdk_version="1.0.0",
                min_kernel_version="1.0.0",
                actor="test-actor",
                reason="initial install",
            )

            with pytest.raises(PackAlreadyRegisteredError, match="test.duplicate"):
                await repository.register(
                    pack_id="test.duplicate",
                    version="2.0.0",
                    manifest=_MANIFEST,
                    sdk_version="1.0.0",
                    min_kernel_version="1.0.0",
                    actor="test-actor",
                    reason="second attempt",
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_activate_transitions_from_installed_to_activated(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            repository = SqlPackLifecycleRepository(engine)
            await repository.register(
                pack_id="test.activate_from_installed",
                version="1.0.0",
                manifest=_MANIFEST,
                sdk_version="1.0.0",
                min_kernel_version="1.0.0",
                actor="test-actor",
                reason="initial install",
            )

            record = await repository.activate(
                pack_id="test.activate_from_installed", actor="test-actor", reason="go live"
            )

            assert record.state is PackState.ACTIVATED
            assert record.activated_at is not None
        finally:
            await engine.dispose()

    asyncio.run(_run())
    assert asyncio.run(_transitions_for(database_url, "test.activate_from_installed")) == [
        ("discovered", "installed"),
        ("installed", "activated"),
    ]


def test_activate_rejects_an_already_activated_pack(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            repository = SqlPackLifecycleRepository(engine)
            await repository.register(
                pack_id="test.already_active",
                version="1.0.0",
                manifest=_MANIFEST,
                sdk_version="1.0.0",
                min_kernel_version="1.0.0",
                actor="test-actor",
                reason="initial install",
            )
            await repository.activate(
                pack_id="test.already_active", actor="test-actor", reason="go live"
            )

            with pytest.raises(InvalidPackTransitionError, match="test.already_active"):
                await repository.activate(
                    pack_id="test.already_active", actor="test-actor", reason="again"
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_activate_rejects_an_unregistered_pack(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            repository = SqlPackLifecycleRepository(engine)

            with pytest.raises(PackNotFoundError, match="test.never_registered"):
                await repository.activate(
                    pack_id="test.never_registered", actor="test-actor", reason="go live"
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_deactivate_transitions_from_activated_to_deactivated(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            repository = SqlPackLifecycleRepository(engine)
            await repository.register(
                pack_id="test.deactivate_from_activated",
                version="1.0.0",
                manifest=_MANIFEST,
                sdk_version="1.0.0",
                min_kernel_version="1.0.0",
                actor="test-actor",
                reason="initial install",
            )
            await repository.activate(
                pack_id="test.deactivate_from_activated", actor="test-actor", reason="go live"
            )

            record = await repository.deactivate(
                pack_id="test.deactivate_from_activated", actor="test-actor", reason="withdraw"
            )

            assert record.state is PackState.DEACTIVATED
        finally:
            await engine.dispose()

    asyncio.run(_run())
    assert asyncio.run(_transitions_for(database_url, "test.deactivate_from_activated")) == [
        ("discovered", "installed"),
        ("installed", "activated"),
        ("activated", "deactivated"),
    ]


def test_deactivate_rejects_a_pack_that_was_never_activated(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            repository = SqlPackLifecycleRepository(engine)
            await repository.register(
                pack_id="test.deactivate_installed_only",
                version="1.0.0",
                manifest=_MANIFEST,
                sdk_version="1.0.0",
                min_kernel_version="1.0.0",
                actor="test-actor",
                reason="initial install",
            )

            with pytest.raises(InvalidPackTransitionError, match="test.deactivate_installed_only"):
                await repository.deactivate(
                    pack_id="test.deactivate_installed_only", actor="test-actor", reason="withdraw"
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_deactivated_pack_can_be_reactivated(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            repository = SqlPackLifecycleRepository(engine)
            await repository.register(
                pack_id="test.reactivate",
                version="1.0.0",
                manifest=_MANIFEST,
                sdk_version="1.0.0",
                min_kernel_version="1.0.0",
                actor="test-actor",
                reason="initial install",
            )
            await repository.activate(
                pack_id="test.reactivate", actor="test-actor", reason="go live"
            )
            await repository.deactivate(
                pack_id="test.reactivate", actor="test-actor", reason="withdraw"
            )

            record = await repository.activate(
                pack_id="test.reactivate", actor="test-actor", reason="bring back"
            )

            assert record.state is PackState.ACTIVATED
        finally:
            await engine.dispose()

    asyncio.run(_run())
    assert asyncio.run(_transitions_for(database_url, "test.reactivate")) == [
        ("discovered", "installed"),
        ("installed", "activated"),
        ("activated", "deactivated"),
        ("deactivated", "activated"),
    ]


def test_get_pack_returns_none_for_an_unregistered_id(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            repository = SqlPackLifecycleRepository(engine)

            assert await repository.get_pack("test.does_not_exist") is None
        finally:
            await engine.dispose()

    asyncio.run(_run())


async def _seed_agent(database_url: str, *, agent_id: str, pack_id: str) -> None:
    engine = build_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                sa.text(
                    "INSERT INTO catalog.agents "
                    "(agent_id, pack_id, version, entrypoint, input_schema, output_schema, "
                    " required_permissions, required_tools) "
                    "VALUES (:agent_id, :pack_id, '1.0.0', :entrypoint, "
                    " '{}'::jsonb, '{}'::jsonb, '[]'::jsonb, '[]'::jsonb)"
                ),
                {"agent_id": agent_id, "pack_id": pack_id, "entrypoint": _ECHO_AGENT_ENTRYPOINT},
            )
    finally:
        await engine.dispose()


def test_a_pack_activated_through_the_new_writer_gates_agent_resolution(
    database_url: str,
) -> None:
    """The specific integration point this step's own approved framing
    names: activation through the real writer must gate
    ``SqlAgentRegistry`` exactly as a hand-seeded ``catalog.packs`` row
    already did (``tests/integration/workflow_engine/test_registry.py``)."""

    async def _run() -> None:
        pack_id = "test.gates_agent_resolution"
        agent_id = f"{pack_id}/analyst"
        await _seed_agent(database_url, agent_id=agent_id, pack_id=pack_id)

        engine = build_engine(database_url)
        try:
            lifecycle = SqlPackLifecycleRepository(engine)
            registry = SqlAgentRegistry(engine)

            await lifecycle.register(
                pack_id=pack_id,
                version="1.0.0",
                manifest=_MANIFEST,
                sdk_version="1.0.0",
                min_kernel_version="1.0.0",
                actor="test-actor",
                reason="initial install",
            )

            # Not yet activated — installed only.
            with pytest.raises(PackNotActivatedError):
                await registry.resolve_agent(agent_id)

            await lifecycle.activate(pack_id=pack_id, actor="test-actor", reason="go live")
            resolved = await registry.resolve_agent(agent_id)
            assert isinstance(resolved, EchoAgent)

            await lifecycle.deactivate(pack_id=pack_id, actor="test-actor", reason="withdraw")
            with pytest.raises(PackNotActivatedError):
                await registry.resolve_agent(agent_id)
        finally:
            await engine.dispose()

    asyncio.run(_run())


# --- upgrade() (P02-S05-M13-T07) ---


async def _agents_for(database_url: str, pack_id: str) -> dict[str, dict[str, object]]:
    engine = build_engine(database_url)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                sa.select(
                    agents_table.c.agent_id,
                    agents_table.c.version,
                    agents_table.c.required_permissions,
                ).where(agents_table.c.pack_id == pack_id)
            )
            return {
                row.agent_id: {"version": row.version, "permissions": row.required_permissions}
                for row in result.all()
            }
    finally:
        await engine.dispose()


def test_upgrade_genuinely_migrates_an_activated_packs_agent_rows(
    database_url: str, tmp_path: Path
) -> None:
    """The real proof this ticket asks for: a pack genuinely upgrades
    from one version to another, with its real `catalog.agents` rows
    correctly migrated to match the new manifest — an agent present in
    both versions is updated (not left with stale content), an agent
    dropped from the new version is deleted (not orphaned), and an
    agent newly declared is added."""

    async def _run() -> None:
        pack_id = "test.upgrade_migrates_agents"
        # Pack-level `permissions` must cover every agent's own declared
        # set (P02-S05-M13-T08's real over-grant check, exercised for
        # real here since this test resolves an agent after upgrading —
        # not a detail this test can skip).
        manifest_v1 = {
            "name": "test-pack",
            "permissions": ["llm:invoke", "sandbox:execute"],
            "agents": [
                _agent_entry("analyst", version="1.0.0", permissions=["llm:invoke"]),
                _agent_entry("builder", version="1.0.0", permissions=["sandbox:execute"]),
            ],
        }
        manifest_v2 = {
            "name": "test-pack",
            "permissions": ["llm:invoke", "knowledge:read"],
            "agents": [
                # analyst survives the upgrade with a genuinely different
                # permission set — must be updated, not left stale.
                _agent_entry(
                    "analyst", version="2.0.0", permissions=["llm:invoke", "knowledge:read"]
                ),
                # builder is dropped entirely — must be deleted, not
                # orphaned pointing at a version that no longer claims it.
                # reviewer is new — must be inserted.
                _agent_entry("reviewer", version="2.0.0", permissions=["llm:invoke"]),
            ],
        }

        engine = build_engine(database_url)
        try:
            repository = SqlPackLifecycleRepository(engine)
            await repository.register(
                pack_id=pack_id,
                version="1.0.0",
                manifest=manifest_v1,
                sdk_version="1.0.0",
                min_kernel_version="1.0.0",
                actor="test-actor",
                reason="initial install",
                pack_root=tmp_path,
            )
            await repository.activate(pack_id=pack_id, actor="test-actor", reason="go live")

            before = await _agents_for(database_url, pack_id)
            assert set(before) == {f"{pack_id}/analyst", f"{pack_id}/builder"}

            record = await repository.upgrade(
                pack_id=pack_id,
                version="2.0.0",
                manifest=manifest_v2,
                sdk_version="1.0.0",
                min_kernel_version="1.0.0",
                pack_root=tmp_path,
                actor="test-actor",
                reason="upgrade",
            )

            assert record.version == "2.0.0"
            assert record.state is PackState.ACTIVATED
            assert record.manifest == manifest_v2

            after = await _agents_for(database_url, pack_id)
            assert set(after) == {f"{pack_id}/analyst", f"{pack_id}/reviewer"}
            assert after[f"{pack_id}/analyst"] == {
                "version": "2.0.0",
                "permissions": ["llm:invoke", "knowledge:read"],
            }
            assert after[f"{pack_id}/reviewer"] == {
                "version": "2.0.0",
                "permissions": ["llm:invoke"],
            }

            # The migrated, still-activated pack is genuinely usable —
            # this ticket's own Output: "A migrated, activated pack."
            registry = SqlAgentRegistry(engine)
            resolved = await registry.resolve_agent(f"{pack_id}/analyst")
            assert isinstance(resolved, EchoAgent)
            with pytest.raises(AgentNotRegisteredError, match="no agent registered"):
                await registry.resolve_agent(f"{pack_id}/builder")
        finally:
            await engine.dispose()

    asyncio.run(_run())
    assert asyncio.run(_transitions_for(database_url, "test.upgrade_migrates_agents")) == [
        ("discovered", "installed"),
        ("installed", "activated"),
        ("activated", "activated"),
    ]


def test_upgrade_refuses_a_same_or_older_version_without_touching_any_row(
    database_url: str, tmp_path: Path
) -> None:
    """The required failure-case proof: an invalid upgrade (no real
    forward progress) is refused outright, and the pack's real state is
    provably unchanged afterward — not silently corrupted."""

    async def _run() -> None:
        pack_id = "test.upgrade_refuses_regression"
        manifest_v1 = {
            "name": "test-pack",
            "agents": [_agent_entry("analyst", version="1.0.0", permissions=["llm:invoke"])],
        }

        engine = build_engine(database_url)
        try:
            repository = SqlPackLifecycleRepository(engine)
            await repository.register(
                pack_id=pack_id,
                version="1.0.0",
                manifest=manifest_v1,
                sdk_version="1.0.0",
                min_kernel_version="1.0.0",
                actor="test-actor",
                reason="initial install",
                pack_root=tmp_path,
            )
            await repository.activate(pack_id=pack_id, actor="test-actor", reason="go live")

            for regressive_version in ("1.0.0", "0.9.0"):
                with pytest.raises(InvalidPackUpgradeError, match="strictly newer"):
                    await repository.upgrade(
                        pack_id=pack_id,
                        version=regressive_version,
                        manifest={"name": "test-pack", "agents": []},
                        sdk_version="1.0.0",
                        min_kernel_version="1.0.0",
                        pack_root=tmp_path,
                        actor="test-actor",
                        reason="attempted regression",
                    )

            record = await repository.get_pack(pack_id)
            assert record is not None
            assert record.version == "1.0.0"
            assert record.manifest == manifest_v1

            unchanged_agents = await _agents_for(database_url, pack_id)
            assert set(unchanged_agents) == {f"{pack_id}/analyst"}
        finally:
            await engine.dispose()

    asyncio.run(_run())
    # No "activated -> activated" upgrade transition was ever recorded.
    assert asyncio.run(_transitions_for(database_url, "test.upgrade_refuses_regression")) == [
        ("discovered", "installed"),
        ("installed", "activated"),
    ]


def test_upgrade_refuses_a_pack_that_is_not_currently_activated(
    database_url: str, tmp_path: Path
) -> None:
    async def _run() -> None:
        pack_id = "test.upgrade_refuses_not_activated"
        engine = build_engine(database_url)
        try:
            repository = SqlPackLifecycleRepository(engine)
            await repository.register(
                pack_id=pack_id,
                version="1.0.0",
                manifest=_MANIFEST,
                sdk_version="1.0.0",
                min_kernel_version="1.0.0",
                actor="test-actor",
                reason="initial install",
            )

            with pytest.raises(InvalidPackTransitionError, match=pack_id):
                await repository.upgrade(
                    pack_id=pack_id,
                    version="2.0.0",
                    manifest=_MANIFEST,
                    sdk_version="1.0.0",
                    min_kernel_version="1.0.0",
                    pack_root=tmp_path,
                    actor="test-actor",
                    reason="premature upgrade",
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())
