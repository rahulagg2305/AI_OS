"""The real Query Engine (``P02-S04-M09-T04``; provenance/versioning
extended ``P02-S04-M09-T05``) — "Answer knowledge queries behind one
interface" (this ticket's own Goal), reusing the already-real
:class:`~ai_os_kernel.retrieval.retrieval_service.RetrievalService`
(``P02-S04-M11-T06``) unchanged — no parallel search mechanism.

**Version provenance (``P02-S04-M09-T05``): surfaced, not managed.**
``P02-S04-M09-T05``'s own Goal — "every retrieved item carries source
and version" — is satisfied by joining two already-real, already-
documented columns onto every result, not by building a new
mechanism: ``chunks.chunk_strategy_version`` (data_model.md §7, real
since ``P02-S04-M09-T03``) is present on every result unconditionally
— every chunk, however it was found, was chunked with a real, stored
strategy version. ``embeddings.embedding_model_id``/
``embedding_model_version``/``index_generation`` are present only when
this exact chunk has a real embedding row under the request's own
queried model/version (``None`` for a keyword-only hit — a real,
disclosed absence, not a guess). **Deliberately not built: a real
"Version Manager" that decides or manages what a second
``index_generation`` means** — knowledge_manager.md's own
Implementation Status already names that as unbuilt, and nothing about
"every retrieved item carries source and version" requires deciding
that; it only requires reporting whichever generation a matching
embedding row genuinely has.

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
from ai_os_kernel.persistence.knowledge_schema import embeddings as embeddings_table
from ai_os_kernel.retrieval.retrieval_service import RetrievalRequest, RetrievalService
from ai_os_kernel.security_manager.permissions import KNOWLEDGE_READ


class QueryError(Exception):
    """A knowledge query could not be answered — a wrapped
    persistence-layer failure during provenance enrichment, never a
    bare stack trace. The underlying exception is chained via
    ``from``."""


class KnowledgeQueryResult(BaseModel):
    """One ranked result, real fusion score plus real source *and
    version* provenance (``P02-S04-M09-T05``'s own Goal: "every
    retrieved item carries source and version") — this ticket's own
    "ranked results with provenance," fully assembled."""

    model_config = ConfigDict(frozen=True)

    chunk_id: str
    document_id: str
    source_uri: str
    trust: Literal["trusted", "untrusted"]
    content: str
    fused_score: float
    keyword_rank: int | None
    vector_rank: int | None
    chunk_strategy_version: str
    embedding_model_id: str | None
    embedding_model_version: str | None
    index_generation: int | None


def knowledge_access_predicate(
    principal_permissions: frozenset[str] | None,
) -> sa.ColumnElement[bool]:
    """§5's **Access / Filter Layer** (`P02-S04-M09-T08`), as a real SQL
    predicate.

    **A predicate, not a post-filter, and that is a requirement rather
    than a style choice.** search_vector_search.md §4 specifies "Access
    Control — applied AS SQL PREDICATES, not post-filtering", and
    ADR-0013 chose pgvector partly for "permission trimming that cannot
    leak through ranking". Returning ``sa.false()`` keeps the trimming
    inside the same statement that resolves provenance and ordering, so
    a denied principal's rows are never materialised, never ranked, and
    never counted — none of which a Python-side filter could promise.

    **Binary today, and honestly so.** ``knowledge.documents`` carries
    ``source_uri``, ``trust``, ``project_id`` and ``archived_at`` — no
    owner or classification column — so there is nothing to discriminate
    *between* documents on. A permitted principal sees every
    non-archived document. ``project_id`` scoping is the real documented
    next step (`knowledge/knowledge_base_structure.md` §3: keeping
    project trees separate "prevents one project's content from being
    retrieved into another's context") and is **not implementable
    today**: ``workflow_instances`` has no ``project_id``, nothing in
    the Workflow Engine carries one, and the ingestion scan writes
    ``NULL`` for every document — so there is no principal-to-project
    binding to filter on that would not have to be invented.

    **``None`` denies — this gate fails closed (R-021, 2026-08-14).**

    It did not originally. ``None`` first meant "this path does not
    carry identity yet, so do not enforce", on the reasoning that no
    principal reached most retrieval paths and denying would change the
    behaviour of already-running code. A targeted R-021 investigation
    then found that reasoning rested on a false premise: identity *was*
    reaching the retrieval path on every route that mattered, and the
    one exception was a **real, authenticated bypass** —
    ``ExperimentRunOrchestrator.run`` took the principal's id but not
    their permissions, so every instance created by
    ``POST /experiments/{id}/run`` persisted
    ``principal_permissions = NULL`` and retrieved knowledge with the
    gate switched off. That bypass is fixed at its source, but it proved
    the failure mode is real rather than theoretical: with a fail-open
    default, any future creation path is one forgotten argument away
    from silently disabling a security control, and nothing fails.

    Failing closed inverts that. A forgotten argument now degrades the
    prompt — :class:`~ai_os_kernel.context_manager.resolvers.
    KnowledgeResolver` contributes no items and the agent still runs —
    which is visible and safe, rather than invisible and permissive.
    That asymmetry is what makes ADR-0023's "absence of a permission is
    denial, never a default-allow" affordable here: the cost of denying
    wrongly is a thinner context, not a failed workflow.

    Every real caller supplies permissions: ``routes/workflows.py`` and
    ``routes/experiments.py`` both pass ``security_context.permissions``,
    and both triggers forward them onto the instance. A caller that
    genuinely has no principal — a background composition, a test —
    must now say so by passing an explicit empty ``frozenset()``, which
    denies, or a real permission set, which does not.
    """
    if principal_permissions is None:
        return sa.false()
    if KNOWLEDGE_READ in principal_permissions:
        return sa.true()
    return sa.false()


class QueryEngine:
    """Composes the real :class:`RetrievalService` with a real
    provenance join — the one interface this ticket's own Goal names."""

    def __init__(self, *, engine: AsyncEngine, retrieval_service: RetrievalService) -> None:
        self._engine = engine
        self._retrieval_service = retrieval_service

    async def query(
        self,
        request: RetrievalRequest,
        *,
        principal_permissions: frozenset[str] | None = None,
    ) -> list[KnowledgeQueryResult]:
        fused_results = await self._retrieval_service.search(request)
        if not fused_results:
            return []

        chunk_ids = [result.chunk_id for result in fused_results]
        # Real embedding provenance only for the exact model/version
        # this request actually searched with -- an embedding row
        # under a different model would never be the reason this chunk
        # matched, so joining on anything broader would attach
        # provenance that misrepresents why the hit happened.
        embedding_join_condition = sa.and_(
            embeddings_table.c.chunk_id == chunks_table.c.chunk_id,
            embeddings_table.c.embedding_model_id == request.embedding_model_id,
            embeddings_table.c.embedding_model_version == request.embedding_model_version,
        )
        try:
            async with self._engine.connect() as connection:
                rows = (
                    (
                        await connection.execute(
                            sa.select(
                                chunks_table.c.chunk_id,
                                chunks_table.c.document_id,
                                chunks_table.c.content,
                                chunks_table.c.chunk_strategy_version,
                                documents_table.c.source_uri,
                                documents_table.c.trust,
                                embeddings_table.c.embedding_model_id,
                                embeddings_table.c.embedding_model_version,
                                embeddings_table.c.index_generation,
                            )
                            .select_from(
                                chunks_table.join(
                                    documents_table,
                                    chunks_table.c.document_id == documents_table.c.document_id,
                                ).outerjoin(embeddings_table, embedding_join_condition)
                            )
                            .where(chunks_table.c.chunk_id.in_(chunk_ids))
                            .where(documents_table.c.archived_at.is_(None))
                            # §5's Access / Filter Layer, in the same
                            # statement that resolves provenance and
                            # ordering — see `knowledge_access_predicate`.
                            .where(knowledge_access_predicate(principal_permissions))
                            # Deterministic (ADR-0022) even in the
                            # currently-unreachable case of more than one
                            # embedding row for the same chunk under this
                            # exact model/version: the highest
                            # index_generation wins, tie-broken by
                            # embedding_id -- the dict below keeps the
                            # *last* row per chunk_id, so ascending order
                            # here means the winner is deterministically
                            # the highest generation.
                            .order_by(
                                embeddings_table.c.index_generation.asc(),
                                embeddings_table.c.embedding_id.asc(),
                            )
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
                    chunk_strategy_version=row["chunk_strategy_version"],
                    embedding_model_id=row["embedding_model_id"],
                    embedding_model_version=row["embedding_model_version"],
                    index_generation=row["index_generation"],
                )
            )
        return results
