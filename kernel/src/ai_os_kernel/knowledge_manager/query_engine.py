"""The real Query Engine (``P02-S04-M09-T04``) — "Answer knowledge
queries behind one interface" (this ticket's own Goal), reusing the
already-real :class:`~ai_os_kernel.retrieval.retrieval_service.
RetrievalService` (``P02-S04-M11-T06``) unchanged — no parallel search
mechanism.

**Real value this step adds: provenance enrichment.**
:class:`~ai_os_kernel.retrieval.hybrid_search.FusedResult` (the real
output ``RetrievalService.search()`` already returns) carries only
*rank* provenance (``keyword_rank``/``vector_rank``) — it has no
``content``, ``source_uri``, or ``trust`` at all. This ticket's own
Output is literally "Ranked results with provenance"
(search_vector_search.md §3's identical phrase), so
:meth:`QueryEngine.query` joins each real fused ``chunk_id`` back to
its real ``knowledge.chunks``/``knowledge.documents`` rows and attaches
that real source provenance — the genuine gap between what
``RetrievalService`` already returns and what this ticket's Output
promises.

**That same join is also the natural, in-scope place to partially
close the ``archived_at``-filtering gap disclosed at
``P02-S04-M09-T03``.** The join's ``WHERE documents.archived_at IS
NULL`` means a caller of *this* interface never sees a superseded
chunk — a real, tested improvement. **Disclosed, not fully closed:**
the filter runs after :func:`~ai_os_kernel.retrieval.hybrid_search.
fuse_rankings` has already applied ``limit``, so a query whose top
hits include an archived chunk can genuinely return fewer than
``request.limit`` results; and a caller who reaches
``RetrievalService``, :class:`~ai_os_kernel.persistence.
knowledge_keyword_search.SqlKeywordSearcher`, or
:class:`~ai_os_kernel.retrieval.vector_search.SqlVectorSearcher`
directly, bypassing this Query Engine, still sees it unfiltered —
fixing that at the lowest layer would mean modifying two already-real,
separately-tested searchers, a real expansion beyond what "provenance
enrichment" itself requires, deliberately left for a later step.

**No ``embed()`` call — the identical, disclosed scope boundary
``RetrievalService`` itself already establishes.** This engine's own
``query()`` still takes a full
:class:`~ai_os_kernel.retrieval.retrieval_service.RetrievalRequest`
(reused as-is, not a parallel request shape): the caller supplies
``query_vector``. Computing one from plain text would mean choosing a
default embedding model/alias this codebase has no configured,
documented answer for (ADR-0002: never a literal model id) — the same
reasoning ``RetrievalService``'s own docstring already gives, applied
consistently one layer up rather than re-opened as a new question.
"""

from __future__ import annotations

from typing import Literal

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.persistence.knowledge_schema import chunks as chunks_table
from ai_os_kernel.persistence.knowledge_schema import documents as documents_table
from ai_os_kernel.retrieval.retrieval_service import RetrievalRequest, RetrievalService


class QueryError(Exception):
    """A knowledge query could not be answered — a wrapped
    persistence-layer failure during provenance enrichment, never a
    bare stack trace. The underlying exception is chained via
    ``from``."""


class KnowledgeQueryResult(BaseModel):
    """One ranked result, real fusion score plus real source
    provenance — this ticket's own "ranked results with provenance,"
    fully assembled."""

    model_config = ConfigDict(frozen=True)

    chunk_id: str
    document_id: str
    source_uri: str
    trust: Literal["trusted", "untrusted"]
    content: str
    fused_score: float
    keyword_rank: int | None
    vector_rank: int | None


class QueryEngine:
    """Composes the real :class:`RetrievalService` with a real
    provenance join — the one interface this ticket's own Goal names."""

    def __init__(self, *, engine: AsyncEngine, retrieval_service: RetrievalService) -> None:
        self._engine = engine
        self._retrieval_service = retrieval_service

    async def query(self, request: RetrievalRequest) -> list[KnowledgeQueryResult]:
        fused_results = await self._retrieval_service.search(request)
        if not fused_results:
            return []

        chunk_ids = [result.chunk_id for result in fused_results]
        try:
            async with self._engine.connect() as connection:
                rows = (
                    (
                        await connection.execute(
                            sa.select(
                                chunks_table.c.chunk_id,
                                chunks_table.c.document_id,
                                chunks_table.c.content,
                                documents_table.c.source_uri,
                                documents_table.c.trust,
                            )
                            .select_from(
                                chunks_table.join(
                                    documents_table,
                                    chunks_table.c.document_id == documents_table.c.document_id,
                                )
                            )
                            .where(chunks_table.c.chunk_id.in_(chunk_ids))
                            .where(documents_table.c.archived_at.is_(None))
                        )
                    )
                    .mappings()
                    .all()
                )
        except sa.exc.SQLAlchemyError as exc:
            raise QueryError(
                f"failed to enrich provenance for {len(chunk_ids)} chunk(s): {exc}"
            ) from exc

        provenance_by_chunk_id = {row["chunk_id"]: row for row in rows}

        results: list[KnowledgeQueryResult] = []
        for fused_result in fused_results:
            row = provenance_by_chunk_id.get(fused_result.chunk_id)
            if row is None:
                # Genuinely superseded (archived_at is set) -- excluded,
                # not an error. See this module's own docstring.
                continue
            results.append(
                KnowledgeQueryResult(
                    chunk_id=fused_result.chunk_id,
                    document_id=row["document_id"],
                    source_uri=row["source_uri"],
                    trust=row["trust"],
                    content=row["content"],
                    fused_score=fused_result.fused_score,
                    keyword_rank=fused_result.keyword_rank,
                    vector_rank=fused_result.vector_rank,
                )
            )
        return results
