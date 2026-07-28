"""Add evaluation.experiments.

Revision ID: 0015_evaluation_experiments
Revises: 0014_evaluation_experiment_runs
Create Date: 2026-07-26

Creates ``evaluation.experiments`` per docs/08_database/data_model.md
§6 — the third of the six `evaluation` tables (`run_manifests`,
`experiment_runs` came first). `metrics`, `gate_results`, `llm_calls`
remain undocumented-scope for this step; `metrics` specifically is
deferred a second time (its `metric_value numeric` column has no
documented precision/scale). Column-for-column mirror of
:mod:`ai_os_kernel.persistence.evaluation_schema` — see that module's
docstring for the full reasoning.

No foreign key on ``definition_id``/``definition_version`` — deliberately
consistent with the identical, still-open deferral already on
``workflow.workflow_instances`` and ``catalog.workflow_definitions``
(data_model.md §4.1 vs. §5 versioning ambiguity). Not this migration's
decision to resolve.

Schema and migration only — no writer. No Evaluation Engine exists yet
to define or run an experiment.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0015_evaluation_experiments"
down_revision: str | None = "0014_evaluation_experiment_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "experiments",
        sa.Column("experiment_id", sa.Text, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("definition_id", sa.Text, nullable=False),
        sa.Column("definition_version", sa.Text, nullable=False),
        sa.Column("variables", JSONB, nullable=False),
        sa.Column("pinned_conditions", JSONB, nullable=False),
        sa.Column("runs_per_variant", sa.Integer, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("created_by", sa.Text, nullable=False),
        schema="evaluation",
    )
    op.create_index(
        "ix_experiments_definition_id",
        "experiments",
        ["definition_id"],
        schema="evaluation",
    )
    op.create_index(
        "ix_experiments_status",
        "experiments",
        ["status"],
        schema="evaluation",
    )


def downgrade() -> None:
    op.drop_table("experiments", schema="evaluation")
