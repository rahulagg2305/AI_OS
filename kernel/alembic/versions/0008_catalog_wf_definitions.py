"""Add catalog.workflow_definitions.

Revision ID: 0008_catalog_wf_definitions
Revises: 0007_trace_artifacts_and_links
Create Date: 2026-07-26

Creates ``catalog.workflow_definitions`` per docs/08_database/data_model.md
§5 — one table only, not the full ``catalog`` schema (``packs``,
``pack_state_transitions``, ``agents``, ``tools``, ``prompts`` remain
undocumented-scope for this step). Column-for-column mirror of
:mod:`ai_os_kernel.persistence.catalog_schema` — see that module's
docstring for the nullability reasoning, why ``inputs_schema``/
``outputs_schema``/``declared_permissions`` are typed ``JSONB`` even
though only ``graph`` is explicitly marked so in §5, and why there is
no foreign key on ``pack_id`` (``catalog.packs`` does not exist yet).

This table is the one ``persistence/schema.py`` has deferred a foreign
key to (from ``workflow_instances``/``workflow_events``) since the very
first migration. Adding it here unblocks that retrofit as a distinct,
later step — this migration does not perform the retrofit itself and
does not touch any ``workflow`` schema table.

Schema and migration only — no writer. Nothing in this codebase
persists a pack yet (``ManifestLoader`` reads and validates a manifest
file; it does not write one to the database).

Revision id kept to 32 characters or fewer, per the lesson learned in
``0006_platform_outbox_idempotency``: Alembic's own
``alembic_version.version_num`` column defaults to ``VARCHAR(32)``.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0008_catalog_wf_definitions"
down_revision: str | None = "0007_trace_artifacts_and_links"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS catalog")

    op.create_table(
        "workflow_definitions",
        sa.Column("definition_id", sa.Text, primary_key=True),
        sa.Column("pack_id", sa.Text, nullable=False),
        sa.Column("version", sa.Text, nullable=False),
        sa.Column("graph", JSONB, nullable=False),
        sa.Column("inputs_schema", JSONB, nullable=False),
        sa.Column("outputs_schema", JSONB, nullable=False),
        sa.Column("declared_permissions", JSONB, nullable=False),
        sa.Column("validated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        schema="catalog",
    )
    op.create_index(
        "ix_workflow_definitions_pack_id",
        "workflow_definitions",
        ["pack_id"],
        schema="catalog",
    )


def downgrade() -> None:
    op.drop_table("workflow_definitions", schema="catalog")
    op.execute("DROP SCHEMA IF EXISTS catalog")
