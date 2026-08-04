"""One real, callable service interface over the two already-real
search strategies and their already-real fusion
(``P02-S04-M11-T01``/``T04``/``T05``) — this ticket's own "one service
interface over both strategies."

**Composes the three already-real pieces; reimplements none of
them.** :class:`RetrievalService` holds a real
:class:`~ai_os_kernel.persistence.knowledge_keyword_search.KeywordSearcher`
and a real
:class:`~ai_os_kernel.retrieval.vector_search.VectorSearcher` and calls
both, unchanged, then hands their two real result lists to the already-
real, pure :func:`~ai_os_kernel.retrieval.hybrid_search.fuse_rankings`
— the identical "orchestrate already-real collaborators, no parallel
mechanism" shape :func:`~ai_os_kernel.retrieval.embedding_writer.
embed_chunk` already establishes for calling ``embed()`` then a writer.

**``RetrievalRequest.limit`` has no default (unlike
``KeywordSearcher.search``'s own optional default)** — mirroring
:class:`~ai_os_kernel.retrieval.vector_search.VectorSearcher`'s own
stricter, no-default ``limit`` parameter, and the task's own "no
hardcoded values" constraint: a shared default here would be a value
this service invents, not one either real dependency already commits
to. The identical ``limit`` is used as each individual searcher's own
top-K *and* as :func:`fuse_rankings`' final truncation — the simplest
behaviour fully determined by the two real dependencies' own contracts,
not a distinct over-fetch multiplier this step invents.

**Deliberately not calling ``embed()``.** The task itself scopes this
service to composing exactly "the three already-real pieces (keyword
search, vector search, RRF fusion)" — a fourth, the LLM Gateway's real
``embed()``, is out of that scope. ``RetrievalRequest.query_vector`` is
supplied already-computed by the caller, the same "accepts an already-
computed embedding, never calls ``embed()`` itself" boundary
:class:`~ai_os_kernel.retrieval.embedding_writer.SqlEmbeddingWriter`
already draws on the write side.

No error wrapping of its own: a real
:class:`~ai_os_kernel.persistence.knowledge_keyword_search.KeywordSearchError`
or :class:`~ai_os_kernel.retrieval.vector_search.VectorSearchError`
propagates unchanged — introducing a third exception type here to wrap
two already-real, already-specific ones would be a parallel mechanism,
not a composition.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from ai_os_kernel.persistence.knowledge_keyword_search import KeywordSearcher
from ai_os_kernel.retrieval.hybrid_search import FusedResult, fuse_rankings
from ai_os_kernel.retrieval.vector_search import VectorSearcher


class RetrievalRequest(BaseModel):
    """A single retrieval request carrying everything both real
    searchers need — a plain-text query for keyword search and an
    already-computed vector (plus its real provenance fields) for
    vector search."""

    model_config = ConfigDict(frozen=True)

    query_text: str
    query_vector: list[float]
    embedding_model_id: str
    embedding_model_version: str
    limit: int
    index_generation: int | None = None


class RetrievalService:
    """Composes a real :class:`KeywordSearcher` and a real
    :class:`VectorSearcher` behind one interface, fusing their results
    with the already-real :func:`fuse_rankings`."""

    def __init__(
        self, *, keyword_searcher: KeywordSearcher, vector_searcher: VectorSearcher
    ) -> None:
        self._keyword_searcher = keyword_searcher
        self._vector_searcher = vector_searcher

    async def search(self, request: RetrievalRequest) -> list[FusedResult]:
        keyword_results = await self._keyword_searcher.search(
            query=request.query_text, limit=request.limit
        )
        vector_results = await self._vector_searcher.search(
            query_vector=request.query_vector,
            embedding_model_id=request.embedding_model_id,
            embedding_model_version=request.embedding_model_version,
            limit=request.limit,
            index_generation=request.index_generation,
        )
        return fuse_rankings(
            keyword_results=keyword_results,
            vector_results=vector_results,
            limit=request.limit,
        )
