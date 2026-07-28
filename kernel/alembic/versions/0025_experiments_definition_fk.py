"""Add experiments (definition_id, definition_version) -> workflow_definitions FK.

Revision ID: 0025_experiments_definition_fk
Revises: 0024_catalog_prompts_pk
Create Date: 2026-07-26

Retrofits the foreign key `evaluation_schema.py` has deferred since
`evaluation.experiments` was created: `experiments.definition_id` +
`experiments.definition_version` -> `catalog.workflow_definitions
(definition_id, version)`. The two blockers that previously applied
here are both resolved: the `definition_id`/`version` composite-key
ambiguity was settled in a documentation-only step, and
`SqlWorkflowDefinitionCatalog` now exists so a real definition can
actually be registered before anything references it —
`workflow_instances`' own identical composite FK to the same target
(`0023_workflow_definition_fk`) is already enforced and passing.

Verified safe against the existing test suite before writing this
migration, not assumed: every `evaluation.experiments` row inserted by
`tests/integration/persistence/test_migrations.py` already uses the
`(def_test, 1.0.0)` pair that file's own autouse fixture
(`_ensure_default_workflow_definition_registered`) guarantees exists in
`catalog.workflow_definitions` before every test in that file runs.

Schema only — no writer exists for `evaluation.experiments` yet (the
Evaluation Engine is not built).
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0025_experiments_definition_fk"
down_revision: str | None = "0024_catalog_prompts_pk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FK_NAME = "fk_experiments_definition_id_version"


def upgrade() -> None:
    op.create_foreign_key(
        _FK_NAME,
        "experiments",
        "workflow_definitions",
        ["definition_id", "definition_version"],
        ["definition_id", "version"],
        source_schema="evaluation",
        referent_schema="catalog",
    )


def downgrade() -> None:
    op.drop_constraint(
        _FK_NAME,
        "experiments",
        schema="evaluation",
        type_="foreignkey",
    )
