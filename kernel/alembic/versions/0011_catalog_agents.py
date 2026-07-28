"""Add catalog.agents.

Revision ID: 0011_catalog_agents
Revises: 0010_catalog_tools
Create Date: 2026-07-26

Creates ``catalog.agents`` per docs/08_database/data_model.md §5 — the
last cleanly-specified table `catalog` documents that did not already
exist. `packs`/`pack_state_transitions` remain out of scope: §5 states
no primary key at all for either, which needs resolving (a
documentation decision) before either can be added without inventing
one. Column-for-column mirror of
:mod:`ai_os_kernel.persistence.catalog_schema` — see that module's
docstring for the full reasoning, including why the in-process
``Agent`` Protocol's own lack of an ``input_schema`` (a runtime-contract
deferral) does not affect this table's documented ``input_schema``
column.

Schema and migration only — no writer. Nothing in this codebase
persists a pack or an agent yet; agent *invocation* is unaffected —
this only adds a database table describing agents.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0011_catalog_agents"
down_revision: str | None = "0010_catalog_tools"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("agent_id", sa.Text, primary_key=True),
        sa.Column("pack_id", sa.Text, nullable=False),
        sa.Column("version", sa.Text, nullable=False),
        sa.Column("input_schema", JSONB, nullable=False),
        sa.Column("output_schema", JSONB, nullable=False),
        sa.Column("required_permissions", JSONB, nullable=False),
        sa.Column("required_tools", JSONB, nullable=False),
        schema="catalog",
    )
    op.create_index("ix_agents_pack_id", "agents", ["pack_id"], schema="catalog")


def downgrade() -> None:
    op.drop_table("agents", schema="catalog")
