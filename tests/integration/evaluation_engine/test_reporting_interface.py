"""The Reporting Interface (`P04-S01-M12-T08`), end to end, against
real Postgres (ADR-0015 — no mocking the database). Proves this
component's own real value: `EvaluationReportingInterface` composes
the real `SqlComparisonComputer` (no parallel mechanism — no second
way to compute a mean or a variance), and the `ComparisonReport` it
returns is genuinely queryable by variant, by variant-and-metric, and
— the one new capability — by metric across every variant at once.
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
from ai_os_kernel.evaluation_engine.reporting_interface import EvaluationReportingInterface
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.evaluation_schema import experiment_runs, experiments, metrics
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

_DEFINITION_ID = "test.reporting-interface-workflow"
_DEFINITION_VERSION = "1.0.0"
_EXPERIMENT_ID = "exp_reporting_interface_test"
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
                name="reporting interface test",
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
                served_from_cache=False,
                status="completed",
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


def test_get_report_exposes_the_real_computed_comparison_as_a_queryable_report(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            await _seed_workflow_definition_and_experiment(engine)
            repository = SqlWorkflowInstanceRepository(engine)

            # control: mean 200 over three real replicates.
            for index, value in enumerate(["100", "200", "300"]):
                await _seed_replicate(
                    engine,
                    repository,
                    run_id=f"run_control_{index}",
                    variant_key="control",
                    metric_value=Decimal(value),
                )
            # treatment: mean 50 over three real, identical replicates.
            for index in range(3):
                await _seed_replicate(
                    engine,
                    repository,
                    run_id=f"run_treatment_{index}",
                    variant_key="treatment",
                    metric_value=Decimal("50"),
                )

            reporting_interface = EvaluationReportingInterface(SqlComparisonComputer(engine))
            report = await reporting_interface.get_report(experiment_id=_EXPERIMENT_ID)

            assert report.experiment_id == _EXPERIMENT_ID
            assert set(report.variant_keys()) == {"control", "treatment"}

            control_variant = report.get_variant("control")
            assert control_variant is not None
            assert control_variant.variant_key == "control"

            assert report.get_variant("nonexistent_variant") is None

            control_metric = report.get_metric(variant_key="control", metric_name=_METRIC_NAME)
            assert control_metric is not None
            assert control_metric.mean == Decimal("200")

            assert (
                report.get_metric(variant_key="control", metric_name="nonexistent_metric") is None
            )
            assert (
                report.get_metric(variant_key="nonexistent_variant", metric_name=_METRIC_NAME)
                is None
            )

            # The one genuinely new capability: the real, cross-variant
            # pivot by metric name.
            by_variant = report.compare_by_metric(_METRIC_NAME)
            assert set(by_variant) == {"control", "treatment"}
            assert by_variant["control"].mean == Decimal("200")
            assert by_variant["treatment"].mean == Decimal("50")

            assert report.compare_by_metric("nonexistent_metric") == {}
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_get_report_returns_an_empty_but_real_report_for_an_experiment_with_no_runs(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            await _seed_workflow_definition_and_experiment(engine)

            reporting_interface = EvaluationReportingInterface(SqlComparisonComputer(engine))
            report = await reporting_interface.get_report(experiment_id="exp_never_run")

            assert report.experiment_id == "exp_never_run"
            assert report.variant_keys() == []
            assert report.get_variant("control") is None
            assert report.compare_by_metric(_METRIC_NAME) == {}
        finally:
            await engine.dispose()

    asyncio.run(_run())
