"""SqlKeywordSearcher against a real Postgres container (ADR-0015 — no
mocking the database). Seeds real ``knowledge.documents``/``knowledge.
chunks`` rows through the previous step's own ``SqlKnowledgeWriter``
(not hand-written SQL), then proves: matching chunks are found and
ranked by relevance, non-matching chunks are excluded, ``limit`` is
respected (including its documented default), English stemming agrees
between ``content_tsv``'s own generation and this reader's query parsing,
tied ranks are ordered deterministically, and blank/invalid input is
rejected before any query runs.
"""

import asyncio
import os
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.knowledge_keyword_search import (
    _DEFAULT_LIMIT,
    KeywordSearchError,
    SqlKeywordSearcher,
)
from ai_os_kernel.persistence.knowledge_writer import ChunkInput, SqlKnowledgeWriter
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"


@pytest.fixture(scope="module")
def database_url() -> Generator[str, None, None]:
    with postgres_container() as postgres:
        url = postgres.get_connection_url()
        previous = os.environ.get("AIOS_DATABASE_URL")
        os.environ["AIOS_DATABASE_URL"] = url
        try:
            command.upgrade(Config(str(ALEMBIC_INI)), "head")
            yield url
        finally:
            if previous is None:
                os.environ.pop("AIOS_DATABASE_URL", None)
            else:
                os.environ["AIOS_DATABASE_URL"] = previous


def _chunk(content: str) -> ChunkInput:
    return ChunkInput(
        content=content, token_count=len(content.split()), chunk_strategy_version="v1"
    )


async def _seed_document(database_url: str, *, source_uri: str, chunk_contents: list[str]) -> str:
    engine = build_engine(database_url)
    try:
        writer = SqlKnowledgeWriter(engine)
        record = await writer.write_document(
            source_uri=source_uri,
            content_hash="sha256:" + "0" * 64,
            media_type="text/markdown",
            trust="trusted",
            chunks=[_chunk(content) for content in chunk_contents],
        )
        return record.document_id
    finally:
        await engine.dispose()


def test_search_finds_a_matching_chunk_and_returns_the_documented_fields(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            document_id = await _seed_document(
                database_url,
                source_uri="https://example.com/kernel.md",
                chunk_contents=["The kernel architecture document describes the runtime core."],
            )

            searcher = SqlKeywordSearcher(engine)
            results = await searcher.search(query="kernel architecture")

            assert len(results) == 1
            result = results[0]
            assert result.document_id == document_id
            assert result.chunk_id.startswith("chunk_")
            assert result.content == "The kernel architecture document describes the runtime core."
            assert result.rank > 0.0
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_search_ranks_more_relevant_chunks_first(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            await _seed_document(
                database_url,
                source_uri="https://example.com/rank-low.md",
                chunk_contents=["A single mention of retrieval appears here."],
            )
            await _seed_document(
                database_url,
                source_uri="https://example.com/rank-high.md",
                chunk_contents=["Retrieval retrieval retrieval: this chunk is about retrieval."],
            )

            searcher = SqlKeywordSearcher(engine)
            results = await searcher.search(query="retrieval", limit=10)

            matching = [r for r in results if "retrieval" in r.content.lower()]
            assert len(matching) == 2
            assert matching[0].rank >= matching[1].rank
            assert "retrieval retrieval retrieval" in matching[0].content.lower()
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_search_excludes_non_matching_chunks(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            await _seed_document(
                database_url,
                source_uri="https://example.com/unrelated.md",
                chunk_contents=["This chunk discusses gardening and unrelated topics entirely."],
            )

            searcher = SqlKeywordSearcher(engine)
            results = await searcher.search(query="quantum cryptography nonsense term")

            assert results == []
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_search_respects_an_explicit_limit(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            await _seed_document(
                database_url,
                source_uri="https://example.com/many-matches.md",
                chunk_contents=[
                    f"Widget occurrence number {i} in this document." for i in range(5)
                ],
            )

            searcher = SqlKeywordSearcher(engine)
            results = await searcher.search(query="widget", limit=2)

            assert len(results) == 2
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_search_defaults_to_the_documented_default_limit(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            await _seed_document(
                database_url,
                source_uri="https://example.com/default-limit.md",
                chunk_contents=[
                    f"Gadget occurrence number {i} appears here." for i in range(_DEFAULT_LIMIT + 5)
                ],
            )

            searcher = SqlKeywordSearcher(engine)
            results = await searcher.search(query="gadget")

            assert len(results) == _DEFAULT_LIMIT
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_search_matches_using_the_same_english_configuration_as_content_tsv(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            await _seed_document(
                database_url,
                source_uri="https://example.com/stemming.md",
                chunk_contents=["The system requires one technical document to proceed."],
            )

            searcher = SqlKeywordSearcher(engine)
            # The plural query "documents" should still match the singular
            # "document" in the seeded content, via English stemming —
            # proving content_tsv's own generation and this query's
            # parsing genuinely agree on the 'english' configuration,
            # rather than each silently using a different one.
            results = await searcher.search(query="documents")

            assert any("document" in r.content.lower() for r in results)
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_search_orders_tied_ranks_deterministically(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            await _seed_document(
                database_url,
                source_uri="https://example.com/tie-1.md",
                chunk_contents=["Unique tiebreak phrase appears exactly once."],
            )
            await _seed_document(
                database_url,
                source_uri="https://example.com/tie-2.md",
                chunk_contents=["Unique tiebreak phrase appears exactly once."],
            )

            searcher = SqlKeywordSearcher(engine)
            first_call = await searcher.search(query="tiebreak")
            second_call = await searcher.search(query="tiebreak")

            assert [r.chunk_id for r in first_call] == [r.chunk_id for r in second_call]
            assert [r.chunk_id for r in first_call] == sorted(r.chunk_id for r in first_call)
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_search_rejects_a_blank_query(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            searcher = SqlKeywordSearcher(engine)
            with pytest.raises(KeywordSearchError, match="must not be blank"):
                await searcher.search(query="   ")
        finally:
            await engine.dispose()

    asyncio.run(_run())


@pytest.mark.parametrize("limit", [0, -1])
def test_search_rejects_a_non_positive_limit(database_url: str, limit: int) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            searcher = SqlKeywordSearcher(engine)
            with pytest.raises(KeywordSearchError, match="limit must be positive"):
                await searcher.search(query="anything", limit=limit)
        finally:
            await engine.dispose()

    asyncio.run(_run())
