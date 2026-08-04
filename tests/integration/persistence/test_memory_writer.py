"""SqlMemoryStore against real Postgres (ADR-0015 — no mocking the
database). Proves a real memory item is genuinely written to and
queryable back from ``knowledge.memory_items``: structural filtering
by ``memory_type``/``source_workflow_id``, a real FK to a real
workflow instance, and deterministic ordering.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Generator
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.memory_writer import MemoryWriteError, SqlMemoryStore
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from tests.integration._postgres_fixture import postgres_container

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
    definition_id = "test.memory-writer-workflow"
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


def test_write_memory_is_readable_back_with_real_defaults(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            workflow_id = await _create_real_workflow_instance(database_url, engine)
            store = SqlMemoryStore(engine)

            record = await store.write_memory(
                memory_type="engineering",
                content="the retry policy caps at 3 attempts",
                source_workflow_id=workflow_id,
            )

            assert record.memory_id.startswith("mem_")
            assert record.promoted_at is None
            assert record.quality_signal is None
            assert record.expires_at is None
            assert record.provenance == {}

            results = await store.query_memories(source_workflow_id=workflow_id, limit=10)
            assert len(results) == 1
            assert results[0].memory_id == record.memory_id
            assert results[0].content == "the retry policy caps at 3 attempts"
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_write_memory_persists_real_optional_fields(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            workflow_id = await _create_real_workflow_instance(database_url, engine)
            store = SqlMemoryStore(engine)

            record = await store.write_memory(
                memory_type="asset",
                content="generated diagram for the delivery pipeline",
                source_workflow_id=workflow_id,
                quality_signal=Decimal("0.875"),
                provenance={"generated_by": "test-agent"},
            )

            results = await store.query_memories(
                source_workflow_id=workflow_id, memory_type="asset", limit=10
            )
            assert len(results) == 1
            assert results[0].quality_signal == Decimal("0.875000")
            assert results[0].provenance == {"generated_by": "test-agent"}
            assert record.memory_type == "asset"
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_query_memories_filters_by_type_across_a_shared_workflow(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            workflow_id = await _create_real_workflow_instance(database_url, engine)
            store = SqlMemoryStore(engine)

            engineering_memory = await store.write_memory(
                memory_type="engineering",
                content="use exponential backoff for retries",
                source_workflow_id=workflow_id,
            )
            workflow_memory = await store.write_memory(
                memory_type="workflow",
                content="this run took 4 attempts to succeed",
                source_workflow_id=workflow_id,
            )

            engineering_only = await store.query_memories(
                source_workflow_id=workflow_id, memory_type="engineering", limit=10
            )
            assert [r.memory_id for r in engineering_only] == [engineering_memory.memory_id]

            both = await store.query_memories(source_workflow_id=workflow_id, limit=10)
            assert {r.memory_id for r in both} == {
                engineering_memory.memory_id,
                workflow_memory.memory_id,
            }
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_query_memories_from_a_different_workflow_are_isolated(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            workflow_id_a = await _create_real_workflow_instance(database_url, engine)
            workflow_id_b = await _create_real_workflow_instance(database_url, engine)
            store = SqlMemoryStore(engine)

            await store.write_memory(
                memory_type="workflow",
                content="memory from workflow A",
                source_workflow_id=workflow_id_a,
            )
            memory_b = await store.write_memory(
                memory_type="workflow",
                content="memory from workflow B",
                source_workflow_id=workflow_id_b,
            )

            results = await store.query_memories(source_workflow_id=workflow_id_b, limit=10)
            assert [r.memory_id for r in results] == [memory_b.memory_id]
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_write_memory_rejects_blank_content(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            workflow_id = await _create_real_workflow_instance(database_url, engine)
            store = SqlMemoryStore(engine)

            with pytest.raises(MemoryWriteError, match="content must not be blank"):
                await store.write_memory(
                    memory_type="workflow", content="   ", source_workflow_id=workflow_id
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_write_memory_rejects_an_unknown_workflow_id(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            store = SqlMemoryStore(engine)

            with pytest.raises(MemoryWriteError):
                await store.write_memory(
                    memory_type="workflow",
                    content="orphaned memory",
                    source_workflow_id="wf_does_not_exist",
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())
