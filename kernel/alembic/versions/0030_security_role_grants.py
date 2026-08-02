"""Add security.role_grants: real, persisted role administration
(grant/revoke) for a principal.

Revision ID: 0030_security_role_grants
Revises: 0029_knowledge_schema
Create Date: 2026-08-03

Column-for-column mirror of :mod:`ai_os_kernel.security_manager.schema`
— see that module's own docstring, and
docs/08_database/data_model.md §9a, for the full reasoning.

Closes a real, previously-disclosed gap named repeatedly across the
Human Approval work (P03-S05-M14-T04 through T06): every role has come
solely from a bearer token's own `roles` claim; there was no persisted
state to grant/revoke one against.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0030_security_role_grants"
down_revision: str | None = "0029_knowledge_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ROLE_GRANT_STATUSES = ("active", "revoked")


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS security")

    op.create_table(
        "role_grants",
        sa.Column("grant_id", sa.Text, primary_key=True),
        sa.Column("principal_id", sa.Text, nullable=False),
        sa.Column("role", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("granted_by", sa.Text, nullable=False),
        sa.Column("granted_reason", sa.Text, nullable=False),
        sa.Column("granted_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("revoked_by", sa.Text, nullable=True),
        sa.Column("revoked_reason", sa.Text, nullable=True),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in _ROLE_GRANT_STATUSES) + ")",
            name="ck_role_grants_status",
        ),
        schema="security",
    )
    op.create_index(
        "ix_role_grants_principal_id", "role_grants", ["principal_id"], schema="security"
    )
    op.create_index(
        "uq_role_grants_active_principal_role",
        "role_grants",
        ["principal_id", "role"],
        unique=True,
        schema="security",
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_table("role_grants", schema="security")
    op.execute("DROP SCHEMA IF EXISTS security")
