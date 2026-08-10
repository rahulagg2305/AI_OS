"""``SqlGateResultRecorder.list_all`` against a real Postgres container
(ADR-0015 — no mocking the database). Backs ``GET /api/v1/gates/results``
(added 2026-08-10, `P06-S01-M36-T04`). ``record()`` itself is already
proven end to end by ``tests/integration/workflow_engine/
test_delivery_pipeline.py`` — this file covers the read side only.
"""

import asyncio
import os
from collections.abc import Generator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.evaluation_schema import gate_results
from ai_os_kernel.workflow_engine.gate_result_recorder import SqlGateResultRecorder
from ai_os_kernel.workflow_engine.ids import new_gate_result_id
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
_DEFINITION_ID = "se.product_creation"
_DEFINITION_VERSION = "1.0.0"


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


async def _seed_gate_result(
    database_url: str,
    *,
    workflow_id: str,
    status: str = "completed",
    severity: str = "blocking",
) -> str:
    """A direct insert, not `SqlGateResultRecorder.record()` — that
    writer needs a real, resolved `WorkflowStepRecord` this file's own
    read-side tests have no need to build; `record()`'s own real
    correctness is already proven by `test_delivery_pipeline.py`."""
    result_id = new_gate_result_id()
    engine = build_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                sa.insert(gate_results).values(
                    result_id=result_id,
                    workflow_id=workflow_id,
                    step_id="test-gate-step",
                    gate_id="test-gate-step",
                    gate_version="1.0.0",
                    status=status,
                    severity=severity,
                    metrics={"attempt": 1},
                    messages=[],
                    duration_ms=0,
                )
            )
    finally:
        await engine.dispose()
    return result_id


async def _create_real_instance(database_url: str) -> str:
    engine = build_engine(database_url)
    try:
        instance = await SqlWorkflowInstanceRepository(engine).create(
            definition_id=_DEFINITION_ID,
            definition_version=_DEFINITION_VERSION,
            inputs={},
            principal_id="test-principal",
        )
        return instance.workflow_id
    finally:
        await engine.dispose()


def test_list_all_returns_a_real_gate_result(database_url: str) -> None:
    async def _run() -> None:
        workflow_id = await _create_real_instance(database_url)
        result_id = await _seed_gate_result(database_url, workflow_id=workflow_id)

        engine = build_engine(database_url)
        try:
            results = await SqlGateResultRecorder(engine).list_all(limit=50)
            matching = next(r for r in results if r.result_id == result_id)
            assert matching.workflow_id == workflow_id
            assert matching.status == "completed"
            assert matching.severity == "blocking"
            assert matching.metrics == {"attempt": 1}
            assert matching.messages == []
            assert matching.duration_ms == 0
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_list_all_filters_by_workflow_id(database_url: str) -> None:
    async def _run() -> None:
        first_workflow_id = await _create_real_instance(database_url)
        second_workflow_id = await _create_real_instance(database_url)
        first_result_id = await _seed_gate_result(database_url, workflow_id=first_workflow_id)
        await _seed_gate_result(database_url, workflow_id=second_workflow_id)

        engine = build_engine(database_url)
        try:
            results = await SqlGateResultRecorder(engine).list_all(
                workflow_id=first_workflow_id, limit=50
            )
            assert {r.result_id for r in results} == {first_result_id}
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_list_all_paginates_newest_first_with_a_real_keyset_cursor(database_url: str) -> None:
    async def _run() -> None:
        workflow_id = await _create_real_instance(database_url)
        result_ids = [
            await _seed_gate_result(database_url, workflow_id=workflow_id) for _ in range(3)
        ]

        engine = build_engine(database_url)
        try:
            recorder = SqlGateResultRecorder(engine)
            first_page = await recorder.list_all(workflow_id=workflow_id, limit=2)
            assert [r.result_id for r in first_page] == sorted(result_ids, reverse=True)[:2]

            second_page = await recorder.list_all(
                workflow_id=workflow_id, limit=2, before=first_page[-1].result_id
            )
            # Real keyset pagination, not offset in disguise: the two
            # pages share no row, and together cover every real row.
            first_ids = {r.result_id for r in first_page}
            second_ids = {r.result_id for r in second_page}
            assert first_ids.isdisjoint(second_ids)
            assert set(result_ids) == first_ids | second_ids
        finally:
            await engine.dispose()

    asyncio.run(_run())
