"""Minimal write path for ``knowledge.documents`` and ``knowledge.chunks``
(data_model.md §7) — the smallest real seam that lets a future Indexing
Pipeline (search_vector_search.md: "Indexing Pipeline — deterministic,
versioned chunk_strategy_version") persist a document it has already
fetched and chunked.

**Deliberately not a Knowledge Manager, and not placed inside the
``knowledge_manager`` package.** knowledge_manager.md documents the
Knowledge Manager as the owner of retrieval-facing access to this data;
that package (:mod:`ai_os_kernel.knowledge_manager`) is an intentionally
untouched stub (this step's own approved framing: "No Knowledge Manager
... integration yet"). This module is a bare persistence boundary —
exactly the same "own schema, own writer module, no owning domain
component built yet" shape already established for
:mod:`ai_os_kernel.workflow_engine.definition_catalog` (registers into
``catalog.workflow_definitions`` without being a Capability Manager) and
:mod:`ai_os_kernel.llm_gateway.call_recorder` (writes ``evaluation.
llm_calls`` without being an Observability platform). It lives beside
:mod:`ai_os_kernel.persistence.knowledge_schema` rather than inside a
component package for the same reason that module gives no writer of
its own a home: no owning component (Knowledge Manager, or an Indexing
Pipeline) exists yet to claim it.

**Accepts already-chunked input; performs no chunking, hashing, or
fetching of its own.** ``content_hash`` and every chunk's ``content``/
``token_count``/``chunk_strategy_version`` are supplied by the caller,
not computed here — computing a document hash from a fetched resource,
or splitting raw content into chunks, is Indexing Pipeline territory
(search_vector_search.md's own "Indexing Pipeline" component, still
unbuilt), out of scope for "no ingestion pipeline" this step's own
fence draws. This module only persists what it is given.

**``ordinal`` is derived from the supplied chunks' list position, not a
caller-supplied field.** ``chunks: Sequence[ChunkInput]`` is already an
ordered sequence — the caller's own chunking already fixed the order — so
re-deriving ``ordinal`` via ``enumerate()`` is the least-invented reading
that also makes the ``uq_chunks_document_id_ordinal`` constraint
trivially satisfiable within one write, rather than asking the caller to
track and supply a value this module can already compute for free.

**One transaction spans both tables, mirroring every other
snapshot(-plus-children) writer in this codebase**
(``workflow_instances``+``workflow_events``,
``catalog.packs``+``catalog.pack_state_transitions``): a document with
zero persisted chunks, or chunks with no parent document, should never
be observable. An empty ``chunks`` sequence is rejected before opening a
transaction at all — a document with no content is not a meaningful
increment to this schema, and data_model.md §7 gives no indication a
zero-chunk document is a legitimate case to support silently.

**``document_id``/``chunk_id`` are generated here, not caller-supplied**
— the identical "the writer mints a fresh identity for what it creates"
shape :meth:`~ai_os_kernel.workflow_engine.repository.
SqlWorkflowInstanceRepository.create` already uses for ``workflow_id``,
as opposed to a caller-supplied natural key like
``catalog.workflow_definitions.definition_id``. A document being ingested
has no natural stable identity to key on (unlike a workflow definition's
own declared ``id``), so each call always creates a brand-new row; this
is intentionally **not** an idempotent upsert. Deduplicating by
``content_hash`` (re-ingesting identical content twice) is a policy
decision left to whichever future Indexing Pipeline step calls this
writer, not decided here.

**No ``.returning()`` on either insert.** Every column value this writer
writes is already fully known to it before the ``INSERT`` runs (no
column here has a meaningful server-computed value except
``chunks.content_tsv``, a generated column deliberately excluded from
:class:`ChunkRecord` — see :mod:`ai_os_kernel.persistence.knowledge_schema`'s
own docstring for why that column, and its HNSW-dependent embeddings
sibling, are out of scope entirely). Reading a row back immediately
after writing it would be redundant, the same reasoning already applied
by :class:`~ai_os_kernel.workflow_engine.definition_catalog.
SqlWorkflowDefinitionCatalog`/:class:`~ai_os_kernel.llm_gateway.
call_recorder.SqlLLMCallRecorder` (neither uses ``.returning()`` either).

No reader, no update, no delete, no search — "prove the writer with
appropriate tests," per this step's own scope, does not require a
read-back API of its own; integration tests query the real table
directly instead, the identical pattern already used to verify
:mod:`ai_os_kernel.workflow_engine.definition_catalog`.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.persistence.knowledge_ids import new_chunk_id, new_document_id
from ai_os_kernel.persistence.knowledge_schema import chunks as chunks_table
from ai_os_kernel.persistence.knowledge_schema import documents as documents_table


class KnowledgeWriteError(Exception):
    """A document (with its chunks) could not be written to
    ``knowledge.documents``/``knowledge.chunks``.

    Raised for both invalid input (e.g. an empty chunk sequence) and a
    wrapped persistence-layer failure — never a bare stack trace. The
    underlying exception, when there is one, is chained via ``from``.
    """


class ChunkInput(BaseModel):
    """One already-produced chunk of a document's content, as supplied
    by the caller — the reduced input shape this writer accepts (no
    chunking logic of its own, see this module's own docstring)."""

    model_config = ConfigDict(frozen=True)

    content: str
    token_count: int = Field(gt=0)
    chunk_strategy_version: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChunkRecord(BaseModel):
    """One ``knowledge.chunks`` row, as written by :meth:`KnowledgeWriter.
    write_document`. ``content_tsv`` is deliberately absent — a
    Postgres-generated column with no meaningful in-Python value to
    return (see this module's own docstring)."""

    model_config = ConfigDict(frozen=True)

    chunk_id: str
    document_id: str
    ordinal: int
    content: str
    token_count: int
    chunk_strategy_version: str
    metadata: dict[str, Any]


class DocumentRecord(BaseModel):
    """One ``knowledge.documents`` row, plus the ``knowledge.chunks``
    rows written alongside it in the same call — the full result of one
    :meth:`KnowledgeWriter.write_document` invocation."""

    model_config = ConfigDict(frozen=True)

    document_id: str
    source_uri: str
    content_hash: str
    media_type: str
    project_id: str | None
    trust: Literal["trusted", "untrusted"]
    ingested_at: datetime
    archived_at: datetime | None
    chunks: list[ChunkRecord]


class KnowledgeWriter(Protocol):
    """Persistence boundary for writing one document and its chunks —
    the seam a fake implementation substitutes in unit tests (ADR-0004:
    interface-driven, configuration over code)."""

    async def write_document(
        self,
        *,
        source_uri: str,
        content_hash: str,
        media_type: str,
        trust: Literal["trusted", "untrusted"],
        chunks: Sequence[ChunkInput],
        project_id: str | None = None,
    ) -> DocumentRecord: ...


class SqlKnowledgeWriter:
    """The only implementation of :class:`KnowledgeWriter` at this
    stage: SQLAlchemy 2.0 Core against Postgres (ADR-0011)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def write_document(
        self,
        *,
        source_uri: str,
        content_hash: str,
        media_type: str,
        trust: Literal["trusted", "untrusted"],
        chunks: Sequence[ChunkInput],
        project_id: str | None = None,
    ) -> DocumentRecord:
        if not source_uri or not source_uri.strip():
            raise KnowledgeWriteError("source_uri must not be blank")
        if not content_hash or not content_hash.strip():
            raise KnowledgeWriteError("content_hash must not be blank")
        if not media_type or not media_type.strip():
            raise KnowledgeWriteError("media_type must not be blank")
        if not chunks:
            raise KnowledgeWriteError(
                "chunks must not be empty: a document with no chunks is not a "
                "meaningful knowledge.documents/knowledge.chunks write"
            )

        document_id = new_document_id()
        ingested_at = datetime.now(UTC)
        chunk_records = [
            ChunkRecord(
                chunk_id=new_chunk_id(),
                document_id=document_id,
                ordinal=ordinal,
                content=chunk.content,
                token_count=chunk.token_count,
                chunk_strategy_version=chunk.chunk_strategy_version,
                metadata=chunk.metadata,
            )
            for ordinal, chunk in enumerate(chunks)
        ]

        try:
            async with self._engine.begin() as connection:
                await connection.execute(
                    sa.insert(documents_table).values(
                        document_id=document_id,
                        source_uri=source_uri,
                        content_hash=content_hash,
                        media_type=media_type,
                        project_id=project_id,
                        trust=trust,
                        ingested_at=ingested_at,
                        archived_at=None,
                    )
                )
                await connection.execute(
                    sa.insert(chunks_table),
                    [
                        {
                            "chunk_id": record.chunk_id,
                            "document_id": record.document_id,
                            "ordinal": record.ordinal,
                            "content": record.content,
                            "token_count": record.token_count,
                            "chunk_strategy_version": record.chunk_strategy_version,
                            "metadata": record.metadata,
                        }
                        for record in chunk_records
                    ],
                )
        except sa.exc.SQLAlchemyError as exc:
            raise KnowledgeWriteError(
                f"failed to write document '{source_uri}' and its {len(chunks)} chunk(s): {exc}"
            ) from exc

        return DocumentRecord(
            document_id=document_id,
            source_uri=source_uri,
            content_hash=content_hash,
            media_type=media_type,
            project_id=project_id,
            trust=trust,
            ingested_at=ingested_at,
            archived_at=None,
            chunks=chunk_records,
        )
