"""Real, Postgres-backed proof of the ``trace.links`` writer
(``P04-S02-M16-T01``) — this table's first real writer.

The central proof this file exists for: a real requirement (modelled
on FR-019, the ticket's own literal Goal) and a real module/test case
each resolve to the identical ``artifact_key`` no matter which of two
independent calls creates them, closing the "which artifact am I even
linking to" gap a random id would have left open.

Every test builds its own, uniquely-suffixed artifacts (never sharing
one module-scoped Postgres' rows with another test in this file,
mirroring ``test_role_administration.py``'s own "distinct target per
test" discipline) — each assertion is genuinely caused by that test's
own actions, not a previous test's leftover state. Real Postgres via
testcontainers (ADR-0015).
"""

import asyncio
import os
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.trace_schema import artifacts
from ai_os_kernel.traceability_engine.errors import (
    TraceabilityValidationError,
    TraceLinkNotFoundError,
)
from ai_os_kernel.traceability_engine.ids import compute_artifact_key
from ai_os_kernel.traceability_engine.link_writer import SqlTraceLinkWriter
from ai_os_kernel.traceability_engine.models import ArtifactInput
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"


def _requirement(suffix: str) -> ArtifactInput:
    return ArtifactInput(
        artifact_type="requirement",
        external_id=f"FR-019-{suffix}",
        title="Traceability links",
        location="docs/02_requirements/functional/functional_requirements.md",
        version="1.0",
    )


def _module(suffix: str) -> ArtifactInput:
    return ArtifactInput(
        artifact_type="module",
        external_id=f"traceability_engine.link_writer-{suffix}",
        title="trace.links writer",
        location="kernel/src/ai_os_kernel/traceability_engine/link_writer.py",
        version="1.0",
    )


def _test_case(suffix: str) -> ArtifactInput:
    return ArtifactInput(
        artifact_type="test_case",
        external_id=f"test_link_writer-{suffix}",
        title="Real, Postgres-backed proof of the trace.links writer",
        location="tests/integration/traceability_engine/test_link_writer.py",
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


def test_recording_a_link_upserts_both_artifacts_with_deterministic_keys(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine: AsyncEngine = build_engine(database_url)
        try:
            writer = SqlTraceLinkWriter(engine)
            module = _module("recording")
            requirement = _requirement("recording")

            link = await writer.record_link(
                source=module,
                relationship="implements",
                target=requirement,
                confidence="confirmed",
                created_by="test_link_writer",
                created_by_type="process",
            )

            expected_source_key = compute_artifact_key(
                artifact_type="module", external_id=module.external_id
            )
            expected_target_key = compute_artifact_key(
                artifact_type="requirement", external_id=requirement.external_id
            )
            assert link.source_key == expected_source_key
            assert link.target_key == expected_target_key
            assert link.relationship == "implements"
            assert link.closed_at is None

            async with engine.connect() as connection:
                rows = (
                    (
                        await connection.execute(
                            select(artifacts).where(
                                artifacts.c.artifact_key.in_(
                                    [expected_source_key, expected_target_key]
                                )
                            )
                        )
                    )
                    .mappings()
                    .all()
                )
            by_key = {row["artifact_key"]: row for row in rows}
            assert by_key[expected_target_key]["title"] == "Traceability links"
            assert by_key[expected_target_key]["external_id"] == requirement.external_id
            assert by_key[expected_source_key]["artifact_type"] == "module"
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_two_independent_calls_naming_the_same_real_artifact_land_on_one_row(
    database_url: str,
) -> None:
    """The real proof this ticket's own design decision exists for: no
    shared state between these two calls beyond the real database —
    each independently computes the identical key for the same real
    requirement."""

    async def _run() -> None:
        engine: AsyncEngine = build_engine(database_url)
        try:
            writer = SqlTraceLinkWriter(engine)
            requirement = _requirement("shared")

            first_link = await writer.record_link(
                source=_module("shared"),
                relationship="implements",
                target=requirement,
                confidence="confirmed",
                created_by="agent-a",
                created_by_type="agent",
            )
            second_link = await writer.record_link(
                source=_test_case("shared"),
                relationship="verifies",
                # A fresh ArtifactInput instance, same real identity —
                # proving the *key*, not object identity, is what
                # converges.
                target=_requirement("shared"),
                confidence="confirmed",
                created_by="agent-b",
                created_by_type="agent",
            )

            assert first_link.target_key == second_link.target_key

            async with engine.connect() as connection:
                requirement_rows = (
                    (
                        await connection.execute(
                            select(artifacts).where(
                                artifacts.c.artifact_key == first_link.target_key
                            )
                        )
                    )
                    .mappings()
                    .all()
                )
            assert len(requirement_rows) == 1
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_reasserting_an_already_open_identical_link_is_idempotent_not_an_error(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine: AsyncEngine = build_engine(database_url)
        try:
            writer = SqlTraceLinkWriter(engine)
            module = _module("idempotent")
            requirement = _requirement("idempotent")

            first = await writer.record_link(
                source=module,
                relationship="implements",
                target=requirement,
                confidence="confirmed",
                created_by="agent-a",
                created_by_type="agent",
            )
            second = await writer.record_link(
                source=module,
                relationship="implements",
                target=requirement,
                confidence="confirmed",
                created_by="agent-a",
                created_by_type="agent",
            )

            assert first.link_id == second.link_id
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_upserting_an_artifact_again_refreshes_its_real_metadata(database_url: str) -> None:
    async def _run() -> None:
        engine: AsyncEngine = build_engine(database_url)
        try:
            writer = SqlTraceLinkWriter(engine)
            module = _module("refresh")
            requirement = _requirement("refresh")
            updated_requirement = requirement.model_copy(update={"title": "Traceability links, v2"})

            await writer.record_link(
                source=module,
                relationship="implements",
                target=requirement,
                confidence="confirmed",
                created_by="agent-a",
                created_by_type="agent",
            )
            link = await writer.record_link(
                source=module,
                relationship="implements",
                target=updated_requirement,
                confidence="confirmed",
                created_by="agent-a",
                created_by_type="agent",
            )

            async with engine.connect() as connection:
                row = (
                    (
                        await connection.execute(
                            select(artifacts).where(artifacts.c.artifact_key == link.target_key)
                        )
                    )
                    .mappings()
                    .one()
                )
            assert row["title"] == "Traceability links, v2"
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_closing_a_real_link_sets_closed_at_and_a_second_close_is_refused(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine: AsyncEngine = build_engine(database_url)
        try:
            writer = SqlTraceLinkWriter(engine)
            link = await writer.record_link(
                source=_module("close"),
                relationship="implements",
                target=_requirement("close"),
                confidence="confirmed",
                created_by="agent-a",
                created_by_type="agent",
            )

            closed = await writer.close_link(link_id=link.link_id)
            assert closed.closed_at is not None

            with pytest.raises(TraceLinkNotFoundError):
                await writer.close_link(link_id=link.link_id)
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_closing_a_nonexistent_link_is_refused(database_url: str) -> None:
    async def _run() -> None:
        engine: AsyncEngine = build_engine(database_url)
        try:
            writer = SqlTraceLinkWriter(engine)
            with pytest.raises(TraceLinkNotFoundError):
                await writer.close_link(link_id="link_does_not_exist")
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_reasserting_after_a_close_creates_a_genuinely_new_open_link(
    database_url: str,
) -> None:
    """data_model.md §8's own partial unique index scopes uniqueness
    to ``WHERE closed_at IS NULL`` specifically so a closed triple can
    be re-asserted later — proven here, not merely cited."""

    async def _run() -> None:
        engine: AsyncEngine = build_engine(database_url)
        try:
            writer = SqlTraceLinkWriter(engine)
            module = _module("reopen")
            requirement = _requirement("reopen")

            first = await writer.record_link(
                source=module,
                relationship="implements",
                target=requirement,
                confidence="confirmed",
                created_by="agent-a",
                created_by_type="agent",
            )
            await writer.close_link(link_id=first.link_id)

            second = await writer.record_link(
                source=module,
                relationship="implements",
                target=requirement,
                confidence="confirmed",
                created_by="agent-a",
                created_by_type="agent",
            )

            assert second.link_id != first.link_id
            assert second.closed_at is None
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_an_invalid_relationship_is_refused_before_any_real_database_call(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine: AsyncEngine = build_engine(database_url)
        try:
            writer = SqlTraceLinkWriter(engine)
            requirement = _requirement("invalid-relationship")

            with pytest.raises(TraceabilityValidationError, match="relationship"):
                await writer.record_link(
                    source=_module("invalid-relationship"),
                    relationship="not-a-real-relationship",
                    target=requirement,
                    confidence="confirmed",
                    created_by="agent-a",
                    created_by_type="agent",
                )

            async with engine.connect() as connection:
                rows = (
                    (
                        await connection.execute(
                            select(artifacts).where(
                                artifacts.c.artifact_key
                                == compute_artifact_key(
                                    artifact_type="requirement",
                                    external_id=requirement.external_id,
                                )
                            )
                        )
                    )
                    .mappings()
                    .all()
                )
            # Refused before any upsert — no real row was ever written.
            assert rows == []
        finally:
            await engine.dispose()

    asyncio.run(_run())
