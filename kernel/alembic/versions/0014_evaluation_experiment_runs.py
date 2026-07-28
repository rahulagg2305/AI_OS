"""Add evaluation.experiment_runs.

Revision ID: 0014_evaluation_experiment_runs
Revises: 0013_workflow_run_manifest_fk
Create Date: 2026-07-26

Creates ``evaluation.experiment_runs`` per docs/08_database/data_model.md
§6 — the second of the six `evaluation` tables (`run_manifests` was the
first). `experiments`, `metrics`, `gate_results`, `llm_calls` remain
undocumented-scope for this step. Column-for-column mirror of
:mod:`ai_os_kernel.persistence.evaluation_schema` — see that module's
docstring for the full reasoning, including why `experiment_runs` was
chosen over `metrics` (the latter has an unspecified `numeric`
precision/scale and a `run_id` FK to this very table).

``workflow_id`` gets a real foreign key to ``workflow.workflow_instances``,
mirroring ``run_manifests.workflow_id`` exactly. ``experiment_id`` gets
no foreign key: ``evaluation.experiments`` does not exist yet.

Schema and migration only — no writer. No Evaluation Engine exists yet
to run an experiment or record one of its runs.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0014_evaluation_experiment_runs"
down_revision: str | None = "0013_workflow_run_manifest_fk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "experiment_runs",
        sa.Column("run_id", sa.Text, primary_key=True),
        sa.Column("experiment_id", sa.Text, nullable=False),
        sa.Column(
            "workflow_id",
            sa.Text,
            sa.ForeignKey("workflow.workflow_instances.workflow_id"),
            nullable=False,
        ),
        sa.Column("variant_key", sa.Text, nullable=False),
        sa.Column("model_alias", sa.Text, nullable=False),
        sa.Column("resolved_model_id", sa.Text, nullable=False),
        sa.Column("replicate_index", sa.Integer, nullable=False),
        sa.Column("served_from_cache", sa.Boolean, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        schema="evaluation",
    )
    op.create_index(
        "ix_experiment_runs_workflow_id",
        "experiment_runs",
        ["workflow_id"],
        schema="evaluation",
    )
    op.create_index(
        "ix_experiment_runs_experiment_id",
        "experiment_runs",
        ["experiment_id"],
        schema="evaluation",
    )


def downgrade() -> None:
    op.drop_table("experiment_runs", schema="evaluation")
