"""The real Indexing component (``P02-S04-M09-T03``) —
search_vector_search.md's own "Indexing Pipeline" box, in its smallest
real form: turn real source content into real, chunked
``knowledge.documents``/``knowledge.chunks`` rows through the already-
real :class:`~ai_os_kernel.persistence.knowledge_writer.
SqlKnowledgeWriter` (``P02-S04-M09-T01``) — no parallel write path.

**The first real code in this package.** ``knowledge_manager/
__init__.py`` was a docstring-only stub before this step; the writer,
keyword searcher, vector searcher, fusion, and Retrieval Service all
live one layer down in :mod:`ai_os_kernel.persistence`/
:mod:`ai_os_kernel.retrieval` per their own tickets' ``module_path``.
This ticket's own ``module_path`` is ``knowledge_manager`` — the first
component that genuinely belongs here.

**Two decisions this step's own writer explicitly left open — both
resolved by explicit product-owner choice, not invented unilaterally:**

1. **Chunking strategy: fixed-size character windows with overlap**
   (:data:`CHUNK_STRATEGY_VERSION` = ``"fixed-size-v1"``, the identical
   id already used as a placeholder in prior tests, now made real).
   Deterministic and versioned (ADR-0013's own "no tuning parameter"
   framing applies here too — a fixed size needs no per-corpus
   retuning), and media-type-agnostic: no structural parser exists for
   any of the ``media_type`` values this schema documents, so a
   structure-aware strategy would only really work for one of them.
   :data:`_CHUNK_SIZE_CHARS`/:data:`_CHUNK_OVERLAP_CHARS` are named,
   disclosed constants (no doc fixes an exact number) rather than
   invented magic literals inline; both are also constructor
   parameters, never hardcoded into the algorithm itself.

2. **Change handling: archive-and-replace by content hash.**
   :meth:`IndexingService.index_document` looks up the most recent
   non-archived ``knowledge.documents`` row for the same
   ``source_uri``. Identical ``content_hash`` — a genuine no-op,
   ``IndexResult.skipped=True``, nothing written. Different hash (or no
   prior row) — the old row's own ``archived_at`` (already in the
   schema, previously unused by any writer) is set, then a fresh
   document+chunks is written through the real, unchanged
   :class:`SqlKnowledgeWriter`. **Disclosed limitation, not hidden:**
   neither :class:`~ai_os_kernel.persistence.knowledge_keyword_search.
   SqlKeywordSearcher` nor :class:`~ai_os_kernel.retrieval.
   vector_search.SqlVectorSearcher` filters on ``archived_at`` yet, so
   a superseded chunk can still surface in a real search result until
   a later step teaches those two real, already-tested modules to
   exclude it — deliberately not touched by this step, per "reuse the
   real searchers, no parallel mechanism."

**``content_hash`` is computed here, not supplied by a caller** — the
identical real ``hashlib.sha256(...).hexdigest()``, ``f"sha256:{digest}"``
formatting :class:`~ai_os_kernel.storage_service.local_store.
LocalFilesystemArtifactStore` already establishes for content-addressed
storage. ``SqlKnowledgeWriter``'s own docstring explicitly assigns this
computation to "whichever future Indexing Pipeline step calls this
writer" — this one.

**``token_count`` is a disclosed, local approximation (~4 characters
per token), not a real call to the provider token-counting endpoint**
(:meth:`~ai_os_kernel.llm_gateway.adapters.anthropic.AnthropicAdapter.
count_tokens`, ``P02-S02-M06-T10``). That real endpoint exists for
LLM-bound prompt/response accounting; round-tripping every indexed
chunk through a live provider call for a bookkeeping field neither
searcher reads or ranks on would be real network cost for no real
retrieval benefit — a deliberate, disclosed scope boundary, not an
oversight.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Literal

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.persistence.knowledge_schema import documents as documents_table
from ai_os_kernel.persistence.knowledge_writer import ChunkInput, DocumentRecord, KnowledgeWriter

# Fixed, versioned chunking strategy id (data_model.md §7's own
# "chunk_strategy_version stored per chunk" requirement) -- see this
# module's own docstring for why fixed-size-with-overlap was chosen.
CHUNK_STRATEGY_VERSION = "fixed-size-v1"

# Named, disclosed defaults -- no document fixes an exact number;
# always overridable per IndexingService instance, never baked into
# the chunking algorithm itself.
_CHUNK_SIZE_CHARS = 2000
_CHUNK_OVERLAP_CHARS = 200

# A common, disclosed characters-per-token approximation -- see this
# module's own docstring for why this is a local estimate, not a real
# provider token-counting call.
_APPROX_CHARS_PER_TOKEN = 4


class IndexingError(Exception):
    """Content could not be chunked or indexed.

    Raised for invalid input (blank content, a non-positive chunk size,
    an overlap that is not strictly smaller than the chunk size) and
    for a wrapped persistence-layer failure -- never a bare stack
    trace. The underlying exception, when there is one, is chained via
    ``from``.
    """


class IndexResult(BaseModel):
    """The outcome of one :meth:`IndexingService.index_document` call."""

    model_config = ConfigDict(frozen=True)

    document: DocumentRecord | None
    skipped: bool
    superseded_document_id: str | None


def chunk_content(
    content: str,
    *,
    chunk_size: int = _CHUNK_SIZE_CHARS,
    overlap: int = _CHUNK_OVERLAP_CHARS,
) -> list[ChunkInput]:
    """Splits ``content`` into deterministic, fixed-size, overlapping
    windows -- the real chunking algorithm this step adds. Always
    produces at least one chunk for non-blank content; the last window
    is truncated to whatever remains rather than padded."""
    if not content or not content.strip():
        raise IndexingError("content must not be blank")
    if chunk_size <= 0:
        raise IndexingError(f"chunk_size must be positive, got {chunk_size}")
    if overlap < 0 or overlap >= chunk_size:
        raise IndexingError(f"overlap must be in [0, chunk_size), got {overlap}")

    step = chunk_size - overlap
    length = len(content)
    windows: list[ChunkInput] = []
    start = 0
    while start < length:
        end = min(start + chunk_size, length)
        text = content[start:end]
        windows.append(
            ChunkInput(
                content=text,
                token_count=max(1, len(text) // _APPROX_CHARS_PER_TOKEN),
                chunk_strategy_version=CHUNK_STRATEGY_VERSION,
            )
        )
        if end >= length:
            break
        start += step
    return windows


class IndexingService:
    """Composes the real chunking algorithm above with the real
    :class:`KnowledgeWriter`, plus the archive-and-replace change
    policy this step adds — the "maintain the retrievable index as
    content changes" half of the ticket's own Goal."""

    def __init__(
        self,
        *,
        engine: AsyncEngine,
        writer: KnowledgeWriter,
        chunk_size: int = _CHUNK_SIZE_CHARS,
        chunk_overlap: int = _CHUNK_OVERLAP_CHARS,
    ) -> None:
        self._engine = engine
        self._writer = writer
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    async def index_document(
        self,
        *,
        source_uri: str,
        content: str,
        media_type: str,
        trust: Literal["trusted", "untrusted"],
        project_id: str | None = None,
    ) -> IndexResult:
        if not source_uri or not source_uri.strip():
            raise IndexingError("source_uri must not be blank")

        content_hash = f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"

        try:
            async with self._engine.connect() as connection:
                existing = (
                    (
                        await connection.execute(
                            sa.select(documents_table.c.document_id, documents_table.c.content_hash)
                            .where(documents_table.c.source_uri == source_uri)
                            .where(documents_table.c.archived_at.is_(None))
                            .order_by(documents_table.c.ingested_at.desc())
                            .limit(1)
                        )
                    )
                    .mappings()
                    .first()
                )
        except sa.exc.SQLAlchemyError as exc:
            raise IndexingError(
                f"failed to look up existing document for '{source_uri}': {exc}"
            ) from exc

        if existing is not None and existing["content_hash"] == content_hash:
            return IndexResult(document=None, skipped=True, superseded_document_id=None)

        superseded_document_id: str | None = None
        if existing is not None:
            superseded_document_id = existing["document_id"]
            try:
                async with self._engine.begin() as connection:
                    await connection.execute(
                        sa.update(documents_table)
                        .where(documents_table.c.document_id == superseded_document_id)
                        .values(archived_at=datetime.now(UTC))
                    )
            except sa.exc.SQLAlchemyError as exc:
                raise IndexingError(
                    f"failed to archive superseded document '{superseded_document_id}': {exc}"
                ) from exc

        chunks = chunk_content(content, chunk_size=self._chunk_size, overlap=self._chunk_overlap)
        document = await self._writer.write_document(
            source_uri=source_uri,
            content_hash=content_hash,
            media_type=media_type,
            trust=trust,
            chunks=chunks,
            project_id=project_id,
        )
        return IndexResult(
            document=document, skipped=False, superseded_document_id=superseded_document_id
        )
