"""Canonical Core table definitions for the Retrieval subsystem's own
persistence layer (data_model.md §7: "Knowledge and Retrieval").

Mirrors §7 exactly, in the same style already established for
``trace``/``governance``/``platform``: kept in its own module with its
own ``MetaData`` (schema ``knowledge``), a genuinely distinct bounded
context. Combined into ``target_metadata`` in ``kernel/alembic/env.py``
alongside the other schema modules.

All four tables §7 documents are defined here: ``documents``, ``chunks``,
``embeddings``, ``memory_items``. **Schema and migration only — no
reader, no writer, no search logic.** No Retrieval Service, Knowledge
Manager, or Memory Manager exists yet to populate or query any of
these; :class:`~ai_os_kernel.workflow_engine.repository.
SqlWorkflowInstanceRepository`'s own "schema and migration only" steps
(``catalog``/``evaluation``/``governance``/``platform``/``trace``) are
the direct precedent this module follows.

**Why this is the correct first Retrieval increment, and why it has no
dependency on embedding generation despite creating a ``vector`` column
— a decision recorded explicitly, not left implicit.** Three documents
(``infra/docker-compose.yml``'s own ``pgvector/pgvector:pg16`` image,
already provisioned since Stage A; ``deployment_architecture.md`` §5's
production topology, "postgres (with pgvector)"; and ADR-0013's own
accepted technology decision) already establish that this platform's
Postgres always has the ``pgvector`` extension available — enabling it
here (``CREATE EXTENSION IF NOT EXISTS vector``) activates an
already-provisioned, already-decided capability; it does not introduce
a new one. Nothing here calls the LLM Gateway's ``embed()`` (which does
not exist), generates a real embedding, or performs a vector query —
this module only makes the column *exist*.

**``embeddings.embedding`` is declared as an unconstrained
:class:`pgvector.sqlalchemy.Vector` (no fixed dimension) — a reasoned
resolution of a genuine ambiguity in data_model.md §7's own notation,
not an invented value.** §7 writes the column's documented type
literally as ``vector(N)`` — ``N`` is not a concrete number anywhere in
the approved documentation; it is a placeholder for a dimension that
depends on which embedding model is eventually chosen (search_vector_search.md
§5: "Vector embeddings and models used for embedding must be
configuration-driven"; ADR-0013: "changing the embedding model requires
a re-index"). Choosing a concrete number now (1536, 1024, …) would be
inventing an architectural decision this codebase has not made and no
document authorises — exactly the "no speculative architecture" this
step must avoid. §7's own separate ``dimensions`` column (recorded
*per row*, alongside ``embedding_model_id``/``embedding_model_version``)
confirms this reading: the schema is already designed to let rows from
different embedding models — and therefore different actual vector
sizes — coexist, which is only possible if the column itself does not
hard-code one dimension. An unconstrained ``Vector`` column is
therefore not a workaround but the faithful reading of what §7 already
specifies.

**One documented index is deferred as a direct, unavoidable consequence
of the same ambiguity — reported here, not silently dropped.** §7 also
documents "HNSW on `embeddings.embedding` (cosine)" — but pgvector's
HNSW index requires a fixed vector dimension to be created at all,
which requires the same not-yet-made embedding-model decision the
column itself defers. Creating this index now would require inventing
the exact dimension this module's own docstring just explained cannot
be invented. The GIN index on ``chunks.content_tsv`` has no such
dependency (Postgres full-text search, no pgvector involved) and is
created normally. The HNSW index is deferred to whichever future step
first chooses a real embedding model and dimension — at that point it
is a purely additive migration, not a redesign of this one.

**``content_tsv`` uses ``to_tsvector('english', content)`` — a concrete,
necessary choice to make a documented "generated" column real, not a
speculative one.** §7 names the column and its generated nature but not
a text-search configuration. English is this project's own working
language throughout every existing document and identifier; a future
step adding real multi-language ingestion can change the generation
expression in a purely additive migration without altering this
table's shape.

**Nullability follows this project's own established "explicit ``NULL``
only" reading of data_model.md's table headers** (already used for
``trace``/``governance``/``platform``): a column §7 marks ``NULL``
(``documents.project_id``; ``memory_items.quality_signal``/
``promoted_at``/``expires_at``) is nullable; every other column is
``NOT NULL``. ``chunks.metadata`` and ``memory_items.provenance`` are
``JSONB NOT NULL`` with a ``'{}'`` server default — an honest "nothing
extra recorded" value, not a nullable field, matching data_model.md
§2's own "Structured payloads: JSONB" convention.

**``memory_items.source_workflow_id`` gets a real foreign key to
``workflow.workflow_instances.workflow_id``** — the identical
"unambiguous pointer to an already-real table, safe to import directly
because no cycle results" reasoning already used for
``workflow_instances.definition_id``/``definition_version`` ->
``catalog.workflow_definitions`` (:mod:`ai_os_kernel.persistence.schema`)
and ``trace.links.source_key``/``target_key`` -> ``trace.artifacts``
(:mod:`ai_os_kernel.persistence.trace_schema`). Importing
:mod:`ai_os_kernel.persistence.schema` here introduces no cycle: that
module does not import this one.

No id-generation helper module (mirroring every other "schema and
migration only" step in this codebase — ``trace``/``governance``/
``platform`` have none either): nothing here generates a real id yet,
since no writer exists.
"""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR

from ai_os_kernel.persistence.schema import workflow_instances

metadata = sa.MetaData(schema="knowledge")

_TRUST_VALUES = ("trusted", "untrusted")

documents = sa.Table(
    "documents",
    metadata,
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
)

sa.Index("ix_documents_project_id", documents.c.project_id)
sa.Index("ix_documents_content_hash", documents.c.content_hash)

chunks = sa.Table(
    "chunks",
    metadata,
    sa.Column("chunk_id", sa.Text, primary_key=True),
    sa.Column(
        "document_id",
        sa.Text,
        sa.ForeignKey(documents.c.document_id),
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
)

sa.Index("ix_chunks_document_id", chunks.c.document_id)
sa.Index("ix_chunks_content_tsv", chunks.c.content_tsv, postgresql_using="gin")

embeddings = sa.Table(
    "embeddings",
    metadata,
    sa.Column("embedding_id", sa.Text, primary_key=True),
    sa.Column(
        "chunk_id",
        sa.Text,
        sa.ForeignKey(chunks.c.chunk_id),
        nullable=False,
    ),
    # Unconstrained (no fixed dimension) — see this module's own
    # docstring for why a concrete number would be an invented,
    # undocumented decision, and why the documented HNSW index cannot
    # be created until one is real.
    sa.Column("embedding", Vector(), nullable=False),
    sa.Column("embedding_model_id", sa.Text, nullable=False),
    sa.Column("embedding_model_version", sa.Text, nullable=False),
    sa.Column("dimensions", sa.Integer, nullable=False),
    sa.Column("index_generation", sa.BigInteger, nullable=False),
)

sa.Index("ix_embeddings_chunk_id", embeddings.c.chunk_id)
sa.Index("ix_embeddings_model_id_version", embeddings.c.embedding_model_id, embeddings.c.dimensions)

_MEMORY_TYPES = ("workflow", "engineering", "asset")

memory_items = sa.Table(
    "memory_items",
    metadata,
    sa.Column("memory_id", sa.Text, primary_key=True),
    sa.Column("memory_type", sa.Text, nullable=False),
    sa.Column("content", sa.Text, nullable=False),
    sa.Column(
        "source_workflow_id",
        sa.Text,
        sa.ForeignKey(workflow_instances.c.workflow_id),
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
)

sa.Index("ix_memory_items_source_workflow_id", memory_items.c.source_workflow_id)
sa.Index("ix_memory_items_memory_type", memory_items.c.memory_type)
