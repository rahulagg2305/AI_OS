"""Real-database proof of the synchronous experiment-run orchestrator
(``ai_os_kernel.evaluation_engine.experiment_run_orchestrator``,
``P04-S01-M12-T13``) — the first production caller of the
``evaluation.experiment_runs`` writer, closing the R-018 "proven but idle"
gap for that table.

The orchestrator is driven with the same real collaborators the worker
loop uses, against real Postgres (ADR-0015, no mocking the database): a
``NoOpStepExecutor`` so each variant's real workflow instance genuinely
runs to *completion* (proving the happy path end to end), a real
:class:`StaticRouter` resolving each alias, and the real
``SqlExperimentRunRecorder``/``SqlExperimentRepository``. The point is
that real ``experiment_runs`` rows appear, one per variant x replicate,
each linked to a real ``workflow_instances`` row, with the resolved model
id and ``served_from_cache=False`` (overview.md §7), and the experiment's
own status transitions ``defined`` -> ``complete``.
"""

import asyncio
import os
from collections.abc import Generator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.evaluation_engine.experiment_repository import (
    ExperimentDefinitionInput,
    SqlExperimentRepository,
)
from ai_os_kernel.evaluation_engine.experiment_run_orchestrator import (
    ExperimentNotFoundError,
    ExperimentNotRunnableError,
    ExperimentRunOrchestrator,
    expand_model_variants,
)
from ai_os_kernel.evaluation_engine.experiment_run_reader import SqlExperimentRunReader
from ai_os_kernel.llm_gateway.errors import LLMProviderError
from ai_os_kernel.llm_gateway.router import RoutingDecision, StaticRouter
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.evaluation_schema import experiment_runs
from ai_os_kernel.sdk_adapters.experiment_run_recorder_adapter import SqlExperimentRunRecorder
from ai_os_kernel.workflow_engine.advance_runner import WorkflowAdvanceRunner
from ai_os_kernel.workflow_engine.definition_catalog import SqlWorkflowDefinitionCatalog
from ai_os_kernel.workflow_engine.lease import SqlWorkflowLeaseRepository, WorkflowLeaseService
from ai_os_kernel.workflow_engine.models import WorkflowDefinition
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from ai_os_kernel.workflow_engine.service import WorkflowInstanceService
from ai_os_kernel.workflow_engine.step_executor import DispatchingStepExecutor, NoOpStepExecutor
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

_DEFINITION_ID = "se.experiment_run_orchestrator_test"
_DEFINITION_VERSION = "1.0.0"
_PACK_ID = "se.software_engineering"
_ALIAS_ONE = "alias-one"
_ALIAS_TWO = "alias-two"
_MODEL_ONE = "resolved-model-one"
_MODEL_TWO = "resolved-model-two"


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


def _one_step_definition() -> WorkflowDefinition:
    return WorkflowDefinition.model_validate(
        {
            "id": _DEFINITION_ID,
            "name": "Experiment Run Orchestrator Test",
            "description": "The smallest real definition an experiment run can complete.",
            "version": _DEFINITION_VERSION,
            "inputs": {"type": "object"},
            "outputs": {"type": "object"},
            "steps": [{"id": "do_work", "type": "agent", "agentId": f"{_PACK_ID}/analyst"}],
            "failureHandling": {"onError": "escalate"},
        }
    )


def _build_orchestrator(engine: AsyncEngine) -> ExperimentRunOrchestrator:
    definition_catalog = SqlWorkflowDefinitionCatalog(engine)
    instance_repository = SqlWorkflowInstanceRepository(engine)
    instance_service = WorkflowInstanceService(
        repository=instance_repository,
        step_executor=DispatchingStepExecutor(
            agent_executor=NoOpStepExecutor(),
            tool_executor=NoOpStepExecutor(),
            default_executor=NoOpStepExecutor(),
        ),
        definition_catalog=definition_catalog,
    )
    return ExperimentRunOrchestrator(
        experiment_repository=SqlExperimentRepository(
            engine, definition_catalog=definition_catalog
        ),
        definition_catalog=definition_catalog,
        instance_repository=instance_repository,
        advance_runner=WorkflowAdvanceRunner(
            instance_service=instance_service,
            lease_service=WorkflowLeaseService(SqlWorkflowLeaseRepository(engine)),
        ),
        router=StaticRouter(
            routes={
                _ALIAS_ONE: RoutingDecision(provider="anthropic", model_id=_MODEL_ONE),
                _ALIAS_TWO: RoutingDecision(provider="anthropic", model_id=_MODEL_TWO),
            }
        ),
        run_recorder=SqlExperimentRunRecorder(engine),
    )


async def _create_experiment(
    engine: AsyncEngine, *, variables: dict[str, list[str]], runs_per_variant: int
) -> str:
    definition_catalog = SqlWorkflowDefinitionCatalog(engine)
    await definition_catalog.register(definition=_one_step_definition(), pack_id=_PACK_ID)
    repository = SqlExperimentRepository(engine, definition_catalog=definition_catalog)
    record = await repository.create(
        ExperimentDefinitionInput(
            name="orchestrator test experiment",
            description="two model aliases, three replicates each",
            definition_id=_DEFINITION_ID,
            definition_version=_DEFINITION_VERSION,
            variables=variables,
            runs_per_variant=runs_per_variant,
        ),
        created_by="orchestrator-test",
    )
    return record.experiment_id


def test_expand_model_variants_yields_one_variant_per_declared_alias() -> None:
    variants = expand_model_variants({"model_alias": [_ALIAS_ONE, _ALIAS_TWO]})
    assert variants == [
        (f"model_alias={_ALIAS_ONE}", _ALIAS_ONE),
        (f"model_alias={_ALIAS_TWO}", _ALIAS_TWO),
    ]


def test_expand_model_variants_rejects_a_non_model_dimension() -> None:
    with pytest.raises(ExperimentNotRunnableError):
        expand_model_variants({"prompt_variant": ["a", "b"]})


def test_expand_model_variants_rejects_a_multi_factor_map() -> None:
    with pytest.raises(ExperimentNotRunnableError):
        expand_model_variants({"model_alias": [_ALIAS_ONE, _ALIAS_TWO], "prompt_variant": ["a"]})


def test_a_full_run_materialises_one_experiment_run_row_per_variant_and_replicate(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            experiment_id = await _create_experiment(
                engine, variables={"model_alias": [_ALIAS_ONE, _ALIAS_TWO]}, runs_per_variant=3
            )
            orchestrator = _build_orchestrator(engine)

            summary = await orchestrator.run(experiment_id, principal_id="runner-1")

            assert summary.variant_count == 2
            assert summary.runs_per_variant == 3
            assert len(summary.run_ids) == 6
            assert summary.status == "complete"

            # The experiment's own lifecycle status genuinely advanced.
            repository = SqlExperimentRepository(
                engine, definition_catalog=SqlWorkflowDefinitionCatalog(engine)
            )
            experiment = await repository.get(experiment_id)
            assert experiment is not None
            assert experiment.status == "complete"

            # Six real experiment_runs rows, one per (alias, replicate).
            async with engine.connect() as connection:
                rows = (
                    (
                        await connection.execute(
                            sa.select(experiment_runs).where(
                                experiment_runs.c.experiment_id == experiment_id
                            )
                        )
                    )
                    .mappings()
                    .all()
                )
            assert len(rows) == 6
            assert {r["run_id"] for r in rows} == set(summary.run_ids)
            # Every run genuinely completed (NoOp executor), was never
            # cache-served (§7), and resolved to the right model id.
            assert all(r["status"] == "completed" for r in rows)
            assert all(r["served_from_cache"] is False for r in rows)
            resolved_by_alias = {r["model_alias"]: r["resolved_model_id"] for r in rows}
            assert resolved_by_alias == {_ALIAS_ONE: _MODEL_ONE, _ALIAS_TWO: _MODEL_TWO}
            # Each variant has replicates 0,1,2 and a real variant_key.
            assert {(r["model_alias"], r["replicate_index"]) for r in rows} == {
                (_ALIAS_ONE, 0),
                (_ALIAS_ONE, 1),
                (_ALIAS_ONE, 2),
                (_ALIAS_TWO, 0),
                (_ALIAS_TWO, 1),
                (_ALIAS_TWO, 2),
            }
            assert {r["variant_key"] for r in rows} == {
                f"model_alias={_ALIAS_ONE}",
                f"model_alias={_ALIAS_TWO}",
            }
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_the_run_reader_lists_every_produced_row_in_a_stable_order(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            experiment_id = await _create_experiment(
                engine, variables={"model_alias": [_ALIAS_ONE, _ALIAS_TWO]}, runs_per_variant=3
            )
            await _build_orchestrator(engine).run(experiment_id, principal_id="runner-1")

            records = await SqlExperimentRunReader(engine).list_for_experiment(experiment_id)

            assert len(records) == 6
            # Ordered by (variant_key, replicate_index): alias-one 0,1,2 then alias-two 0,1,2.
            assert [(r.model_alias, r.replicate_index) for r in records] == [
                (_ALIAS_ONE, 0),
                (_ALIAS_ONE, 1),
                (_ALIAS_ONE, 2),
                (_ALIAS_TWO, 0),
                (_ALIAS_TWO, 1),
                (_ALIAS_TWO, 2),
            ]
            assert all(r.experiment_id == experiment_id for r in records)
            assert all(r.status == "completed" for r in records)
            assert all(r.served_from_cache is False for r in records)
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_the_run_reader_returns_an_empty_list_for_an_experiment_with_no_runs(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            experiment_id = await _create_experiment(
                engine, variables={"model_alias": [_ALIAS_ONE, _ALIAS_TWO]}, runs_per_variant=3
            )
            records = await SqlExperimentRunReader(engine).list_for_experiment(experiment_id)
            assert records == []
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_running_a_missing_experiment_is_a_clear_error(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            orchestrator = _build_orchestrator(engine)
            with pytest.raises(ExperimentNotFoundError):
                await orchestrator.run("exp_does_not_exist", principal_id="runner-1")
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_non_model_experiment_is_rejected_before_any_run(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            experiment_id = await _create_experiment(
                engine, variables={"prompt_variant": ["a", "b"]}, runs_per_variant=3
            )
            orchestrator = _build_orchestrator(engine)
            with pytest.raises(ExperimentNotRunnableError):
                await orchestrator.run(experiment_id, principal_id="runner-1")
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_an_unroutable_alias_fails_the_run(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            experiment_id = await _create_experiment(
                engine, variables={"model_alias": [_ALIAS_ONE, "no-such-alias"]}, runs_per_variant=3
            )
            orchestrator = _build_orchestrator(engine)
            with pytest.raises(LLMProviderError):
                await orchestrator.run(experiment_id, principal_id="runner-1")
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_no_experiment_runs_are_written_when_an_alias_is_unroutable(database_url: str) -> None:
    """Alias resolution happens up front, before any instance is created —
    an unroutable alias must leave no half-run experiment behind."""

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            experiment_id = await _create_experiment(
                engine, variables={"model_alias": [_ALIAS_ONE, "no-such-alias"]}, runs_per_variant=3
            )
            orchestrator = _build_orchestrator(engine)
            with pytest.raises(LLMProviderError):
                await orchestrator.run(experiment_id, principal_id="runner-1")
            async with engine.connect() as connection:
                count = (
                    await connection.execute(
                        sa.select(sa.func.count())
                        .select_from(experiment_runs)
                        .where(experiment_runs.c.experiment_id == experiment_id)
                    )
                ).scalar_one()
            assert count == 0
        finally:
            await engine.dispose()

    asyncio.run(_run())
