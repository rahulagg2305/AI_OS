"""Add workflow_instances.run_manifest_id -> evaluation.run_manifests FK.

Revision ID: 0013_workflow_run_manifest_fk
Revises: 0012_evaluation_run_manifests
Create Date: 2026-07-26

Retrofits the foreign key ``persistence/schema.py`` has deferred since
the baseline migration (data_model.md §4.1: ``run_manifest_id`` | text
NULL | FK -> ``evaluation.run_manifests``). The column itself
(``workflow.workflow_instances.run_manifest_id``, nullable) has existed
since ``0001_workflow_state_baseline``; the target table
(``evaluation.run_manifests``) was added in ``0012_evaluation_run_manifests``.
Both prerequisites now exist, so this migration only adds the constraint
— no new column, no new table.

This is a single ``ALTER TABLE ... ADD CONSTRAINT``, not a
``create_table``: unlike every migration so far, the table being altered
already exists and already has rows in any real deployment (none yet in
practice, but the migration is written as a genuine ALTER regardless).

Does not touch ``experiment_id`` (still deferred: ``evaluation.experiments``
does not exist yet) or ``definition_id`` (still deferred: blocked on the
open ``definition_id`` versioning ambiguity, data_model.md §4.1 vs. §5) —
neither is in scope for this step.

See :mod:`ai_os_kernel.persistence.cross_schema_foreign_keys` for why the
corresponding SQLAlchemy Core change lives in its own module rather than
inline in ``persistence/schema.py``.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0013_workflow_run_manifest_fk"
down_revision: str | None = "0012_evaluation_run_manifests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FK_NAME = "fk_workflow_instances_run_manifest_id"


def upgrade() -> None:
    op.create_foreign_key(
        _FK_NAME,
        "workflow_instances",
        "run_manifests",
        ["run_manifest_id"],
        ["run_manifest_id"],
        source_schema="workflow",
        referent_schema="evaluation",
    )


def downgrade() -> None:
    op.drop_constraint(
        _FK_NAME,
        "workflow_instances",
        schema="workflow",
        type_="foreignkey",
    )
