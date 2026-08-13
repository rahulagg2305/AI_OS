"""Shared fixtures for ``tests/integration/workflow_engine``.

Every test module in this package defines its own module-scoped
``database_url`` fixture (its own ephemeral Postgres container, migrated
to head). ``workflow_instances`` now carries a real composite foreign
key to ``catalog.workflow_definitions`` (data_model.md §4.1), and every
test across this package that creates an instance uses the same
(``se.product_creation``, ``1.0.0``) definition. This autouse fixture
ensures that one row exists before any test runs — an idempotent
upsert (via the real writer, `ON CONFLICT DO NOTHING` under the hood —
see :meth:`~ai_os_kernel.workflow_engine.definition_catalog.
SqlWorkflowDefinitionCatalog.register`'s own docstring), not a hard
dependency on test ordering — so tests that go through
:class:`~ai_os_kernel.workflow_engine.repository.SqlWorkflowInstanceRepository`
directly (bypassing
:class:`~ai_os_kernel.workflow_engine.service.WorkflowInstanceService`,
which would otherwise register it itself) are covered too.

**Uses the real `SqlWorkflowDefinitionCatalog.register()`, not a raw
SQL insert (fixed 2026-08-10, found while building `list_all()` /
`GET /api/v1/workflow_definitions`, `P06-S01-M36-T04`).** A prior
version hand-inserted a row with `graph = '{}'::jsonb` — enough to
satisfy the FK, but not a genuinely valid `WorkflowDefinition` (missing
`name`/`description`/`steps`/`failureHandling`), so any real reader
that reconstructs the full definition back out (the new `list_all()`)
genuinely crashed on it. `register()` needs a real, complete
`WorkflowDefinition`, so this now builds and validates the smallest
one that satisfies it (`_at_least_one_step` requires at least one real
step) — real, representative test data, not a shape that only happens
to satisfy one caller's own foreign key.

Depends on ``database_url`` by name, which pytest resolves to whichever
module-local ``database_url`` fixture is active for the test currently
running — so this always runs after that module's own migrations.
"""

import asyncio

import pytest

from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.workflow_engine.definition_catalog import SqlWorkflowDefinitionCatalog
from ai_os_kernel.workflow_engine.models import WorkflowDefinition

_DEFAULT_DEFINITION_ID = "se.product_creation"
_DEFAULT_DEFINITION_VERSION = "1.0.0"
_DEFAULT_PACK_ID = "se.software_engineering"


def _default_definition() -> WorkflowDefinition:
    return WorkflowDefinition.model_validate(
        {
            "id": _DEFAULT_DEFINITION_ID,
            "name": "Product Creation (conftest default)",
            "description": "The smallest valid definition satisfying every real "
            "workflow_instances FK across this package's own tests.",
            "version": _DEFAULT_DEFINITION_VERSION,
            "inputs": {"type": "object"},
            "outputs": {"type": "object"},
            "steps": [
                {"id": "noop", "type": "agent", "agentId": "se.software_engineering/analyst"}
            ],
            "failureHandling": {"onError": "halt"},
        }
    )


@pytest.fixture(autouse=True)
def _ensure_default_workflow_definition_registered(database_url: str) -> None:
    async def _ensure() -> None:
        engine = build_engine(database_url)
        try:
            await SqlWorkflowDefinitionCatalog(engine).register(
                definition=_default_definition(), pack_id=_DEFAULT_PACK_ID
            )
        finally:
            await engine.dispose()

    asyncio.run(_ensure())
