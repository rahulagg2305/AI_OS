"""Write path for ``knowledge.embeddings`` (data_model.md §7,
``P02-S04-M11-T03``) — the smallest real seam that persists a genuine
:class:`~ai_os_kernel.llm_gateway.models.EmbeddingResponse` (the real
``embed()`` built at ``P02-S02-M06-T09``) against an already-real
``knowledge.chunks`` row.

**Deliberately not placed inside the ``knowledge_manager`` package**,
the identical reasoning :mod:`ai_os_kernel.persistence.knowledge_writer`
already establishes for ``knowledge.documents``/``knowledge.chunks``:
that package (:mod:`ai_os_kernel.knowledge_manager`) remains an
intentionally untouched stub, and no owning Indexing Pipeline/Retrieval
Service exists yet to claim this either. This module lives in
:mod:`ai_os_kernel.retrieval` per this ticket's own ``module_path``,
importing :mod:`ai_os_kernel.persistence.knowledge_schema` directly —
the identical cross-package shape :mod:`ai_os_kernel.event_bus.
outbox_relay` already establishes for importing
:mod:`ai_os_kernel.persistence.platform_schema`.

**A pure persistence boundary — accepts an already-computed
``EmbeddingResponse``, never calls ``embed()`` itself.** Mirrors
:mod:`~ai_os_kernel.persistence.knowledge_writer`'s own "accepts
already-chunked input, performs no chunking of its own" shape:
computing the real embedding is a distinct concern (the LLM Gateway's
own, already-real job), not repeated here. :func:`embed_chunk` is the
separate, thin orchestrator that actually calls the real ``embed()``
and hands the result to :class:`SqlEmbeddingWriter` — "reuse the real
``embed()`` built last step, no parallel mechanism" in one real,
callable place, without collapsing the persistence boundary and the
Gateway call into one class.

**``index_generation`` starts at a real, disclosed constant
(:data:`INITIAL_INDEX_GENERATION`), not an invented business value.**
data_model.md §7: "``index_generation`` is pinnable in a search
request, so an experiment can retrieve against a fixed index even as
ingestion continues" — a real, evolving, system-wide counter incremented
by a re-index event. `platform.schema_metadata` (data_model.md §10) is
the documented home for that counter, but is deliberately not defined
anywhere in this codebase yet (`persistence/platform_schema.py`'s own
docstring: §10 gives it no column list to build against). No Version
Manager or re-index mechanism exists either. Because nothing in this
codebase has ever produced a second generation, ``1`` is not a guess —
it is the real, current, and today the *only* generation that exists;
whichever future step builds a real re-index mechanism decides what a
second value means, not this one.
"""

from __future__ import annotations

from typing import Protocol

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.llm_gateway.gateway import Embedder
from ai_os_kernel.llm_gateway.models import EmbeddingRequest, EmbeddingResponse
from ai_os_kernel.persistence.knowledge_ids import new_embedding_id
from ai_os_kernel.persistence.knowledge_schema import embeddings as embeddings_table

INITIAL_INDEX_GENERATION = 1


class EmbeddingWriteError(Exception):
    """A real embedding could not be written to ``knowledge.embeddings``.

    Raised for both invalid input (e.g. a response with no vectors) and
    a wrapped persistence-layer failure (including a real foreign-key
    violation when ``chunk_id`` names no real ``knowledge.chunks``
    row) — never a bare stack trace. The underlying exception, when
    there is one, is chained via ``from``.
    """


class EmbeddingRecord(BaseModel):
    """One ``knowledge.embeddings`` row, as written by
    :meth:`EmbeddingWriter.write_embedding`."""

    model_config = ConfigDict(frozen=True)

    embedding_id: str
    chunk_id: str
    embedding: list[float]
    embedding_model_id: str
    embedding_model_version: str
    dimensions: int
    index_generation: int


class EmbeddingWriter(Protocol):
    """Persistence boundary for writing one real embedding vector — the
    seam a fake implementation substitutes in unit tests (ADR-0004:
    interface-driven, configuration over code)."""

    async def write_embedding(
        self, *, chunk_id: str, response: EmbeddingResponse, vector_index: int = 0
    ) -> EmbeddingRecord: ...


class SqlEmbeddingWriter:
    """The only implementation of :class:`EmbeddingWriter` at this
    stage: SQLAlchemy 2.0 Core against Postgres/pgvector (ADR-0011,
    ADR-0013)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def write_embedding(
        self, *, chunk_id: str, response: EmbeddingResponse, vector_index: int = 0
    ) -> EmbeddingRecord:
        if not chunk_id or not chunk_id.strip():
            raise EmbeddingWriteError("chunk_id must not be blank")
        if not (0 <= vector_index < len(response.vectors)):
            raise EmbeddingWriteError(
                f"vector_index {vector_index} is out of range for a response with "
                f"{len(response.vectors)} vector(s)"
            )

        embedding_id = new_embedding_id()
        vector = response.vectors[vector_index]
        record = EmbeddingRecord(
            embedding_id=embedding_id,
            chunk_id=chunk_id,
            embedding=vector,
            embedding_model_id=response.model_id,
            embedding_model_version=response.model_version,
            dimensions=response.dimensions,
            index_generation=INITIAL_INDEX_GENERATION,
        )

        try:
            async with self._engine.begin() as connection:
                await connection.execute(
                    sa.insert(embeddings_table).values(
                        embedding_id=record.embedding_id,
                        chunk_id=record.chunk_id,
                        embedding=record.embedding,
                        embedding_model_id=record.embedding_model_id,
                        embedding_model_version=record.embedding_model_version,
                        dimensions=record.dimensions,
                        index_generation=record.index_generation,
                    )
                )
        except sa.exc.SQLAlchemyError as exc:
            raise EmbeddingWriteError(
                f"failed to write embedding for chunk '{chunk_id}': {exc}"
            ) from exc

        return record


async def embed_chunk(
    *, gateway: Embedder, writer: EmbeddingWriter, chunk_id: str, text: str, model_alias: str
) -> EmbeddingRecord:
    """Populates a real vector for one stored chunk (this ticket's own
    Goal: "Populate vectors for stored chunks") — calls the real,
    already-built ``embed()`` (``gateway``, any real
    :class:`~ai_os_kernel.llm_gateway.gateway.Embedder`, e.g. the real
    ``DispatchingLLMGateway``) exactly once, then persists the result
    via ``writer``. No parallel embedding mechanism: this function
    contains no vector-producing logic of its own.
    """
    response = await gateway.embed(EmbeddingRequest(model_alias=model_alias, inputs=[text]))
    return await writer.write_embedding(chunk_id=chunk_id, response=response)
