"""`SqlExperimentRunRecorder`, end to end, against real Postgres
(ADR-0015 — no mocking the database). Proves the real Kernel-side
implementation of the Benchmarking Pack's `ExperimentRunRecorder`
Protocol genuinely writes correct `evaluation.experiment_runs` rows,
one per real, planned replicate (`plan_replicates`,
`P04-S03-M34-T02`) — including the real, distinct row each real
replicate of a variant gets.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Generator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.evaluation_schema import experiment_runs, experiments
from ai_os_kernel.sdk_adapters.experiment_run_recorder_adapter import (
    ExperimentRunRecordingError,
    SqlExperimentRunRecorder,
)
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from ai_os_pack_benchmarking.experiment_definition import ExperimentVariant
from ai_os_pack_benchmarking.replicate_management import plan_replicates
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

_DEFINITION_ID = "test.replicate-management-workflow"
_DEFINITION_VERSION = "1.0.0"
_EXPERIMENT_ID = "exp_replicate_management_test"


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
                name="replicate management test",
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


def test_recording_every_planned_replicate_writes_one_real_row_each(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            await _seed_workflow_definition_and_experiment(engine)

            variant = ExperimentVariant(variant_key="control", model_alias="coding-strong")
            plans = plan_replicates(variant, runs_per_variant=3)
            recorder = SqlExperimentRunRecorder(engine)
            repository = SqlWorkflowInstanceRepository(engine)

            run_ids: list[str] = []
            for plan in plans:
                # A real workflow_instances row per replicate — the
                # real precondition this recorder's own module
                # docstring discloses (evaluation.experiment_runs.workflow_id
                # is a NOT NULL foreign key).
                instance = await repository.create(
                    definition_id=_DEFINITION_ID,
                    definition_version=_DEFINITION_VERSION,
                    inputs={},
                    principal_id="test-principal",
                )
                run_id = await recorder.record(
                    experiment_id=_EXPERIMENT_ID,
                    workflow_id=instance.workflow_id,
                    variant_key=plan.variant_key,
                    model_alias=plan.model_alias,
                    replicate_index=plan.replicate_index,
                    resolved_model_id="claude-opus-5",
                    served_from_cache=False,
                    status="running",
                )
                run_ids.append(run_id)

            assert len(set(run_ids)) == 3

            async with engine.connect() as connection:
                rows = (
                    (
                        await connection.execute(
                            sa.select(experiment_runs)
                            .where(experiment_runs.c.experiment_id == _EXPERIMENT_ID)
                            .order_by(experiment_runs.c.replicate_index)
                        )
                    )
                    .mappings()
                    .all()
                )

            assert len(rows) == 3
            for index, row in enumerate(rows):
                assert row["replicate_index"] == index
                assert row["variant_key"] == "control"
                assert row["model_alias"] == "coding-strong"
                assert row["resolved_model_id"] == "claude-opus-5"
                assert row["served_from_cache"] is False
                assert row["status"] == "running"
                assert row["run_id"] == run_ids[index]
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_recording_against_an_unregistered_workflow_raises_a_clear_error(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            await _seed_workflow_definition_and_experiment(engine)
            recorder = SqlExperimentRunRecorder(engine)

            with pytest.raises(ExperimentRunRecordingError, match="failed to record"):
                await recorder.record(
                    experiment_id=_EXPERIMENT_ID,
                    workflow_id="wf_does-not-exist",
                    variant_key="control",
                    model_alias="coding-strong",
                    replicate_index=0,
                    resolved_model_id="claude-opus-5",
                    served_from_cache=False,
                    status="running",
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())
