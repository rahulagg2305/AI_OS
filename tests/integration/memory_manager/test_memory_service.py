"""`MemoryService` over the real `SqlMemoryStore` against real Postgres
(ADR-0015 — no mocking the database), `P02-S04-M10-T04`.

The unit tests substitute a real fake store. These deliberately do not:
they run the **actually-produced** path end to end — `MemoryService.write()`
→ real `SqlMemoryStore` → a real committed row in
`knowledge.memory_items` — and assert on the row Postgres genuinely
holds, read back through the real query path and by direct SQL for the
columns that path does not expose. A hand-built record standing in for
a real produced one is exactly the class of gap that let a defect
survive in `P02-S06-M15-T11`.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Generator
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine
from tests.integration._postgres_fixture import postgres_container

from ai_os_kernel.context_manager.models import ContextRequest
from ai_os_kernel.context_manager.resolvers import MemoryResolver
from ai_os_kernel.memory_manager import PROVENANCE_SCHEMA_VERSION, MemoryService, MemoryWrite
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.memory_writer import MemoryWriteError, SqlMemoryStore
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"


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


async def _ensure_workflow_definition_registered(
    database_url: str, *, definition_id: str, version: str
) -> None:
    engine = build_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                sa.text(
                    "INSERT INTO catalog.workflow_definitions "
                    "(definition_id, version, pack_id, graph, inputs_schema, "
                    " outputs_schema, declared_permissions, validated_at) "
                    "VALUES (:definition_id, :version, 'test.pack', '{}'::jsonb, "
                    " '{}'::jsonb, '{}'::jsonb, '[]'::jsonb, now()) "
                    "ON CONFLICT (definition_id, version) DO NOTHING"
                ),
                {"definition_id": definition_id, "version": version},
            )
    finally:
        await engine.dispose()


async def _create_real_workflow_instance(database_url: str, engine: AsyncEngine) -> str:
    definition_id = "test.memory-service-workflow"
    version = "1.0.0"
    await _ensure_workflow_definition_registered(
        database_url, definition_id=definition_id, version=version
    )
    instance = await SqlWorkflowInstanceRepository(engine).create(
        definition_id=definition_id,
        definition_version=version,
        inputs={},
        principal_id="test-principal",
    )
    return instance.workflow_id


def test_a_mediated_write_genuinely_reaches_postgres(database_url: str) -> None:
    """The real produced path: what `MemoryService` returns must match
    the row Postgres actually holds."""

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            workflow_id = await _create_real_workflow_instance(database_url, engine)
            service = MemoryService(SqlMemoryStore(engine))

            ref = await service.write(
                MemoryWrite(
                    memory_type="engineering",
                    content="the retry policy caps at 3 attempts",
                    source_workflow_id=workflow_id,
                    quality_signal=Decimal("0.75"),
                    step_id="analyze",
                    agent_id="se.architect",
                )
            )

            assert ref.memory_id.startswith("mem_")
            assert ref.memory_type == "engineering"

            # Read back through the real query path, not a fixture.
            stored = await SqlMemoryStore(engine).query_memories(
                source_workflow_id=workflow_id, limit=10
            )
            assert len(stored) == 1
            row = stored[0]
            assert row.memory_id == ref.memory_id
            assert row.content == "the retry policy caps at 3 attempts"
            assert row.memory_type == "engineering"
            assert row.quality_signal == Decimal("0.75")
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_mediated_write_is_never_already_promoted(database_url: str) -> None:
    """`MemoryWrite` cannot express `promoted_at`, so the real committed
    row must carry `NULL` — asserted against the column itself, since
    the structural guard is only worth as much as what lands on disk."""

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            workflow_id = await _create_real_workflow_instance(database_url, engine)

            ref = await MemoryService(SqlMemoryStore(engine)).write(
                MemoryWrite(
                    memory_type="engineering",
                    content="a lesson worth keeping",
                    source_workflow_id=workflow_id,
                )
            )

            async with engine.connect() as connection:
                promoted_at = (
                    await connection.execute(
                        sa.text(
                            "SELECT promoted_at FROM knowledge.memory_items "
                            "WHERE memory_id = :memory_id"
                        ),
                        {"memory_id": ref.memory_id},
                    )
                ).scalar_one()

            assert promoted_at is None
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_computed_provenance_survives_the_real_jsonb_round_trip(database_url: str) -> None:
    """`P02-S04-M10-T05` against real Postgres: the composed record has
    to come back out of the real `jsonb` column intact, not merely be
    correct in memory before the insert."""

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            workflow_id = await _create_real_workflow_instance(database_url, engine)

            ref = await MemoryService(SqlMemoryStore(engine)).write(
                MemoryWrite(
                    memory_type="engineering",
                    content="prefer perf_counter for elapsed time",
                    source_workflow_id=workflow_id,
                    step_id="analyze",
                    agent_id="se.architect",
                )
            )

            stored = await SqlMemoryStore(engine).query_memories(
                source_workflow_id=workflow_id, limit=10
            )
            provenance = next(r.provenance for r in stored if r.memory_id == ref.memory_id)

            assert provenance["schemaVersion"] == PROVENANCE_SCHEMA_VERSION
            # Verified, not asserted: this id passed a real FK check.
            assert provenance["workflowId"] == workflow_id
            assert provenance["stepId"] == "analyze"
            assert provenance["agentId"] == "se.architect"
            assert provenance["trust"] == "untrusted"
            assert provenance["recordedBy"] == "ai_os_kernel.memory_manager.MemoryService"
            # A real, parseable timestamp, not a string that merely looks like one.
            assert datetime.fromisoformat(provenance["recordedAt"]).tzinfo is not None
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_an_unknown_workflow_is_refused_by_the_real_foreign_key(database_url: str) -> None:
    """`source_workflow_id` is a real FK to `workflow.workflow_instances`.
    A well-formed id that does not exist must still be rejected — the
    boundary model checks shape, the database checks truth."""

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            service = MemoryService(SqlMemoryStore(engine))
            with pytest.raises(MemoryWriteError):
                await service.write(
                    MemoryWrite(
                        memory_type="workflow",
                        content="orphaned",
                        source_workflow_id="wf_does_not_exist",
                    )
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_written_memory_is_visible_to_the_real_context_manager_resolver(
    database_url: str,
) -> None:
    """The write side finally feeds the read side that was already
    wired. `MemoryResolver` is composed unconditionally in
    `bootstrap.py` over `memory_type="engineering"`, and until this
    service existed nothing in production ever wrote a row for it to
    find. This proves the two genuinely meet.
    """

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            workflow_id = await _create_real_workflow_instance(database_url, engine)
            ref = await MemoryService(SqlMemoryStore(engine)).write(
                MemoryWrite(
                    memory_type="engineering",
                    content="prefer perf_counter for elapsed time",
                    source_workflow_id=workflow_id,
                )
            )

            resolver = MemoryResolver(
                memory_store=SqlMemoryStore(engine), memory_type="engineering", limit=50
            )
            items = await resolver.resolve(
                ContextRequest(workflow_id=workflow_id, step_id="any-step")
            )

            matching = [
                item
                for item in items
                if item.provenance.identifier == f"memory_item:{ref.memory_id}"
            ]
            assert len(matching) == 1, [item.provenance.identifier for item in items]
            assert matching[0].content == "prefer perf_counter for elapsed time"
        finally:
            await engine.dispose()

    asyncio.run(_run())
