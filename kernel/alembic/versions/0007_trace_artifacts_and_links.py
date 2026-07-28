"""Add trace.artifacts and trace.links: traceability schema.

Revision ID: 0007_trace_artifacts_and_links
Revises: 0006_platform_outbox_idempotency
Create Date: 2026-07-26

Creates ``trace.artifacts`` and ``trace.links`` per
docs/08_database/data_model.md §8. Column-for-column mirror of
:mod:`ai_os_kernel.persistence.trace_schema` — see that module's
docstring for the reasoning behind which columns get ``CHECK``
constraints, why ``links.source_key``/``target_key`` get foreign keys
(unlike every ``governance``/``platform`` table so far), and the
partial-unique-index implementation of the documented
``UNIQUE (source_key, relationship, target_key) WHERE closed_at IS NULL``
rule.

Schema and migration only — no writer. No Traceability Engine exists
yet to run the recursive-CTE impact analysis §8 describes, and nothing
writes a traceability link yet either.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_trace_artifacts_and_links"
down_revision: str | None = "0006_platform_outbox_idempotency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ARTIFACT_TYPES = (
    "requirement",
    "architecture_element",
    "adr",
    "design_element",
    "module",
    "source_file",
    "test_case",
    "documentation",
    "release",
    "workflow_run",
)

_LINK_RELATIONSHIPS = (
    "implements",
    "verifies",
    "realizes",
    "affects",
    "contains",
    "produced",
    "applies_to",
)

_LINK_CONFIDENCES = (
    "confirmed",
    "inferred",
    "provisional",
)

_LINK_CREATED_BY_TYPES = (
    "agent",
    "user",
    "process",
)


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS trace")

    op.create_table(
        "artifacts",
        sa.Column("artifact_key", sa.Text, primary_key=True),
        sa.Column("artifact_type", sa.Text, nullable=False),
        sa.Column("external_id", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("location", sa.Text, nullable=False),
        sa.Column("version", sa.Text, nullable=False),
        sa.CheckConstraint(
            "artifact_type IN (" + ", ".join(f"'{t}'" for t in _ARTIFACT_TYPES) + ")",
            name="ck_artifacts_artifact_type",
        ),
        schema="trace",
    )
    op.create_index("ix_artifacts_artifact_type", "artifacts", ["artifact_type"], schema="trace")
    op.create_index("ix_artifacts_external_id", "artifacts", ["external_id"], schema="trace")

    op.create_table(
        "links",
        sa.Column("link_id", sa.Text, primary_key=True),
        sa.Column(
            "source_key",
            sa.Text,
            sa.ForeignKey("trace.artifacts.artifact_key"),
            nullable=False,
        ),
        sa.Column("relationship", sa.Text, nullable=False),
        sa.Column(
            "target_key",
            sa.Text,
            sa.ForeignKey("trace.artifacts.artifact_key"),
            nullable=False,
        ),
        sa.Column("confidence", sa.Text, nullable=False),
        sa.Column("created_by", sa.Text, nullable=False),
        sa.Column("created_by_type", sa.Text, nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("closed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint(
            "relationship IN (" + ", ".join(f"'{r}'" for r in _LINK_RELATIONSHIPS) + ")",
            name="ck_links_relationship",
        ),
        sa.CheckConstraint(
            "confidence IN (" + ", ".join(f"'{c}'" for c in _LINK_CONFIDENCES) + ")",
            name="ck_links_confidence",
        ),
        sa.CheckConstraint(
            "created_by_type IN (" + ", ".join(f"'{t}'" for t in _LINK_CREATED_BY_TYPES) + ")",
            name="ck_links_created_by_type",
        ),
        schema="trace",
    )
    op.create_index("ix_links_source_key", "links", ["source_key"], schema="trace")
    op.create_index("ix_links_target_key", "links", ["target_key"], schema="trace")
    op.create_index(
        "uq_links_open_source_relationship_target",
        "links",
        ["source_key", "relationship", "target_key"],
        unique=True,
        schema="trace",
        postgresql_where=sa.text("closed_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("links", schema="trace")
    op.drop_table("artifacts", schema="trace")
    op.execute("DROP SCHEMA IF EXISTS trace")
