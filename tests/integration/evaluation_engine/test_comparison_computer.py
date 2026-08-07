"""`SqlComparisonComputer`, end to end, against real Postgres
(ADR-0015 — no mocking the database). Proves the real aggregation
this component exists for: mean and variance over a variant's own
real replicates, a cache-served run and an incomplete run both
genuinely excluded from the result, not silently averaged in.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Generator
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.evaluation_engine.comparison_computer import SqlComparisonComputer
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.evaluation_schema import experiment_runs, experiments, metrics
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

_DEFINITION_ID = "test.comparison-computer-workflow"
_DEFINITION_VERSION = "1.0.0"
_EXPERIMENT_ID = "exp_comparison_computer_test"
_METRIC_NAME = "aios.workflow.total_tokens"


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


async def _seed_workflow_definition_and_experiment(engine: AsyncEngine) -> None:
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
        await connection.execute(
            pg_insert(experiments)
            .values(
                experiment_id=_EXPERIMENT_ID,
                name="comparison computer test",
                description="a real, minimal experiment for this real proof",
                definition_id=_DEFINITION_ID,
                definition_version=_DEFINITION_VERSION,
                variables={},
                pinned_conditions={},
                runs_per_variant=3,
                status="running",
                created_by="test-principal",
            )
            .on_conflict_do_nothing(index_elements=["experiment_id"])
        )


async def _seed_replicate(
    engine: AsyncEngine,
    repository: SqlWorkflowInstanceRepository,
    *,
    run_id: str,
    variant_key: str,
    metric_value: Decimal,
    served_from_cache: bool = False,
    run_status: str = "completed",
) -> None:
    instance = await repository.create(
        definition_id=_DEFINITION_ID,
        definition_version=_DEFINITION_VERSION,
        inputs={},
        principal_id="test-principal",
    )
    async with engine.begin() as connection:
        await connection.execute(
            sa.insert(experiment_runs).values(
                run_id=run_id,
                experiment_id=_EXPERIMENT_ID,
                workflow_id=instance.workflow_id,
                variant_key=variant_key,
                model_alias="coding-strong",
                resolved_model_id="claude-opus-5",
                replicate_index=0,
                served_from_cache=served_from_cache,
                status=run_status,
            )
        )
        await connection.execute(
            sa.insert(metrics).values(
                metric_id=f"met_{run_id}",
                workflow_id=instance.workflow_id,
                run_id=run_id,
                metric_name=_METRIC_NAME,
                metric_value=metric_value,
                unit="tokens",
                source_component="test",
                recorded_at=sa.func.now(),
            )
        )


def test_compute_reports_mean_and_variance_excluding_cached_and_incomplete_runs(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            await _seed_workflow_definition_and_experiment(engine)
            repository = SqlWorkflowInstanceRepository(engine)

            # control: three real, completed, non-cached replicates —
            # 100, 200, 300 (mean 200, sample variance 10000).
            await _seed_replicate(
                engine,
                repository,
                run_id="run_control_1",
                variant_key="control",
                metric_value=Decimal("100"),
            )
            await _seed_replicate(
                engine,
                repository,
                run_id="run_control_2",
                variant_key="control",
                metric_value=Decimal("200"),
            )
            await _seed_replicate(
                engine,
                repository,
                run_id="run_control_3",
                variant_key="control",
                metric_value=Decimal("300"),
            )
            # A real, cache-served control run with an extreme value —
            # must be excluded, not averaged in.
            await _seed_replicate(
                engine,
                repository,
                run_id="run_control_cached",
                variant_key="control",
                metric_value=Decimal("999999"),
                served_from_cache=True,
            )
            # A real, still-running control run with an extreme value —
            # must be excluded, not averaged in.
            await _seed_replicate(
                engine,
                repository,
                run_id="run_control_incomplete",
                variant_key="control",
                metric_value=Decimal("888888"),
                run_status="running",
            )

            # treatment: three real, identical replicates — 50, 50, 50
            # (mean 50, sample variance 0).
            for index in range(3):
                await _seed_replicate(
                    engine,
                    repository,
                    run_id=f"run_treatment_{index}",
                    variant_key="treatment",
                    metric_value=Decimal("50"),
                )

            computer = SqlComparisonComputer(engine)
            comparison = await computer.compute(experiment_id=_EXPERIMENT_ID)

            assert comparison.experiment_id == _EXPERIMENT_ID
            by_variant = {variant.variant_key: variant for variant in comparison.variants}
            assert set(by_variant) == {"control", "treatment"}

            control_metric = by_variant["control"].metrics[0]
            assert control_metric.metric_name == _METRIC_NAME
            assert control_metric.unit == "tokens"
            assert control_metric.replicate_count == 3
            assert control_metric.mean == Decimal("200")
            assert control_metric.variance == Decimal("10000")

            treatment_metric = by_variant["treatment"].metrics[0]
            assert treatment_metric.replicate_count == 3
            assert treatment_metric.mean == Decimal("50")
            assert treatment_metric.variance == Decimal("0")
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_compute_reports_no_variance_for_a_single_real_replicate(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            await _seed_workflow_definition_and_experiment(engine)
            repository = SqlWorkflowInstanceRepository(engine)

            await _seed_replicate(
                engine,
                repository,
                run_id="run_solo",
                variant_key="solo",
                metric_value=Decimal("42"),
            )

            computer = SqlComparisonComputer(engine)
            comparison = await computer.compute(experiment_id=_EXPERIMENT_ID)

            solo_variant = next(v for v in comparison.variants if v.variant_key == "solo")
            solo_metric = solo_variant.metrics[0]
            assert solo_metric.replicate_count == 1
            assert solo_metric.mean == Decimal("42")
            assert solo_metric.variance is None
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_compute_returns_no_variants_for_an_experiment_with_no_real_runs(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            await _seed_workflow_definition_and_experiment(engine)

            computer = SqlComparisonComputer(engine)
            comparison = await computer.compute(experiment_id="exp_never_run")

            assert comparison.variants == []
        finally:
            await engine.dispose()

    asyncio.run(_run())
