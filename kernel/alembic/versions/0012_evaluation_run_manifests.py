"""Add evaluation.run_manifests.

Revision ID: 0012_evaluation_run_manifests
Revises: 0011_catalog_agents
Create Date: 2026-07-26

Creates ``evaluation.run_manifests`` per docs/08_database/data_model.md
§6 — one table only, not the full `evaluation` schema (`experiments`,
`experiment_runs`, `metrics`, `gate_results`, `llm_calls` remain
undocumented-scope for this step). Column-for-column mirror of
:mod:`ai_os_kernel.persistence.evaluation_schema` — see that module's
docstring for the full reasoning.

``workflow_id`` gets a real foreign key to ``workflow.workflow_instances``
— unlike every table added in the `governance`/`platform`/`trace`/
`catalog` steps, the target here already exists, so nothing is
deferred. This migration does not retrofit the reverse, already-deferred
foreign key noted in ``persistence/schema.py``'s own docstring
(``workflow_instances.run_manifest_id`` → ``evaluation.run_manifests``)
— that remains a distinct, later step, and this migration does not
touch any ``workflow`` schema table.

Schema and migration only — no writer. No Evaluation Engine exists yet
to assemble or write a run manifest.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0012_evaluation_run_manifests"
down_revision: str | None = "0011_catalog_agents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS evaluation")

    op.create_table(
        "run_manifests",
        sa.Column("run_manifest_id", sa.Text, primary_key=True),
        sa.Column(
            "workflow_id",
            sa.Text,
            sa.ForeignKey("workflow.workflow_instances.workflow_id"),
            nullable=False,
        ),
        sa.Column("manifest", JSONB, nullable=False),
        sa.Column("manifest_hash", sa.Text, nullable=False),
        schema="evaluation",
    )
    op.create_index(
        "ix_run_manifests_workflow_id",
        "run_manifests",
        ["workflow_id"],
        schema="evaluation",
    )


def downgrade() -> None:
    op.drop_table("run_manifests", schema="evaluation")
    op.execute("DROP SCHEMA IF EXISTS evaluation")
