"""Real Hybrid Ranker: Reciprocal Rank Fusion over the two already-real
search paths this module now has — keyword (``P02-S04-M11-T01``) and
vector (``P02-S04-M11-T04``) — per search_vector_search.md §4's own
"Hybrid Ranker — Reciprocal Rank Fusion" and ADR-0013's decision record
(§ "Hybrid ranking").

**A pure function over two already-produced ranked lists — calls
neither searcher itself.** Mirrors this package's own established
"pure persistence/combination boundary, real I/O happens elsewhere"
shape (:mod:`ai_os_kernel.retrieval.embedding_writer`'s own
``SqlEmbeddingWriter`` vs. ``embed_chunk`` split): "reuse the real
keyword/vector search, no parallel mechanism" is satisfied by a caller
running both real searches first and handing the two real result
lists here — this module contains no search logic of its own, only
fusion.

**Standard Reciprocal Rank Fusion, fixed ``k`` (not a per-corpus
tuning knob).** ADR-0013's own "Hybrid ranking" row: "RRF is chosen
because it needs no score normalisation between two incomparable
scoring systems *and no tuning parameter per corpus*." The real,
well-known Cormack/Clarke/Buettcher RRF formula
(``score = sum(1 / (k + rank))`` across every list an item appears in,
1-indexed rank) already has exactly this property — ``k`` is a fixed
constant proven to work well across corpora without being re-tuned
per dataset, which is precisely the "no tuning parameter" advantage
the ADR cites, not a claim that no constant exists at all.
:data:`RRF_K` uses ``60``, the original paper's own real, published
value, not an invented number — a real citation, not a guess.

**Fusion key is ``chunk_id`` — the only identifier both real result
shapes share** (:class:`~ai_os_kernel.persistence.
knowledge_keyword_search.ChunkSearchResult`/:class:`~ai_os_kernel.
retrieval.vector_search.RankedNeighbor`). An item present in only one
list still contributes its own real reciprocal-rank score from that
one list — RRF's own standard "let each ranker vote independently,
absence from one list is zero contribution, not exclusion" behaviour,
not a design choice unique to this implementation.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from ai_os_kernel.persistence.knowledge_keyword_search import ChunkSearchResult
from ai_os_kernel.retrieval.vector_search import RankedNeighbor

# The original Reciprocal Rank Fusion paper's own published constant
# (Cormack, Clarke & Buettcher, 2009, "Reciprocal Rank Fusion Outperforms
# Condorcet and Individual Rank Learning Methods") -- a real, cited
# value, not an invented one. ADR-0013's own "no tuning parameter per
# corpus" reasoning for choosing RRF at all depends on treating this as
# fixed, not re-tuned per dataset.
RRF_K = 60


class FusedResult(BaseModel):
    """One real chunk's fused ranking — its combined RRF score, and,
    for provenance (search_vector_search.md §3: "return ranked results
    with provenance"), its real 1-indexed rank in each individual list
    it appeared in at all (``None`` when it was genuinely absent from
    that list, not a fabricated rank)."""

    model_config = ConfigDict(frozen=True)

    chunk_id: str
    fused_score: float
    keyword_rank: int | None
    vector_rank: int | None


def fuse_rankings(
    *,
    keyword_results: Sequence[ChunkSearchResult],
    vector_results: Sequence[RankedNeighbor],
    limit: int | None = None,
    k: int = RRF_K,
) -> list[FusedResult]:
    """Combines two already-real, already-ranked result lists (each
    already ordered best-first by its own real scorer — descending
    ``ts_rank`` for ``keyword_results``, ascending cosine distance for
    ``vector_results``) into one real fused ranking, descending by
    :attr:`FusedResult.fused_score`.

    Ties are broken by ``chunk_id`` ascending — the identical
    "sortable ULID as a deterministic tiebreak" reproducibility
    requirement (ADR-0022) :class:`~ai_os_kernel.persistence.
    knowledge_keyword_search.SqlKeywordSearcher` already applies to its
    own ``ts_rank`` ties.
    """
    scores: dict[str, float] = {}
    keyword_ranks: dict[str, int] = {}
    vector_ranks: dict[str, int] = {}

    for rank, result in enumerate(keyword_results, start=1):
        keyword_ranks[result.chunk_id] = rank
        scores[result.chunk_id] = scores.get(result.chunk_id, 0.0) + 1.0 / (k + rank)

    for rank, neighbor in enumerate(vector_results, start=1):
        vector_ranks[neighbor.chunk_id] = rank
        scores[neighbor.chunk_id] = scores.get(neighbor.chunk_id, 0.0) + 1.0 / (k + rank)

    fused = [
        FusedResult(
            chunk_id=chunk_id,
            fused_score=score,
            keyword_rank=keyword_ranks.get(chunk_id),
            vector_rank=vector_ranks.get(chunk_id),
        )
        for chunk_id, score in scores.items()
    ]
    fused.sort(key=lambda result: (-result.fused_score, result.chunk_id))

    return fused[:limit] if limit is not None else fused
