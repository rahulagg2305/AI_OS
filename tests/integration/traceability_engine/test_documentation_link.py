"""Real, Postgres-backed proof of the delivery pipeline's own
``workflow_run --produced--> documentation`` traceability writer
(``record_documentation_traceability_link``, ``P04-S02-M16-T04``).

This is the domain-helper half of closing risk register R-018's own
worst-case "proven but idle" instance: the Traceability Engine's
writer/queries were all ``done`` yet nothing in production ever wrote a
link. This file proves the helper writes honest, correctly-shaped rows
against real Postgres; ``tests/integration/test_delivery_pipeline_route.py``
proves the real HTTP route + real bootstrap wiring genuinely calls it.

Real Postgres via testcontainers (ADR-0015) — no mocking the database.
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
from ai_os_kernel.persistence.trace_schema import artifacts, links
from ai_os_kernel.traceability_engine.ids import compute_artifact_key
from ai_os_kernel.traceability_engine.link_writer import SqlTraceLinkWriter
from ai_os_kernel.workflow_engine.delivery_pipeline import (
    DEFINITION_ID,
    record_documentation_traceability_link,
)
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

_DEFINITION_VERSION = "1.9.0"
_DOCUMENTATION_PATH = "workspace/docs/generated/greeting.md"


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


def test_helper_writes_the_real_workflow_run_produced_documentation_link(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine: AsyncEngine = build_engine(database_url)
        try:
            writer = SqlTraceLinkWriter(engine)
            workflow_id = "wf_produced_documentation_happy"

            link = await record_documentation_traceability_link(
                writer,
                workflow_id=workflow_id,
                definition_id=DEFINITION_ID,
                definition_version=_DEFINITION_VERSION,
                documentation_path=_DOCUMENTATION_PATH,
            )

            expected_source_key = compute_artifact_key(
                artifact_type="workflow_run", external_id=workflow_id
            )
            expected_target_key = compute_artifact_key(
                artifact_type="documentation", external_id=_DOCUMENTATION_PATH
            )
            assert link.source_key == expected_source_key
            assert link.target_key == expected_target_key
            assert link.relationship == "produced"
            assert link.confidence == "confirmed"
            assert link.created_by == DEFINITION_ID
            assert link.created_by_type == "process"
            assert link.closed_at is None

            # The two real trace.artifacts rows the link references — every
            # field genuinely derived from the run, none fabricated.
            async with engine.connect() as connection:
                artifact_rows = {
                    row.artifact_key: row
                    for row in (
                        await connection.execute(
                            select(artifacts).where(
                                artifacts.c.artifact_key.in_(
                                    [expected_source_key, expected_target_key]
                                )
                            )
                        )
                    ).all()
                }
            source = artifact_rows[expected_source_key]
            target = artifact_rows[expected_target_key]
            assert source.artifact_type == "workflow_run"
            assert source.external_id == workflow_id
            assert source.version == _DEFINITION_VERSION
            assert target.artifact_type == "documentation"
            assert target.external_id == _DOCUMENTATION_PATH
            assert target.location == _DOCUMENTATION_PATH
            assert target.version == _DEFINITION_VERSION
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_helper_is_idempotent_for_the_same_run(database_url: str) -> None:
    """The property the product-owner decision leans on: recording the
    link the moment documentation exists (paused at approval) and again
    later (a future resume-path completion) must converge on one row, not
    two — so a second call is safe, by design."""

    async def _run() -> None:
        engine: AsyncEngine = build_engine(database_url)
        try:
            writer = SqlTraceLinkWriter(engine)
            workflow_id = "wf_produced_documentation_idempotent"

            first = await record_documentation_traceability_link(
                writer,
                workflow_id=workflow_id,
                definition_id=DEFINITION_ID,
                definition_version=_DEFINITION_VERSION,
                documentation_path=_DOCUMENTATION_PATH,
            )
            second = await record_documentation_traceability_link(
                writer,
                workflow_id=workflow_id,
                definition_id=DEFINITION_ID,
                definition_version=_DEFINITION_VERSION,
                documentation_path=_DOCUMENTATION_PATH,
            )

            assert first.link_id == second.link_id
            source_key = compute_artifact_key(artifact_type="workflow_run", external_id=workflow_id)
            async with engine.connect() as connection:
                open_link_count = (
                    await connection.execute(
                        select(links).where(
                            links.c.source_key == source_key,
                            links.c.relationship == "produced",
                            links.c.closed_at.is_(None),
                        )
                    )
                ).all()
            assert len(open_link_count) == 1
        finally:
            await engine.dispose()

    asyncio.run(_run())
