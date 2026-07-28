"""Add experiment_runs.experiment_id -> experiments.experiment_id FK.

Revision ID: 0016_experiment_runs_exp_fk
Revises: 0015_evaluation_experiments
Create Date: 2026-07-26

Retrofits the one foreign key `evaluation_schema.py` flagged as deferred
when `experiment_runs` was added (0014_evaluation_experiment_runs):
`experiment_runs.experiment_id` -> `experiments.experiment_id`. Now that
`experiments` exists (0015_evaluation_experiments), this is a trivial,
unambiguous same-schema retrofit — unlike the cross-module
`workflow_instances.run_manifest_id` retrofit
(0013_workflow_run_manifest_fk), both tables here already share the
`evaluation` schema and the same SQLAlchemy `MetaData`
(`evaluation_schema.py`), so no circular-import wiring module is needed;
the constraint is attached directly in that module via
`experiment_runs.append_constraint(...)`.

A single `ALTER TABLE ... ADD CONSTRAINT` — no new column, no new table.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0016_experiment_runs_exp_fk"
down_revision: str | None = "0015_evaluation_experiments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FK_NAME = "fk_experiment_runs_experiment_id"


def upgrade() -> None:
    op.create_foreign_key(
        _FK_NAME,
        "experiment_runs",
        "experiments",
        ["experiment_id"],
        ["experiment_id"],
        source_schema="evaluation",
        referent_schema="evaluation",
    )


def downgrade() -> None:
    op.drop_constraint(
        _FK_NAME,
        "experiment_runs",
        schema="evaluation",
        type_="foreignkey",
    )
