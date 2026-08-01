"""SqlWorkflowDefinitionCatalog against a real Postgres container
(ADR-0015 — no mocking the database). Proves: registration writes the
documented columns with the reasoned content
(:mod:`ai_os_kernel.workflow_engine.definition_catalog`), is idempotent
per ``(definition_id, version)``, and treats two versions of the same
``definition_id`` as two distinct rows.
"""

import asyncio
import os
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.workflow_engine.definition_catalog import SqlWorkflowDefinitionCatalog
from ai_os_kernel.workflow_engine.models import WorkflowDefinition
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


def _definition(
    *, definition_id: str = "se.definition_catalog_test", version: str
) -> WorkflowDefinition:
    return WorkflowDefinition.model_validate(
        {
            "id": definition_id,
            "name": "Definition Catalog Test",
            "description": "Exercises SqlWorkflowDefinitionCatalog directly.",
            "version": version,
            "inputs": {
                "type": "object",
                "properties": {"specPath": {"type": "string"}},
                "required": ["specPath"],
            },
            "outputs": {"type": "object"},
            "steps": [
                {
                    "id": "analyze_requirements",
                    "type": "agent",
                    "agentId": "se.software_engineering/analyst",
                }
            ],
            "failureHandling": {"onError": "escalate"},
        }
    )


async def _fetch_row(
    database_url: str, *, definition_id: str, version: str
) -> dict[str, Any] | None:
    engine = build_engine(database_url)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                sa.text(
                    "SELECT * FROM catalog.workflow_definitions "
                    "WHERE definition_id = :definition_id AND version = :version"
                ),
                {"definition_id": definition_id, "version": version},
            )
            row = result.mappings().one_or_none()
            return dict(row) if row is not None else None
    finally:
        await engine.dispose()


def test_register_writes_the_documented_columns(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            catalog = SqlWorkflowDefinitionCatalog(engine)
            definition = _definition(version="1.0.0")

            await catalog.register(definition=definition, pack_id="se.software_engineering")

            row = await _fetch_row(
                database_url, definition_id="se.definition_catalog_test", version="1.0.0"
            )
            assert row is not None
            assert row["pack_id"] == "se.software_engineering"
            assert row["inputs_schema"] == definition.inputs
            assert row["outputs_schema"] == definition.outputs
            assert row["declared_permissions"] == []
            assert row["validated_at"] is not None
            # graph excludes id/version/inputs/outputs (already their own
            # columns) but keeps everything else the definition declared.
            assert row["graph"]["name"] == "Definition Catalog Test"
            # model_dump(by_alias=True) includes every field, including
            # every None default (joinPolicy, toolId/promptId/
            # promptVersion/modelAlias, and now condition/branches, added
            # by P02-S01-M05-T09, for this agent step) — the graph column
            # faithfully mirrors the complete validated definition, not a
            # hand-picked subset of it.
            assert row["graph"]["steps"] == [
                {
                    "id": "analyze_requirements",
                    "type": "agent",
                    "joinPolicy": None,
                    "agentId": "se.software_engineering/analyst",
                    "toolId": None,
                    "promptId": None,
                    "promptVersion": None,
                    "modelAlias": None,
                    "condition": None,
                    "branches": None,
                }
            ]
            assert "id" not in row["graph"]
            assert "version" not in row["graph"]
            assert "inputs" not in row["graph"]
            assert "outputs" not in row["graph"]
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_register_is_idempotent_for_the_same_definition_id_and_version(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            catalog = SqlWorkflowDefinitionCatalog(engine)
            definition = _definition(
                definition_id="se.definition_catalog_idempotent", version="1.0.0"
            )

            await catalog.register(definition=definition, pack_id="se.software_engineering")
            # A second registration of the identical (definition_id,
            # version) is a no-op, not an error and not an overwrite —
            # data_model.md §5: "versions are immutable."
            await catalog.register(definition=definition, pack_id="se.software_engineering")

            engine_for_count = build_engine(database_url)
            try:
                async with engine_for_count.connect() as connection:
                    result = await connection.execute(
                        sa.text(
                            "SELECT count(*) FROM catalog.workflow_definitions "
                            "WHERE definition_id = 'se.definition_catalog_idempotent'"
                        )
                    )
                    assert result.scalar_one() == 1
            finally:
                await engine_for_count.dispose()
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_register_treats_two_versions_of_the_same_definition_as_distinct_rows(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            catalog = SqlWorkflowDefinitionCatalog(engine)
            definition_id = "se.definition_catalog_versions"

            await catalog.register(
                definition=_definition(definition_id=definition_id, version="1.0.0"),
                pack_id="se.software_engineering",
            )
            await catalog.register(
                definition=_definition(definition_id=definition_id, version="2.0.0"),
                pack_id="se.software_engineering",
            )

            first = await _fetch_row(database_url, definition_id=definition_id, version="1.0.0")
            second = await _fetch_row(database_url, definition_id=definition_id, version="2.0.0")
            assert first is not None
            assert second is not None
        finally:
            await engine.dispose()

    asyncio.run(_run())
