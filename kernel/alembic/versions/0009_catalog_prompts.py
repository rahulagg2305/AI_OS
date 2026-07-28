"""Add catalog.prompts.

Revision ID: 0009_catalog_prompts
Revises: 0008_catalog_wf_definitions
Create Date: 2026-07-26

Creates ``catalog.prompts`` per docs/08_database/data_model.md §5 — one
more of `catalog`'s six documented tables (`packs`,
`pack_state_transitions`, `agents`, `tools` remain undocumented-scope
for this step). Column-for-column mirror of
:mod:`ai_os_kernel.persistence.catalog_schema` — see that module's
docstring for the nullability reasoning, why `content` is typed
`sa.Text` rather than `JSONB` (a prompt's content is a raw Markdown
template file, per `prompt_engine.md` §12, not a structured document),
and why there is no foreign key on `pack_id` (`catalog.packs` does not
exist yet).

Schema and migration only — no writer. Nothing in this codebase
persists a pack or a prompt yet.

This step does not touch `catalog.workflow_definitions`, its own open
`definition_id` versioning question, or the still-deferred foreign key
retrofit from `workflow_instances`/`workflow_events`.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0009_catalog_prompts"
down_revision: str | None = "0008_catalog_wf_definitions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prompts",
        sa.Column("prompt_id", sa.Text, primary_key=True),
        sa.Column("pack_id", sa.Text, nullable=False),
        sa.Column("version", sa.Text, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("input_schema", JSONB, nullable=False),
        sa.Column("content_hash", sa.Text, nullable=False),
        schema="catalog",
    )
    op.create_index("ix_prompts_pack_id", "prompts", ["pack_id"], schema="catalog")


def downgrade() -> None:
    op.drop_table("prompts", schema="catalog")
