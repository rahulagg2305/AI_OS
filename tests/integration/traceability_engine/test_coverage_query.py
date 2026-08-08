"""Real, Postgres-backed proof of the Coverage Analyzer's real query
(``P04-S02-M16-T03``, FR-115).

Every test builds its own, uniquely-suffixed artifacts (never sharing
rows with another test in this module-scoped Postgres, mirroring
``test_link_writer.py``'s own discipline).
"""

import asyncio
import os
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.traceability_engine.coverage_query import find_uncovered_requirements
from ai_os_kernel.traceability_engine.link_writer import SqlTraceLinkWriter
from ai_os_kernel.traceability_engine.models import ArtifactInput
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"


def _requirement(suffix: str) -> ArtifactInput:
    return ArtifactInput(
        artifact_type="requirement",
        external_id=f"FR-{suffix}",
        title=f"Requirement {suffix}",
        location="docs/02_requirements/functional/functional_requirements.md",
        version="1.0",
    )


def _test_case(suffix: str) -> ArtifactInput:
    return ArtifactInput(
        artifact_type="test_case",
        external_id=f"test-{suffix}",
        title=f"Test {suffix}",
        location="tests/",
        version="1.0",
    )


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


def test_a_requirement_with_a_confirmed_verifying_link_is_not_reported(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine: AsyncEngine = build_engine(database_url)
        try:
            writer = SqlTraceLinkWriter(engine)
            requirement = _requirement("confirmed-covered")

            await writer.record_link(
                source=_test_case("confirmed-covered"),
                relationship="verifies",
                target=requirement,
                confidence="confirmed",
                created_by="test",
                created_by_type="process",
            )

            uncovered = await find_uncovered_requirements(engine)
            assert requirement.external_id not in {a.external_id for a in uncovered}
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_requirement_with_only_a_provisional_verifying_link_is_still_reported(
    database_url: str,
) -> None:
    """The real design decision this ticket made: only ``confirmed``
    confidence discharges the coverage obligation."""

    async def _run() -> None:
        engine: AsyncEngine = build_engine(database_url)
        try:
            writer = SqlTraceLinkWriter(engine)
            requirement = _requirement("provisional-only")

            await writer.record_link(
                source=_test_case("provisional-only"),
                relationship="verifies",
                target=requirement,
                confidence="provisional",
                created_by="test",
                created_by_type="process",
            )

            uncovered = await find_uncovered_requirements(engine)
            assert requirement.external_id in {a.external_id for a in uncovered}
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_requirement_with_no_verifying_link_at_all_is_reported(database_url: str) -> None:
    async def _run() -> None:
        engine: AsyncEngine = build_engine(database_url)
        try:
            writer = SqlTraceLinkWriter(engine)
            requirement = _requirement("no-verifies-link")

            # A real artifact row needs at least one real link to
            # exist at all (the writer only upserts as a side effect of
            # record_link) — a non-"verifies" relationship, so this
            # requirement genuinely has no verifying link pointing at
            # it, only an unrelated one.
            await writer.record_link(
                source=requirement,
                relationship="realizes",
                target=_test_case("no-verifies-link-other-endpoint"),
                confidence="confirmed",
                created_by="test",
                created_by_type="process",
            )

            uncovered = await find_uncovered_requirements(engine)
            assert requirement.external_id in {a.external_id for a in uncovered}
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_verifying_link_for_a_different_requirement_does_not_cover_this_one(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine: AsyncEngine = build_engine(database_url)
        try:
            writer = SqlTraceLinkWriter(engine)
            covered = _requirement("other-covered")
            uncovered_requirement = _requirement("other-uncovered")

            await writer.record_link(
                source=_test_case("other"),
                relationship="verifies",
                target=covered,
                confidence="confirmed",
                created_by="test",
                created_by_type="process",
            )
            # uncovered_requirement is registered as an artifact via an
            # unrelated link, but never verified.
            await writer.record_link(
                source=uncovered_requirement,
                relationship="realizes",
                target=_test_case("other-anchor"),
                confidence="confirmed",
                created_by="test",
                created_by_type="process",
            )

            uncovered = {a.external_id for a in await find_uncovered_requirements(engine)}
            assert covered.external_id not in uncovered
            assert uncovered_requirement.external_id in uncovered
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_closed_confirmed_verifying_link_no_longer_counts_as_coverage(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine: AsyncEngine = build_engine(database_url)
        try:
            writer = SqlTraceLinkWriter(engine)
            requirement = _requirement("closed-link")

            link = await writer.record_link(
                source=_test_case("closed-link"),
                relationship="verifies",
                target=requirement,
                confidence="confirmed",
                created_by="test",
                created_by_type="process",
            )
            await writer.close_link(link_id=link.link_id)

            uncovered = await find_uncovered_requirements(engine)
            assert requirement.external_id in {a.external_id for a in uncovered}
        finally:
            await engine.dispose()

    asyncio.run(_run())
