"""fuse_rankings() is a pure function over two already-real result
shapes (:class:`ChunkSearchResult`/:class:`RankedNeighbor`) with no I/O
of its own -- so, unlike this package's other retrieval tests, no real
Postgres container is needed here (ADR-0015 governs mocking *real
infrastructure*; there is no infrastructure in this function's own
contract to mock or to fake). Every assertion below is checked against
a hand-computed real Reciprocal Rank Fusion score
(``1 / (RRF_K + 1-indexed rank)``, ``RRF_K = 60``), the identical
"hand-computed real math, not just 'it ran'" rigor already applied in
``tests/integration/retrieval/test_vector_search.py``'s own cosine
distances.
"""

from __future__ import annotations

import pytest

from ai_os_kernel.persistence.knowledge_keyword_search import ChunkSearchResult
from ai_os_kernel.retrieval.hybrid_search import RRF_K, fuse_rankings
from ai_os_kernel.retrieval.vector_search import RankedNeighbor


def _chunk(chunk_id: str, rank: float) -> ChunkSearchResult:
    return ChunkSearchResult(chunk_id=chunk_id, document_id="doc-1", content="x", rank=rank)


def _neighbor(chunk_id: str, distance: float) -> RankedNeighbor:
    return RankedNeighbor(chunk_id=chunk_id, embedding_id="emb-1", distance=distance)


def test_fused_ranking_genuinely_differs_from_both_individual_rankings() -> None:
    # Keyword order (best first): A, B, C, D.
    # Vector order (best first):  D, A, C, B.
    # Deliberately conflicting so neither individual list's order can
    # possibly equal the fused order by coincidence.
    keyword_results = [
        _chunk("chunk-a", rank=4.0),
        _chunk("chunk-b", rank=3.0),
        _chunk("chunk-c", rank=2.0),
        _chunk("chunk-d", rank=1.0),
    ]
    vector_results = [
        _neighbor("chunk-d", distance=0.01),
        _neighbor("chunk-a", distance=0.05),
        _neighbor("chunk-c", distance=0.10),
        _neighbor("chunk-b", distance=0.20),
    ]

    fused = fuse_rankings(keyword_results=keyword_results, vector_results=vector_results)
    fused_order = [result.chunk_id for result in fused]

    keyword_order = [result.chunk_id for result in keyword_results]
    vector_order = [neighbor.chunk_id for neighbor in vector_results]
    assert fused_order != keyword_order
    assert fused_order != vector_order

    # Hand-computed: score(x) = 1/(60 + keyword_rank) + 1/(60 + vector_rank).
    # A: kw=1 (1/61), vec=2 (1/62) -> 0.032522474881016
    # D: kw=4 (1/64), vec=1 (1/61) -> 0.032018442622951
    # B: kw=2 (1/62), vec=4 (1/64) -> 0.031754032258065
    # C: kw=3 (1/63), vec=3 (1/63) -> 0.031746031746032
    assert fused_order == ["chunk-a", "chunk-d", "chunk-b", "chunk-c"]
    scores = {result.chunk_id: result.fused_score for result in fused}
    assert scores["chunk-a"] == pytest.approx(1 / 61 + 1 / 62)
    assert scores["chunk-d"] == pytest.approx(1 / 64 + 1 / 61)
    assert scores["chunk-b"] == pytest.approx(1 / 62 + 1 / 64)
    assert scores["chunk-c"] == pytest.approx(1 / 63 + 1 / 63)
    assert scores["chunk-a"] > scores["chunk-d"] > scores["chunk-b"] > scores["chunk-c"]


def test_a_chunk_present_in_only_one_list_still_contributes_its_own_rank() -> None:
    keyword_only = _chunk("keyword-only", rank=1.0)
    vector_only = _neighbor("vector-only", distance=0.01)
    both = [_chunk("both", rank=5.0)]
    both_vector = [_neighbor("both", distance=0.5)]

    fused = fuse_rankings(
        keyword_results=[keyword_only, *both],
        vector_results=[vector_only, *both_vector],
    )
    by_id = {result.chunk_id: result for result in fused}

    assert by_id["keyword-only"].keyword_rank == 1
    assert by_id["keyword-only"].vector_rank is None
    assert by_id["keyword-only"].fused_score == pytest.approx(1 / (RRF_K + 1))

    assert by_id["vector-only"].vector_rank == 1
    assert by_id["vector-only"].keyword_rank is None
    assert by_id["vector-only"].fused_score == pytest.approx(1 / (RRF_K + 1))

    assert by_id["both"].keyword_rank == 2
    assert by_id["both"].vector_rank == 2
    assert by_id["both"].fused_score == pytest.approx(2 / (RRF_K + 2))


def test_limit_truncates_the_fused_ranking() -> None:
    keyword_results = [_chunk("chunk-a", rank=2.0), _chunk("chunk-b", rank=1.0)]
    vector_results = [_neighbor("chunk-a", distance=0.1), _neighbor("chunk-b", distance=0.2)]

    fused = fuse_rankings(keyword_results=keyword_results, vector_results=vector_results, limit=1)

    assert len(fused) == 1
    assert fused[0].chunk_id == "chunk-a"


def test_exact_ties_break_on_chunk_id_ascending() -> None:
    # Both rank #1 in their own (otherwise-empty-of-each-other) list --
    # each contributes the identical 1/(RRF_K + 1) score, a genuine tie
    # that only the chunk_id tiebreak (ADR-0022) can resolve.
    keyword_results = [_chunk("chunk-z", rank=1.0)]
    vector_results = [_neighbor("chunk-a", distance=0.1)]

    fused = fuse_rankings(keyword_results=keyword_results, vector_results=vector_results)

    assert fused[0].fused_score == pytest.approx(fused[1].fused_score)
    assert [result.chunk_id for result in fused] == ["chunk-a", "chunk-z"]


def test_empty_inputs_produce_an_empty_fused_ranking() -> None:
    assert fuse_rankings(keyword_results=[], vector_results=[]) == []
