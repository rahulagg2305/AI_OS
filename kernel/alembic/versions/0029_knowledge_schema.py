"""Add knowledge.documents, knowledge.chunks, knowledge.embeddings, and
knowledge.memory_items: the Retrieval subsystem's first real increment.

Revision ID: 0029_knowledge_schema
Revises: 0028_catalog_entrypoint
Create Date: 2026-07-27

Creates all four tables docs/08_database/data_model.md §7 documents.
Column-for-column mirror of
:mod:`ai_os_kernel.persistence.knowledge_schema` — see that module's
own docstring for the full reasoning behind every non-obvious decision
recorded below.

Schema and migration only — no reader, no writer, no search logic. No
Retrieval Service, Knowledge Manager, or Memory Manager exists yet to
populate or query any of these tables.

Enables the ``pgvector`` extension (already provisioned in this
platform's own Postgres image since Stage A — ``infra/docker-compose.yml``
uses ``pgvector/pgvector:pg16``, and ``deployment_architecture.md`` §5's
production topology already names "postgres (with pgvector)") — this
activates an already-decided, already-provisioned capability (ADR-0013),
it does not introduce a new one.

``embeddings.embedding`` is an unconstrained ``vector`` column (no fixed
dimension) and the documented HNSW index on it is deliberately NOT
created here — both because §7's own ``vector(N)`` notation names no
concrete ``N`` anywhere in the approved architecture, and choosing one
now would invent an undocumented decision (which embedding model, and
therefore which dimension). The GIN index on ``chunks.content_tsv`` has
no such dependency and is created normally.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR

# revision identifiers, used by Alembic.
revision: str = "0029_knowledge_schema"
down_revision: str | None = "0028_catalog_entrypoint"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TRUST_VALUES = ("trusted", "untrusted")
_MEMORY_TYPES = ("workflow", "engineering", "asset")


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS knowledge")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "documents",
        sa.Column("document_id", sa.Text, primary_key=True),
        sa.Column("source_uri", sa.Text, nullable=False),
        sa.Column("content_hash", sa.Text, nullable=False),
        sa.Column("media_type", sa.Text, nullable=False),
        sa.Column("project_id", sa.Text, nullable=True),
        sa.Column("trust", sa.Text, nullable=False),
        sa.Column("ingested_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("archived_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint(
            "trust IN (" + ", ".join(f"'{t}'" for t in _TRUST_VALUES) + ")",
            name="ck_documents_trust",
        ),
        schema="knowledge",
    )
    op.create_index("ix_documents_project_id", "documents", ["project_id"], schema="knowledge")
    op.create_index("ix_documents_content_hash", "documents", ["content_hash"], schema="knowledge")

    op.create_table(
        "chunks",
        sa.Column("chunk_id", sa.Text, primary_key=True),
        sa.Column(
            "document_id",
            sa.Text,
            sa.ForeignKey("knowledge.documents.document_id"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("token_count", sa.Integer, nullable=False),
        sa.Column("chunk_strategy_version", sa.Text, nullable=False),
        sa.Column(
            "content_tsv",
            TSVECTOR,
            sa.Computed("to_tsvector('english', content)", persisted=True),
            nullable=True,
        ),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.UniqueConstraint("document_id", "ordinal", name="uq_chunks_document_id_ordinal"),
        schema="knowledge",
    )
    op.create_index("ix_chunks_document_id", "chunks", ["document_id"], schema="knowledge")
    op.create_index(
        "ix_chunks_content_tsv",
        "chunks",
        ["content_tsv"],
        schema="knowledge",
        postgresql_using="gin",
    )

    op.create_table(
        "embeddings",
        sa.Column("embedding_id", sa.Text, primary_key=True),
        sa.Column(
            "chunk_id",
            sa.Text,
            sa.ForeignKey("knowledge.chunks.chunk_id"),
            nullable=False,
        ),
        # Unconstrained (no fixed dimension) — see this migration's own
        # docstring and knowledge_schema.py's own docstring for why.
        sa.Column("embedding", Vector(), nullable=False),
        sa.Column("embedding_model_id", sa.Text, nullable=False),
        sa.Column("embedding_model_version", sa.Text, nullable=False),
        sa.Column("dimensions", sa.Integer, nullable=False),
        sa.Column("index_generation", sa.BigInteger, nullable=False),
        schema="knowledge",
    )
    op.create_index("ix_embeddings_chunk_id", "embeddings", ["chunk_id"], schema="knowledge")
    op.create_index(
        "ix_embeddings_model_id_version",
        "embeddings",
        ["embedding_model_id", "dimensions"],
        schema="knowledge",
    )
    # The documented HNSW index on `embeddings.embedding` is deliberately
    # NOT created here — it requires a fixed vector dimension, which
    # requires an embedding-model decision this codebase has not made.
    # Purely additive once that decision is real.

    op.create_table(
        "memory_items",
        sa.Column("memory_id", sa.Text, primary_key=True),
        sa.Column("memory_type", sa.Text, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column(
            "source_workflow_id",
            sa.Text,
            sa.ForeignKey("workflow.workflow_instances.workflow_id"),
            nullable=False,
        ),
        sa.Column("quality_signal", sa.Numeric(14, 6), nullable=True),
        sa.Column("promoted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("provenance", JSONB, nullable=False, server_default="{}"),
        sa.CheckConstraint(
            "memory_type IN (" + ", ".join(f"'{t}'" for t in _MEMORY_TYPES) + ")",
            name="ck_memory_items_memory_type",
        ),
        schema="knowledge",
    )
    op.create_index(
        "ix_memory_items_source_workflow_id",
        "memory_items",
        ["source_workflow_id"],
        schema="knowledge",
    )
    op.create_index(
        "ix_memory_items_memory_type", "memory_items", ["memory_type"], schema="knowledge"
    )


def downgrade() -> None:
    op.drop_table("memory_items", schema="knowledge")
    op.drop_table("embeddings", schema="knowledge")
    op.drop_table("chunks", schema="knowledge")
    op.drop_table("documents", schema="knowledge")
    op.execute("DROP SCHEMA IF EXISTS knowledge")
    op.execute("DROP EXTENSION IF EXISTS vector")
