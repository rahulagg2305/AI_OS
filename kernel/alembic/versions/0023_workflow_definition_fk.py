"""Add workflow_instances (definition_id, definition_version) -> catalog.workflow_definitions FK.

Revision ID: 0023_workflow_definition_fk
Revises: 0022_pack_state_transitions
Create Date: 2026-07-26

Retrofits the foreign key `persistence/schema.py` has deferred since the
baseline migration: `workflow_instances.definition_id` +
`workflow_instances.definition_version` -> `catalog.workflow_definitions
(definition_id, version)`. A genuine composite foreign key, possible
since `0021_catalog_wf_definitions_pk` gave `workflow_definitions`
exactly that composite primary key.

This retrofit was attempted once before (a since-deleted migration) and
reverted after verifying it broke 37 of 39
`tests/integration/workflow_engine/` tests: nothing wrote a row to
`catalog.workflow_definitions`, while `SqlWorkflowInstanceRepository.
create()` already wrote `workflow_instances` rows unconditionally. It is
safe now: `WorkflowInstanceService.create_instance()` registers the
definition via the new `SqlWorkflowDefinitionCatalog` (an idempotent
upsert) immediately before creating the instance that references it, on
every call. No data-migration concern: no real deployment has any
`workflow_instances` rows yet.

Historical correction: earlier reports and
`ai_os_kernel.persistence.catalog_schema`'s own docstring described this
as a "`workflow_instances`/`workflow_events`" foreign key.
`workflow_events` never had a `definition_id`/`definition_version`
column at all (checked directly against data_model.md §4.2), so only
`workflow_instances` needed this retrofit.

Schema only — the writer this migration depends on
(`SqlWorkflowDefinitionCatalog`) is application code, not part of this
migration.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0023_workflow_definition_fk"
down_revision: str | None = "0022_pack_state_transitions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FK_NAME = "fk_workflow_instances_definition_id_version"


def upgrade() -> None:
    op.create_foreign_key(
        _FK_NAME,
        "workflow_instances",
        "workflow_definitions",
        ["definition_id", "definition_version"],
        ["definition_id", "version"],
        source_schema="workflow",
        referent_schema="catalog",
    )


def downgrade() -> None:
    op.drop_constraint(
        _FK_NAME,
        "workflow_instances",
        schema="workflow",
        type_="foreignkey",
    )
