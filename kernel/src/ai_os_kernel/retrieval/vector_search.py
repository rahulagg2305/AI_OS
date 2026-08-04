"""Real nearest-neighbour vector search over ``knowledge.embeddings``
(search_vector_search.md §3/§4, ADR-0013, ``P02-S04-M11-T04``).

**Exact pgvector cosine distance (``<=>``), not the documented HNSW
index — a real, disclosed scope boundary, not an oversight.** §4's own
high-level structure names "Vector Search — pgvector HNSW, cosine
distance." pgvector's HNSW index requires a fixed vector dimension to
be created at all — the exact, already-disclosed ambiguity
:mod:`ai_os_kernel.persistence.knowledge_schema`'s own docstring
explains ``knowledge.embeddings.embedding`` cannot resolve yet (no real
embedding model has been chosen as authoritative, so the column stays
an unconstrained ``Vector()``). Building an HNSW index now would
require inventing that same not-yet-made decision. A plain
``ORDER BY embedding <=> :query_vector`` is not an approximation of
HNSW's own answer — it is the mathematically *exact* nearest-neighbour
ranking pgvector's own cosine-distance operator computes directly,
just without the index HNSW would use to answer the identical
question faster at a scale this ticket does not ask for. This module
genuinely satisfies "Nearest-neighbour retrieval over embeddings" /
"Ranked neighbours" today; adding an HNSW index later, once a real
embedding model/dimension is chosen, is a purely additive migration
and constructor change, not a redesign of this query.

**Every query is filtered by ``embedding_model_id``/
``embedding_model_version`` — required, not optional parameters.**
search_vector_search.md §4: "queries compare only vectors from the
same model and version" — a real, hard correctness rule (comparing
vectors from different embedding models is not merely a worse answer,
it is a meaningless one), enforced structurally here rather than left
to caller discipline.

**``index_generation`` is an optional pin, not a required filter** —
§4: "``index_generation`` is pinnable in a request so an experiment
retrieves against a fixed index while ingestion continues." ``None``
(the default) searches every generation; a real caller that needs a
fixed index for reproducibility supplies the real generation number
recorded on the rows it wants to compare against.
"""

from __future__ import annotations

from typing import Protocol

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.persistence.knowledge_schema import embeddings as embeddings_table


class VectorSearchError(Exception):
    """A real nearest-neighbour query against ``knowledge.embeddings``
    could not be completed — wraps a persistence-layer failure (e.g. a
    real query-vector/stored-vector dimension mismatch pgvector itself
    refuses), never a bare stack trace. The underlying exception is
    chained via ``from``.
    """


class RankedNeighbor(BaseModel):
    """One real result row: which stored embedding matched, the real
    ``knowledge.chunks`` row it belongs to, and its real cosine
    distance to the query vector (``0.0`` identical, ``2.0`` opposite)
    — ordered ascending, nearest first, by the caller-visible list
    order :meth:`VectorSearcher.search` returns."""

    model_config = ConfigDict(frozen=True)

    chunk_id: str
    embedding_id: str
    distance: float


class VectorSearcher(Protocol):
    """Real nearest-neighbour retrieval over ``knowledge.embeddings`` —
    the seam a future dedicated vector store (Qdrant, behind this same
    Protocol per search_vector_search.md §4's own documented scale
    trigger) substitutes later without changing any caller (ADR-0004)."""

    async def search(
        self,
        *,
        query_vector: list[float],
        embedding_model_id: str,
        embedding_model_version: str,
        limit: int,
        index_generation: int | None = None,
    ) -> list[RankedNeighbor]: ...


class SqlVectorSearcher:
    """The only implementation of :class:`VectorSearcher` at this
    stage: pgvector's real ``<=>`` cosine-distance operator against
    Postgres (ADR-0011, ADR-0013)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def search(
        self,
        *,
        query_vector: list[float],
        embedding_model_id: str,
        embedding_model_version: str,
        limit: int,
        index_generation: int | None = None,
    ) -> list[RankedNeighbor]:
        if limit <= 0:
            raise VectorSearchError("limit must be positive")
        if not query_vector:
            raise VectorSearchError("query_vector must not be empty")

        distance = embeddings_table.c.embedding.cosine_distance(query_vector).label("distance")
        query = (
            sa.select(embeddings_table.c.chunk_id, embeddings_table.c.embedding_id, distance)
            .where(embeddings_table.c.embedding_model_id == embedding_model_id)
            .where(embeddings_table.c.embedding_model_version == embedding_model_version)
            .order_by(distance)
            .limit(limit)
        )
        if index_generation is not None:
            query = query.where(embeddings_table.c.index_generation == index_generation)

        try:
            async with self._engine.connect() as connection:
                result = await connection.execute(query)
                return [
                    RankedNeighbor(
                        chunk_id=row.chunk_id,
                        embedding_id=row.embedding_id,
                        distance=row.distance,
                    )
                    for row in result
                ]
        except sa.exc.SQLAlchemyError as exc:
            raise VectorSearchError(f"nearest-neighbour query failed: {exc}") from exc
