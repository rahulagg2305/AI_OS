"""Add catalog.packs.

Revision ID: 0018_catalog_packs
Revises: 0017_evaluation_gate_results
Create Date: 2026-07-26

Creates ``catalog.packs`` per docs/08_database/data_model.md §5 — the
fifth of the six `catalog` tables (`workflow_definitions`, `prompts`,
`tools`, `agents` came first). `pack_state_transitions` remains
undocumented-scope for this step: it still has no documented primary
key, a distinct, still-open documentation gap not resolved by the
`packs` decision this migration implements. Column-for-column mirror of
:mod:`ai_os_kernel.persistence.catalog_schema` — see that module's
docstring for the full reasoning, including why `installed_at`,
`activated_at`, and `health` are nullable while every other column is
not.

`state` gets a `CHECK` constraint against the eight-value canonical
lifecycle `capability_manager.md` §4 defines as its single authority.

This migration does not retrofit `workflow_definitions`/`prompts`/
`tools`/`agents`' own `pack_id` columns into real foreign keys against
`packs.pack_id` — out of scope for this step ("no other catalog table
changes"), a distinct, later step.

Schema and migration only — no writer. `ManifestLoader` reads and
validates a manifest file; it does not persist one, so nothing
populates this table yet.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0018_catalog_packs"
down_revision: str | None = "0017_evaluation_gate_results"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PACK_STATES = (
    "discovered",
    "validated",
    "installed",
    "configured",
    "activated",
    "deactivated",
    "failed",
    "uninstalled",
)


def upgrade() -> None:
    op.create_table(
        "packs",
        sa.Column("pack_id", sa.Text, primary_key=True),
        sa.Column("version", sa.Text, nullable=False),
        sa.Column("state", sa.Text, nullable=False),
        sa.Column("manifest", JSONB, nullable=False),
        sa.Column("sdk_version", sa.Text, nullable=False),
        sa.Column("min_kernel_version", sa.Text, nullable=False),
        sa.Column("installed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("activated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("health", JSONB, nullable=True),
        sa.CheckConstraint(
            "state IN (" + ", ".join(f"'{s}'" for s in _PACK_STATES) + ")",
            name="ck_packs_state",
        ),
        schema="catalog",
    )
    op.create_index(
        "ix_packs_state",
        "packs",
        ["state"],
        schema="catalog",
    )


def downgrade() -> None:
    op.drop_table("packs", schema="catalog")
