"""Shared fixtures for ``tests/integration/workflow_engine``.

Every test module in this package defines its own module-scoped
``database_url`` fixture (its own ephemeral Postgres container, migrated
to head). ``workflow_instances`` now carries a real composite foreign
key to ``catalog.workflow_definitions`` (data_model.md §4.1), and every
test across this package that creates an instance uses the same
(``se.product_creation``, ``1.0.0``) definition. This autouse fixture
ensures that one row exists before any test runs — an idempotent
``ON CONFLICT DO NOTHING`` upsert, not a hard dependency on test
ordering — so tests that go through
:class:`~ai_os_kernel.workflow_engine.repository.SqlWorkflowInstanceRepository`
directly (bypassing
:class:`~ai_os_kernel.workflow_engine.service.WorkflowInstanceService`,
which would otherwise register it itself) are covered too.

Depends on ``database_url`` by name, which pytest resolves to whichever
module-local ``database_url`` fixture is active for the test currently
running — so this always runs after that module's own migrations.
"""

import asyncio

import pytest
import sqlalchemy as sa

from ai_os_kernel.persistence.engine import build_engine

_DEFAULT_DEFINITION_ID = "se.product_creation"
_DEFAULT_DEFINITION_VERSION = "1.0.0"
_DEFAULT_PACK_ID = "se.software_engineering"


@pytest.fixture(autouse=True)
def _ensure_default_workflow_definition_registered(database_url: str) -> None:
    async def _ensure() -> None:
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO catalog.workflow_definitions "
                        "(definition_id, version, pack_id, graph, inputs_schema, "
                        " outputs_schema, declared_permissions, validated_at) "
                        "VALUES (:definition_id, :version, :pack_id, '{}'::jsonb, "
                        " '{}'::jsonb, '{}'::jsonb, '[]'::jsonb, now()) "
                        "ON CONFLICT (definition_id, version) DO NOTHING"
                    ),
                    {
                        "definition_id": _DEFAULT_DEFINITION_ID,
                        "version": _DEFAULT_DEFINITION_VERSION,
                        "pack_id": _DEFAULT_PACK_ID,
                    },
                )
        finally:
            await engine.dispose()

    asyncio.run(_ensure())
