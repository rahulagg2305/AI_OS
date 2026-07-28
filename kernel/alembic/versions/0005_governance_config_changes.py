"""Add governance.config_changes: configuration change history.

Revision ID: 0005_governance_config_changes
Revises: 0004_governance_audit_log
Create Date: 2026-07-26

Creates ``governance.config_changes`` per docs/08_database/data_model.md
§9.2. Column-for-column mirror of
:mod:`ai_os_kernel.persistence.governance_schema` — see that module's
docstring for the nullability reasoning (§9.2 marks no column
nullable; ``old_value_digest``/``new_value_digest`` are nullable to
represent a config key's first-ever value / a key's removal) and for
why there is no ``CHECK`` constraint (every column is a plain scalar,
no enum-like column exists here) and no foreign key.

Completes ``governance`` schema §9 in full — this is the second and
last table data_model.md documents for it.

Schema and migration only — no writer. Digests, not values, are
recorded (data_model.md §9.2: "so a secret reference change never
leaks a value"); nothing computes one yet, and no component that would
(Configuration Manager) is built out far enough to.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_governance_config_changes"
down_revision: str | None = "0004_governance_audit_log"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "config_changes",
        sa.Column("change_id", sa.Text, primary_key=True),
        sa.Column("config_key", sa.Text, nullable=False),
        sa.Column("old_value_digest", sa.Text, nullable=True),
        sa.Column("new_value_digest", sa.Text, nullable=True),
        sa.Column("changed_by", sa.Text, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("changed_at", sa.TIMESTAMP(timezone=True), nullable=False),
        schema="governance",
    )
    op.create_index(
        "ix_config_changes_config_key", "config_changes", ["config_key"], schema="governance"
    )
    op.create_index(
        "ix_config_changes_changed_at_desc",
        "config_changes",
        [sa.text("changed_at DESC")],
        schema="governance",
    )


def downgrade() -> None:
    op.drop_table("config_changes", schema="governance")
