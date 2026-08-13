"""Deterministic, real-database verification of ``GET /api/v1/gates/results``
(``ai_os_kernel.routes.gates``, added 2026-08-10, `P06-S01-M36-T04`)
through the real composition root (``bootstrap.build_app()`` +
``_lifespan``) — not a direct call to
``ai_os_kernel.workflow_engine.gate_result_recorder.SqlGateResultRecorder``
as ``tests/integration/workflow_engine/test_gate_result_recorder.py``
uses.

Real Postgres via testcontainers (ADR-0015) — no mocking the database.
"""

import asyncio
import os
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from ai_os_kernel.bootstrap import build_app
from ai_os_kernel.configuration_manager import PlatformConfig
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.evaluation_schema import gate_results
from ai_os_kernel.workflow_engine.definition_catalog import SqlWorkflowDefinitionCatalog
from ai_os_kernel.workflow_engine.ids import new_gate_result_id
from ai_os_kernel.workflow_engine.models import WorkflowDefinition
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
SCHEMA_PATH = "platform_sdk/schemas/manifest.schema.json"
_SIGNING_KEY = "integration-test-signing-key-at-least-32-bytes"  # gitleaks:allow
_DEFINITION_ID = "se.product_creation"
_DEFINITION_VERSION = "1.0.0"
_PACK_ID = "se.software_engineering"


def _minimal_workflow_definition() -> WorkflowDefinition:
    # The identical minimal-but-valid shape
    # `tests/integration/workflow_engine/conftest.py` already
    # establishes — a real `WorkflowDefinitionCatalog.register()` call,
    # not a raw insert, since `workflow_instances` carries a real FK to
    # `catalog.workflow_definitions` (data_model.md §4.1) that a
    # directly-called `SqlWorkflowInstanceRepository.create()` (as this
    # file uses, bypassing `WorkflowInstanceService`) does not satisfy
    # on its own.
    return WorkflowDefinition.model_validate(
        {
            "id": _DEFINITION_ID,
            "name": "Product Creation (gates route test)",
            "description": "The smallest valid definition satisfying the real "
            "workflow_instances FK this test's direct repository call needs.",
            "version": _DEFINITION_VERSION,
            "inputs": {"type": "object"},
            "outputs": {"type": "object"},
            "steps": [
                {"id": "noop", "type": "agent", "agentId": "se.software_engineering/analyst"}
            ],
            "failureHandling": {"onError": "halt"},
        }
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


def _config() -> PlatformConfig:
    return PlatformConfig(
        env="test",
        role="api",
        capability_pack_dirs=[],
        manifest_schema_path=SCHEMA_PATH,
    )


def _token(roles: list[str]) -> str:
    claims = {
        "sub": "integration-test-user",
        "roles": roles,
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    return jwt.encode(claims, _SIGNING_KEY, algorithm="HS256")


def _seed_real_gate_result(database_url: str) -> tuple[str, str]:
    async def _seed() -> tuple[str, str]:
        engine = build_engine(database_url)
        try:
            await SqlWorkflowDefinitionCatalog(engine).register(
                definition=_minimal_workflow_definition(), pack_id=_PACK_ID
            )
            instance = await SqlWorkflowInstanceRepository(engine).create(
                definition_id=_DEFINITION_ID,
                definition_version=_DEFINITION_VERSION,
                inputs={},
                principal_id="gates-route-test-principal",
            )
            result_id = new_gate_result_id()
            async with engine.begin() as connection:
                await connection.execute(
                    sa.insert(gate_results).values(
                        result_id=result_id,
                        workflow_id=instance.workflow_id,
                        step_id="test-gate-step",
                        gate_id="test-gate-step",
                        gate_version="1.0.0",
                        status="completed",
                        severity="blocking",
                        metrics={"attempt": 1},
                        messages=[],
                        duration_ms=0,
                    )
                )
            return instance.workflow_id, result_id
        finally:
            await engine.dispose()

    return asyncio.run(_seed())


def test_gates_results_route_requires_authentication(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.get("/api/v1/gates/results")

    assert response.status_code == 401


def test_gates_results_route_lists_a_real_result_filtered_by_workflow(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    workflow_id, result_id = _seed_real_gate_result(database_url)

    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    with TestClient(app) as client:
        # evaluation:read is granted to every real role (viewer
        # included) — permissions.py's own role table.
        response = client.get(
            "/api/v1/gates/results",
            params={"workflow_id": workflow_id},
            headers={"Authorization": f"Bearer {_token(['viewer'])}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert [item["result_id"] for item in body["items"]] == [result_id]
    assert body["items"][0]["status"] == "completed"
