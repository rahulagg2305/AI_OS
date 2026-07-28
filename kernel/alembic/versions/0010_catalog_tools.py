"""Add catalog.tools.

Revision ID: 0010_catalog_tools
Revises: 0009_catalog_prompts
Create Date: 2026-07-26

Creates ``catalog.tools`` per docs/08_database/data_model.md §5 — one
more of `catalog`'s six documented tables (`packs`,
`pack_state_transitions`, `agents` remain undocumented-scope for this
step; the first two additionally state no primary key in §5 at all).
Column-for-column mirror of :mod:`ai_os_kernel.persistence.catalog_schema`
— see that module's docstring for the full reasoning.

``trust_tier`` gets a ``CHECK`` constraint grounded in the exact two
values ``ai_os_kernel.workflow_engine.tool.TrustTier`` already declares
(``tier1_sandboxed``, ``tier2_trusted``). The values are duplicated as
literals here rather than importing ``TrustTier``: this migration must
remain a frozen historical record of what it enforced at the time it
ran, and the ``persistence`` layer does not import from
``workflow_engine`` in the first place (that dependency already runs
the other way) — the identical reasoning already applied to
``workflow_steps.step_type``'s ``_STEP_TYPES`` in
``0002_workflow_steps.py``.

Schema and migration only — no writer. Nothing in this codebase
persists a pack or a tool yet; tool *execution* is unaffected — this
only adds a database table describing tools.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0010_catalog_tools"
down_revision: str | None = "0009_catalog_prompts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TOOL_TRUST_TIERS = (
    "tier1_sandboxed",
    "tier2_trusted",
)


def upgrade() -> None:
    op.create_table(
        "tools",
        sa.Column("tool_id", sa.Text, primary_key=True),
        sa.Column("pack_id", sa.Text, nullable=False),
        sa.Column("version", sa.Text, nullable=False),
        sa.Column("trust_tier", sa.Text, nullable=False),
        sa.Column("input_schema", JSONB, nullable=False),
        sa.Column("output_schema", JSONB, nullable=False),
        sa.Column("required_permissions", JSONB, nullable=False),
        sa.CheckConstraint(
            "trust_tier IN (" + ", ".join(f"'{t}'" for t in _TOOL_TRUST_TIERS) + ")",
            name="ck_tools_trust_tier",
        ),
        schema="catalog",
    )
    op.create_index("ix_tools_pack_id", "tools", ["pack_id"], schema="catalog")


def downgrade() -> None:
    op.drop_table("tools", schema="catalog")
