"""Real, Postgres-backed proof of the Impact Analyzer's real query
(``P04-S02-M16-T02``) — the first recursive CTE in this codebase.

Every test builds its own, uniquely-suffixed artifact graph (never
sharing rows with another test in this module-scoped Postgres,
mirroring ``test_link_writer.py``'s own discipline).
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
from ai_os_kernel.traceability_engine.impact_query import find_affected_artifacts
from ai_os_kernel.traceability_engine.link_writer import SqlTraceLinkWriter
from ai_os_kernel.traceability_engine.models import ArtifactInput
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"


def _artifact(kind: str, suffix: str) -> ArtifactInput:
    return ArtifactInput(
        artifact_type=kind,
        external_id=f"{kind}-{suffix}",
        title=f"{kind} {suffix}",
        location=f"docs/{kind}/{suffix}.md",
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


def test_a_direct_link_makes_both_endpoints_mutually_reachable(database_url: str) -> None:
    """Bidirectional traversal, proven directly: the module is the
    *source* of the link, yet the requirement (its target) is found
    from the module's own impact query, and vice versa."""

    async def _run() -> None:
        engine: AsyncEngine = build_engine(database_url)
        try:
            writer = SqlTraceLinkWriter(engine)
            module = _artifact("module", "direct")
            requirement = _artifact("requirement", "direct")

            await writer.record_link(
                source=module,
                relationship="implements",
                target=requirement,
                confidence="confirmed",
                created_by="test",
                created_by_type="process",
            )

            from_module = await find_affected_artifacts(
                engine, artifact_type="module", external_id=module.external_id
            )
            from_requirement = await find_affected_artifacts(
                engine, artifact_type="requirement", external_id=requirement.external_id
            )

            assert {a.external_id for a in from_module} == {requirement.external_id}
            assert {a.external_id for a in from_requirement} == {module.external_id}
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_impact_is_transitive_across_a_real_multi_hop_chain(database_url: str) -> None:
    """requirement --verifies-- test_case, module --implements--> requirement:
    changing the module transitively reaches the test case two hops
    away, not only the requirement one hop away."""

    async def _run() -> None:
        engine: AsyncEngine = build_engine(database_url)
        try:
            writer = SqlTraceLinkWriter(engine)
            module = _artifact("module", "chain")
            requirement = _artifact("requirement", "chain")
            test_case = _artifact("test_case", "chain")

            await writer.record_link(
                source=module,
                relationship="implements",
                target=requirement,
                confidence="confirmed",
                created_by="test",
                created_by_type="process",
            )
            await writer.record_link(
                source=test_case,
                relationship="verifies",
                target=requirement,
                confidence="confirmed",
                created_by="test",
                created_by_type="process",
            )

            affected = await find_affected_artifacts(
                engine, artifact_type="module", external_id=module.external_id
            )

            assert {a.external_id for a in affected} == {
                requirement.external_id,
                test_case.external_id,
            }
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_real_cycle_terminates_and_does_not_duplicate_results(database_url: str) -> None:
    """A --affects--> B --affects--> A: a real cycle. The query must
    terminate (proving the cycle guard is real, not merely claimed)
    and report each real artifact exactly once."""

    async def _run() -> None:
        engine: AsyncEngine = build_engine(database_url)
        try:
            writer = SqlTraceLinkWriter(engine)
            a = _artifact("module", "cycle-a")
            b = _artifact("module", "cycle-b")

            await writer.record_link(
                source=a,
                relationship="affects",
                target=b,
                confidence="confirmed",
                created_by="test",
                created_by_type="process",
            )
            await writer.record_link(
                source=b,
                relationship="affects",
                target=a,
                confidence="confirmed",
                created_by="test",
                created_by_type="process",
            )

            affected = await asyncio.wait_for(
                find_affected_artifacts(engine, artifact_type="module", external_id=a.external_id),
                timeout=10.0,
            )

            assert [artifact.external_id for artifact in affected] == [b.external_id]
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_closed_link_is_not_traversed(database_url: str) -> None:
    async def _run() -> None:
        engine: AsyncEngine = build_engine(database_url)
        try:
            writer = SqlTraceLinkWriter(engine)
            module = _artifact("module", "closed")
            requirement = _artifact("requirement", "closed")

            link = await writer.record_link(
                source=module,
                relationship="implements",
                target=requirement,
                confidence="confirmed",
                created_by="test",
                created_by_type="process",
            )
            await writer.close_link(link_id=link.link_id)

            affected = await find_affected_artifacts(
                engine, artifact_type="module", external_id=module.external_id
            )

            assert affected == []
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_an_artifact_with_no_links_has_no_affected_artifacts(database_url: str) -> None:
    async def _run() -> None:
        engine: AsyncEngine = build_engine(database_url)
        try:
            affected = await find_affected_artifacts(
                engine, artifact_type="module", external_id="module-with-no-links-at-all"
            )
            assert affected == []
        finally:
            await engine.dispose()

    asyncio.run(_run())
