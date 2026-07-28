"""Minimal read path for ``knowledge.chunks`` — search_vector_search.md's
own "Keyword Search: Postgres FTS: tsvector + GIN" component, in its
smallest real form: rank matching chunks for a plain-text query against
the already-existing ``content_tsv`` generated column and its GIN index
(:mod:`ai_os_kernel.persistence.knowledge_schema`). No new index, no
schema change — this module only queries what already exists.

**Deliberately not the Retrieval Service, and not placed inside a
``knowledge_manager``/``retrieval`` component package.** search_vector_search.md
also documents a Hybrid Ranker, a Metadata Filter, and Access Control
sitting in front of Keyword Search — none of those exist here. This is
a bare persistence-layer reader, the identical "own module, no owning
domain component built yet" shape already established for
:mod:`ai_os_kernel.persistence.knowledge_writer` (the previous step) and
:class:`~ai_os_kernel.prompt_engine.catalog.SqlPromptCatalog` (a thin
read mirroring a thin write): look up matching rows, map them onto a
reduced result shape, fail cleanly if the query itself fails. No
metadata/``project_id``/``trust`` filtering, no access control, no
vector or hybrid component, no RRF fusion — all explicitly out of scope
for this step.

**``plainto_tsquery``, not ``websearch_to_tsquery`` or ``to_tsquery``.**
``plainto_tsquery`` treats the entire input as plain text and ANDs every
recognised lexeme together, exposing no query syntax at all (no quoted
phrases, no exclusions, no boolean operators) — the simplest, safest
match for "accepts a plain-text query string," this step's own words.
``websearch_to_tsquery``'s richer syntax (phrases, exclusion) and
``to_tsquery``'s raw boolean operators are both real, documented
Postgres capabilities deliberately deferred, not overlooked.

**The query is parsed with the identical ``'english'`` text-search
configuration ``content_tsv`` was generated with**
(``to_tsvector('english', content)`` — see ``knowledge_schema.py``'s own
docstring). This is not a second, independent choice: a query parsed
under a different configuration would silently stop matching rows it
should, since Postgres's ``@@`` match operator compares stemmed
lexemes, not raw text — the two configurations must always agree. Not
made configurable this step for the same reason the generated column's
own configuration is not: doing so would require a per-chunk (or
per-query) configuration column data_model.md §7 does not document.

**Ranking is Postgres's own ``ts_rank`` against the matched query,
descending, with ``chunk_id`` (a sortable ULID) as a deterministic
tiebreak** — ADR-0022's reproducibility requirement applies to every
deterministic read in this codebase, and two chunks scoring identically
under ``ts_rank`` would otherwise have no guaranteed relative order
across repeated identical queries. No custom scoring, weighting, or
multi-signal ranking exists — that is the still-unbuilt Hybrid Ranker's
job (search_vector_search.md), not this reader's.

**A blank query, or a non-positive ``limit``, is rejected before any
query runs** — the identical "clear error before a query that could
only ever return nothing useful" discipline already applied by
:class:`~ai_os_kernel.llm_gateway.call_recorder.SqlLLMCallRecorder`'s own
blank-field checks. ``limit`` defaults to a named, documented constant
rather than being unbounded — the same "named default, not a magic
number silently baked into a query" shape ``kernel/bootstrap.py``'s own
policy constants already use, though this one lives on the method
signature itself since there is no composition root wiring yet for this
step.

No writer, no update, no delete, no filtering beyond the query text
itself, no HTTP route, no Context Manager resolver — "prove the reader
in isolation," per this step's own scope. Integration tests seed real
rows via the previous step's own :class:`~ai_os_kernel.persistence.
knowledge_writer.SqlKnowledgeWriter`, not hand-written SQL, proving the
two increments compose correctly end to end.
"""

from __future__ import annotations

from typing import Protocol

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.persistence.knowledge_schema import chunks

# Matches the text-search configuration `content_tsv` was generated
# with (`to_tsvector('english', content)`) — see this module's own
# docstring for why the two must always agree.
_TEXT_SEARCH_CONFIG = "english"

# A named, documented default rather than an unbounded query or a
# magic number inline at each call site — a caller may always override
# it explicitly.
_DEFAULT_LIMIT = 10


class KeywordSearchError(Exception):
    """A keyword search could not be performed.

    Raised for both invalid input (a blank query, a non-positive
    ``limit``) and a wrapped persistence-layer failure — never a bare
    stack trace. The underlying exception, when there is one, is
    chained via ``from``.
    """


class ChunkSearchResult(BaseModel):
    """One ``knowledge.chunks`` row matching a keyword search, ranked by
    Postgres's own ``ts_rank`` against the parsed query."""

    model_config = ConfigDict(frozen=True)

    chunk_id: str
    document_id: str
    content: str
    rank: float


class KeywordSearcher(Protocol):
    """Persistence boundary for ranked keyword search over
    ``knowledge.chunks.content_tsv`` — the seam a fake implementation
    substitutes in unit tests (ADR-0004: interface-driven, configuration
    over code)."""

    async def search(
        self, *, query: str, limit: int = _DEFAULT_LIMIT
    ) -> list[ChunkSearchResult]: ...


class SqlKeywordSearcher:
    """The only implementation of :class:`KeywordSearcher` at this
    stage: SQLAlchemy 2.0 Core against Postgres full-text search
    (ADR-0011)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def search(self, *, query: str, limit: int = _DEFAULT_LIMIT) -> list[ChunkSearchResult]:
        if not query or not query.strip():
            raise KeywordSearchError("query must not be blank")
        if limit <= 0:
            raise KeywordSearchError(f"limit must be positive, got {limit}")

        tsquery = sa.func.plainto_tsquery(_TEXT_SEARCH_CONFIG, query)
        rank = sa.func.ts_rank(chunks.c.content_tsv, tsquery).label("rank")

        try:
            async with self._engine.connect() as connection:
                result = await connection.execute(
                    sa.select(
                        chunks.c.chunk_id,
                        chunks.c.document_id,
                        chunks.c.content,
                        rank,
                    )
                    .where(chunks.c.content_tsv.op("@@")(tsquery))
                    .order_by(rank.desc(), chunks.c.chunk_id.asc())
                    .limit(limit)
                )
                rows = result.mappings().all()
        except sa.exc.SQLAlchemyError as exc:
            raise KeywordSearchError(f"failed to search for query {query!r}: {exc}") from exc

        return [ChunkSearchResult.model_validate(dict(row)) for row in rows]
