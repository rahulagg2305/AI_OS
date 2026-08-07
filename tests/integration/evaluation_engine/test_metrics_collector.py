"""``SqlMetricsCollector``, end to end, against real Postgres
(ADR-0015 — no mocking the database). Proves the real, multi-table
read this component exists for: given a real, completed workflow
instance with real `total_tokens`/`total_cost_usd`, real
`workflow_steps` rows (including a real retry), and real
`gate_results` rows (including a real failure), `collect()` writes
five real, correctly-valued `evaluation.metrics` rows.

**No real production caller composes this yet** — see
`ai_os_kernel.evaluation_engine.metrics_collector`'s own module
docstring for the disclosed, real `experiment_runs` foreign-key
blocker this file works around the same way every real caller
eventually will: a hand-seeded, schema-valid `experiments`/
`experiment_runs` row, mirroring
`tests/integration/workflow_engine/test_run_manifest_recorder.py`'s
own established "real Postgres, synthetic but schema-valid rows"
convention for a component with no real end-to-end production trigger
yet.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.evaluation_engine.metrics_collector import (
    MetricsCollectionError,
    SqlMetricsCollector,
)
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.evaluation_schema import experiment_runs, experiments, gate_results
from ai_os_kernel.persistence.evaluation_schema import metrics as metrics_table
from ai_os_kernel.persistence.schema import workflow_instances, workflow_steps
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

_DEFINITION_ID = "test.metrics-collector-workflow"
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


async def _seed_workflow_definition(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                "INSERT INTO catalog.workflow_definitions "
                "(definition_id, version, pack_id, graph, inputs_schema, "
                " outputs_schema, declared_permissions, validated_at) "
                "VALUES (:definition_id, :version, 'test-pack', '{}'::jsonb, "
                " '{}'::jsonb, '{}'::jsonb, '[]'::jsonb, now()) "
                "ON CONFLICT (definition_id, version) DO NOTHING"
            ),
            {"definition_id": _DEFINITION_ID, "version": _DEFINITION_VERSION},
        )


def _step_row(
    *, step_id: str, workflow_id: str, step_name: str, attempt: int, status: str
) -> dict[str, object]:
    return {
        "step_id": step_id,
        "workflow_id": workflow_id,
        "step_name": step_name,
        "step_type": "agent",
        "status": status,
        "attempt": attempt,
        "agent_id": None,
        "tool_id": None,
        "prompt_id": None,
        "prompt_version": None,
        "model_alias": None,
        "inputs": {},
        "outputs": {"content": "real output"},
        "error": None,
        "idempotency_key": f"idem_{step_id}",
        "usage": {},
        "started_at": sa.func.now(),
        "completed_at": sa.func.now(),
    }


def test_collect_writes_five_real_metrics_rows_for_a_real_completed_workflow(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            await _seed_workflow_definition(engine)

            instance = await SqlWorkflowInstanceRepository(engine).create(
                definition_id=_DEFINITION_ID,
                definition_version=_DEFINITION_VERSION,
                inputs={},
                principal_id="test-principal",
            )
            workflow_id = instance.workflow_id

            created_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
            completed_at = created_at + timedelta(seconds=42)

            async with engine.begin() as connection:
                # Real, non-default aggregate columns — the LLM
                # Gateway's own per-workflow budget enforcement is what
                # genuinely maintains these in production; set directly
                # here since this test's own scope is the collector's
                # own read, not that enforcement mechanism.
                await connection.execute(
                    sa.update(workflow_instances)
                    .where(workflow_instances.c.workflow_id == workflow_id)
                    .values(
                        total_tokens=1500,
                        total_cost_usd=Decimal("0.045000"),
                        created_at=created_at,
                        completed_at=completed_at,
                    )
                )

                # One step that succeeded on its first attempt, and one
                # that genuinely retried once before succeeding — two
                # real, distinct rows for the retried step, the same
                # real shape gate_result_recorder.py's own docstring
                # already documents.
                await connection.execute(
                    sa.insert(workflow_steps).values(
                        _step_row(
                            step_id="stp_first",
                            workflow_id=workflow_id,
                            step_name="first",
                            attempt=1,
                            status="completed",
                        )
                    )
                )
                await connection.execute(
                    sa.insert(workflow_steps).values(
                        _step_row(
                            step_id="stp_retry_1",
                            workflow_id=workflow_id,
                            step_name="retried",
                            attempt=1,
                            status="failed",
                        )
                    )
                )
                await connection.execute(
                    sa.insert(workflow_steps).values(
                        _step_row(
                            step_id="stp_retry_2",
                            workflow_id=workflow_id,
                            step_name="retried",
                            attempt=2,
                            status="completed",
                        )
                    )
                )

                # One passing gate and one genuinely failed gate.
                await connection.execute(
                    sa.insert(gate_results).values(
                        result_id="gr_pass",
                        workflow_id=workflow_id,
                        step_id="quality-gate-pass",
                        gate_id="quality-gate-pass",
                        gate_version="1.0.0",
                        status="completed",
                        severity="blocking",
                        metrics={"attempt": 1},
                        messages=[],
                        duration_ms=0,
                    )
                )
                await connection.execute(
                    sa.insert(gate_results).values(
                        result_id="gr_fail",
                        workflow_id=workflow_id,
                        step_id="quality-gate-fail",
                        gate_id="quality-gate-fail",
                        gate_version="1.0.0",
                        status="failed",
                        severity="blocking",
                        metrics={"attempt": 1},
                        messages=["genuine failure"],
                        duration_ms=0,
                    )
                )

                # The real, disclosed blocker this collector's own
                # module docstring names: a real experiments/
                # experiment_runs row, hand-seeded (no Benchmarking
                # Pack exists to produce one for real yet).
                await connection.execute(
                    sa.insert(experiments).values(
                        experiment_id="exp_test",
                        name="test experiment",
                        description="a hand-seeded experiment for this real proof",
                        definition_id=_DEFINITION_ID,
                        definition_version=_DEFINITION_VERSION,
                        variables={},
                        pinned_conditions={},
                        runs_per_variant=1,
                        status="running",
                        created_by="test-principal",
                    )
                )
                await connection.execute(
                    sa.insert(experiment_runs).values(
                        run_id="run_test",
                        experiment_id="exp_test",
                        workflow_id=workflow_id,
                        variant_key="control",
                        model_alias="coding-strong",
                        resolved_model_id="claude-opus-5",
                        replicate_index=0,
                        served_from_cache=False,
                        status="completed",
                    )
                )

            collector = SqlMetricsCollector(engine)
            await collector.collect(workflow_id=workflow_id, run_id="run_test")

            async with engine.connect() as connection:
                rows = (
                    (
                        await connection.execute(
                            sa.select(metrics_table).where(
                                metrics_table.c.workflow_id == workflow_id
                            )
                        )
                    )
                    .mappings()
                    .all()
                )

            by_name = {row["metric_name"]: row for row in rows}
            assert len(rows) == 5
            assert by_name["aios.workflow.total_tokens"]["metric_value"] == 1500
            assert by_name["aios.workflow.total_tokens"]["unit"] == "tokens"
            assert by_name["aios.workflow.total_cost_usd"]["metric_value"] == Decimal("0.045000")
            assert by_name["aios.workflow.duration_seconds"]["metric_value"] == 42
            assert by_name["aios.workflow.gate_failures"]["metric_value"] == 1
            assert by_name["aios.workflow.step_retries"]["metric_value"] == 1
            for row in rows:
                assert row["run_id"] == "run_test"
                assert row["source_component"] == "evaluation_engine.metrics_collector"
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_collect_raises_a_clear_error_for_an_unknown_workflow(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            collector = SqlMetricsCollector(engine)
            with pytest.raises(MetricsCollectionError, match="does-not-exist"):
                await collector.collect(workflow_id="wf_does-not-exist", run_id="run_test")
        finally:
            await engine.dispose()

    asyncio.run(_run())
