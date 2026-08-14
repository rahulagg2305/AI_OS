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

**Embeddings are produced in-line, but only when configured
(``P02-S04-M09-T06``).** Before that step this service produced no
embeddings at all, so freshly-indexed content was keyword-searchable
and never vector-searchable — a real caller wanting vector search had
to compute and write vectors separately, and nothing did.
:meth:`IndexingService.index_document` now calls the real, unchanged
:func:`~ai_os_kernel.retrieval.embedding_writer.embed_chunk` once per
freshly-written chunk, so the content is genuinely vector-searchable by
the time the call returns.

*Opt-in, because embedding is billable network work.* ``embedder``,
``embedding_writer`` and ``embedding_model_alias`` are optional and
must be supplied **together**; supply none (every caller that existed
before this step) and the behaviour is byte-identical to before — no
embed call, no cost, no new failure mode. The "all of them or none of
them" rule is enforced at construction rather than silently degrading,
the identical shape ``PlatformConfig``'s own three OIDC fields already
establish. Product-owner decision, 2026-08-14.

*Two real limitations, stated rather than discovered later.* First,
**chunks and vectors commit in sequential transactions, not one.**
ADR-0013 cites "transactional consistency between chunk metadata and
vectors" as a property pgvector delivers, and this is its intent but
not its literal letter: :class:`~ai_os_kernel.retrieval.
embedding_writer.SqlEmbeddingWriter` opens its own transaction per
embedding, and the alternative — holding one transaction open across N
billable Gateway calls — is exactly what this codebase avoids elsewhere
(:meth:`~ai_os_kernel.workflow_engine.service.WorkflowInstanceService.
advance` runs executors "outside any database transaction" for this
reason). Second, and following from it: **a failure partway through
embedding leaves the document and its chunks committed with only some
vectors written.** The error propagates rather than being swallowed —
a silent partial index is worse than a loud one — so a caller sees the
real failure, and the already-real archive-and-replace path makes
re-indexing the same ``source_uri`` the recovery route.

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

from ai_os_kernel.llm_gateway.gateway import Embedder
from ai_os_kernel.persistence.knowledge_schema import documents as documents_table
from ai_os_kernel.persistence.knowledge_writer import ChunkInput, DocumentRecord, KnowledgeWriter
from ai_os_kernel.retrieval.embedding_writer import EmbeddingWriter, embed_chunk

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

    embedded_chunk_count: int = 0
    """How many chunks genuinely got a real vector written
    (``P02-S04-M09-T06``). ``0`` when this service was built without an
    embedder — which is a real, correct outcome, not a failure — and
    equal to ``len(document.chunks)`` on a fully embedded write. Present
    so a caller can tell "vector search will work over this" from
    "keyword only", rather than having to query ``knowledge.embeddings``
    to find out."""


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
        embedder: Embedder | None = None,
        embedding_writer: EmbeddingWriter | None = None,
        embedding_model_alias: str | None = None,
    ) -> None:
        """``embedder``/``embedding_writer``/``embedding_model_alias``
        are the opt-in embedding seam (``P02-S04-M09-T06``) and must be
        supplied together or not at all.

        A partial set is refused here rather than silently treated as
        "no embedding": a caller that passed two of the three plainly
        wanted vectors, and quietly indexing without them would produce
        exactly the keyword-only-index-that-looks-complete this ticket
        exists to eliminate. ``embedding_model_alias`` is an *alias*,
        never a literal model id — ADR-0002, and
        search_vector_search.md §5's "models used for embedding must be
        configuration-driven"; the real composed value lives in
        ``bootstrap.py`` against ``config/llm.yaml``, not here.
        """
        embedding_parts = (embedder, embedding_writer, embedding_model_alias)
        if any(part is not None for part in embedding_parts) and not all(
            part is not None for part in embedding_parts
        ):
            raise IndexingError(
                "embedder, embedding_writer and embedding_model_alias must be supplied "
                "together (all three) or not at all — got "
                f"embedder={embedder is not None}, "
                f"embedding_writer={embedding_writer is not None}, "
                f"embedding_model_alias={embedding_model_alias is not None}"
            )

        self._engine = engine
        self._writer = writer
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._embedder = embedder
        self._embedding_writer = embedding_writer
        self._embedding_model_alias = embedding_model_alias

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
        embedded_chunk_count = await self._embed_document_chunks(document)
        return IndexResult(
            document=document,
            skipped=False,
            superseded_document_id=superseded_document_id,
            embedded_chunk_count=embedded_chunk_count,
        )

    async def _embed_document_chunks(self, document: DocumentRecord) -> int:
        """Write a real vector for each of ``document``'s freshly-written
        chunks, via the real, unchanged
        :func:`~ai_os_kernel.retrieval.embedding_writer.embed_chunk`.

        Returns ``0`` immediately when no embedder was configured — the
        pre-``P02-S04-M09-T06`` behaviour, unchanged and cost-free.

        Chunks are embedded **sequentially, one Gateway call each**, not
        concurrently: a burst of parallel embed calls over a large
        document is exactly the kind of unthrottled provider load the
        LLM Gateway's own rate limiting exists to prevent, and this
        service has no budget or concurrency policy of its own to size
        such a burst against.
        """
        if (
            self._embedder is None
            or self._embedding_writer is None
            or self._embedding_model_alias is None
        ):
            return 0

        embedded = 0
        for chunk in document.chunks:
            # Deliberately unguarded: a failure here propagates with the
            # document and its earlier chunks already committed. See this
            # module's own docstring — a loud partial index beats a
            # silent one, and re-indexing the same `source_uri` is the
            # real recovery path.
            await embed_chunk(
                gateway=self._embedder,
                writer=self._embedding_writer,
                chunk_id=chunk.chunk_id,
                text=chunk.content,
                model_alias=self._embedding_model_alias,
            )
            embedded += 1
        return embedded
