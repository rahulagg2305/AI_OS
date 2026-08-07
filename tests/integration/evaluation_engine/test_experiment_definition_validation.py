"""`ai_os_pack_benchmarking.experiment_definition.validate_experiment_spec`,
end to end, against real Postgres (ADR-0015 — no mocking the
database). Proves the real chain `P04-S03-M34-T01` exists for: a real
`SqlWorkflowDefinitionExistenceCheck`
(`ai_os_kernel.sdk_adapters.workflow_definition_existence_adapter`),
querying real `catalog.workflow_definitions` rows, genuinely backs the
pack's own `WorkflowDefinitionExistenceCheck` Protocol — accepting a
spec that pins a real, registered workflow, and rejecting one that
pins a workflow that was never registered.
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

from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.sdk_adapters.workflow_definition_existence_adapter import (
    SqlWorkflowDefinitionExistenceCheck,
)
from ai_os_pack_benchmarking.experiment_definition import (
    ExperimentSpec,
    ExperimentValidationError,
    ExperimentVariant,
    validate_experiment_spec,
)
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

_DEFINITION_ID = "test.experiment-validation-workflow"
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


def _spec(**overrides: object) -> ExperimentSpec:
    defaults: dict[str, object] = {
        "name": "compare opus vs sonnet",
        "description": "a real, minimal two-variant comparison",
        "definition_id": _DEFINITION_ID,
        "definition_version": _DEFINITION_VERSION,
        "variants": [
            ExperimentVariant(variant_key="control", model_alias="coding-strong"),
            ExperimentVariant(variant_key="treatment", model_alias="reasoning"),
        ],
        "runs_per_variant": 3,
        "created_by": "test-principal",
    }
    defaults.update(overrides)
    return ExperimentSpec(**defaults)


def test_a_spec_pinning_a_real_registered_workflow_is_accepted(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
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

            existence_check = SqlWorkflowDefinitionExistenceCheck(engine)
            definition = await validate_experiment_spec(_spec(), existence_check=existence_check)

            assert definition.definition_id == _DEFINITION_ID
            assert definition.definition_version == _DEFINITION_VERSION
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_spec_pinning_a_never_registered_workflow_is_rejected(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            existence_check = SqlWorkflowDefinitionExistenceCheck(engine)

            with pytest.raises(ExperimentValidationError, match="no workflow definition exists"):
                await validate_experiment_spec(
                    _spec(
                        definition_id="test.never-registered-workflow",
                        definition_version="9.9.9",
                    ),
                    existence_check=existence_check,
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())
