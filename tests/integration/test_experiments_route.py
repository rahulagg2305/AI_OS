"""Real-database verification of the §6.3 Experiments create+read routes
(``ai_os_kernel.routes.experiments``, ``P04-S01-M12-T12``) through the
real composition root (``bootstrap.build_app()`` + ``_lifespan``).

The create path is the point: it gives ``evaluation.experiments`` its
first real writer, so the read routes are not hollow (the "proven but
idle" R-018 trap the recent Traceability/Project-Intelligence steps
closed). A real workflow definition is registered first, since an
experiment's ``definition_id``/``definition_version`` is a real composite
FK into ``catalog.workflow_definitions``.

Real Postgres via testcontainers (ADR-0015) — no mocking the database.
"""

import asyncio
import os
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import jwt
import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from ulid import ULID

from ai_os_kernel.bootstrap import build_app
from ai_os_kernel.configuration_manager import PlatformConfig
from ai_os_kernel.evaluation_engine.experiment_repository import (
    ExperimentDefinitionInput,
    SqlExperimentRepository,
)
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.evaluation_schema import experiment_runs, metrics
from ai_os_kernel.sdk_adapters.experiment_run_recorder_adapter import SqlExperimentRunRecorder
from ai_os_kernel.workflow_engine.definition_catalog import SqlWorkflowDefinitionCatalog
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


def _register_workflow_definition(database_url: str) -> None:
    async def _register() -> None:
        engine = build_engine(database_url)
        try:
            await SqlWorkflowDefinitionCatalog(engine).register(
                definition=WorkflowDefinition.model_validate(
                    {
                        "id": _DEFINITION_ID,
                        "name": "Product Creation (experiments route test)",
                        "description": "The smallest valid definition an experiment can reference.",
                        "version": _DEFINITION_VERSION,
                        "inputs": {"type": "object"},
                        "outputs": {"type": "object"},
                        "steps": [
                            {"id": "noop", "type": "agent", "agentId": "se.software_engineering/x"}
                        ],
                        "failureHandling": {"onError": "halt"},
                    }
                ),
                pack_id=_PACK_ID,
            )
        finally:
            await engine.dispose()

    asyncio.run(_register())


def _valid_body() -> dict[str, Any]:
    return {
        "name": "GPT vs Claude on product creation",
        "description": "Compare two models across three replicates each.",
        "definition_id": _DEFINITION_ID,
        "definition_version": _DEFINITION_VERSION,
        "variables": {"model_alias": ["coding-strong", "coding-fast"]},
        "runs_per_variant": 3,
    }


def _runnable_body() -> dict[str, Any]:
    # Both aliases are real, routable entries in config/llm.yaml, so the
    # run reaches real execution rather than a 422 on an unroutable alias.
    return _valid_body() | {"variables": {"model_alias": ["coding-strong", "coding-balanced"]}}


def _count_experiment_runs(database_url: str, experiment_id: str) -> int:
    async def _count() -> int:
        engine = build_engine(database_url)
        try:
            async with engine.connect() as connection:
                return (
                    await connection.execute(
                        sa.select(sa.func.count())
                        .select_from(experiment_runs)
                        .where(experiment_runs.c.experiment_id == experiment_id)
                    )
                ).scalar_one()
        finally:
            await engine.dispose()

    return asyncio.run(_count())


def _seed_experiment_with_completed_runs_and_metrics(database_url: str) -> str:
    """Seed one experiment with three real, completed, non-cache-served
    runs for a single variant, each with a real `cost_usd_total` metric
    (1.0, 2.0, 3.0 → mean 2.0, sample variance 1.0) — enough for a real,
    non-empty comparison to flow through the route. Each run needs a real
    `workflow_instances` row (both `experiment_runs` and `metrics` FK it),
    created the same way the orchestrator does."""

    async def _seed() -> str:
        engine = build_engine(database_url)
        try:
            catalog = SqlWorkflowDefinitionCatalog(engine)
            experiment_repository = SqlExperimentRepository(engine, definition_catalog=catalog)
            experiment = await experiment_repository.create(
                ExperimentDefinitionInput(
                    name="seeded comparison experiment",
                    description="three completed replicates of one variant, with metrics",
                    definition_id=_DEFINITION_ID,
                    definition_version=_DEFINITION_VERSION,
                    variables={"model_alias": ["coding-strong", "coding-balanced"]},
                    runs_per_variant=3,
                ),
                created_by="seed",
            )
            instance_repository = SqlWorkflowInstanceRepository(engine)
            recorder = SqlExperimentRunRecorder(engine)
            for replicate_index, value in enumerate(("1.0", "2.0", "3.0")):
                instance = await instance_repository.create(
                    definition_id=_DEFINITION_ID,
                    definition_version=_DEFINITION_VERSION,
                    inputs={},
                    principal_id="seed",
                )
                run_id = await recorder.record(
                    experiment_id=experiment.experiment_id,
                    workflow_id=instance.workflow_id,
                    variant_key="model_alias=coding-strong",
                    model_alias="coding-strong",
                    resolved_model_id="claude-opus-5",
                    replicate_index=replicate_index,
                    served_from_cache=False,
                    status="completed",
                )
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.insert(metrics).values(
                            metric_id=f"met_{ULID()}",
                            workflow_id=instance.workflow_id,
                            run_id=run_id,
                            metric_name="cost_usd_total",
                            metric_value=Decimal(value),
                            unit="usd",
                            source_component="test-seed",
                            recorded_at=datetime.now(UTC),
                        )
                    )
            return experiment.experiment_id
        finally:
            await engine.dispose()

    return asyncio.run(_seed())


def test_create_route_requires_authentication(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    with TestClient(app) as client:
        response = client.post("/api/v1/experiments", json=_valid_body())
    assert response.status_code == 401


def test_a_viewer_cannot_create_but_an_operator_can(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _register_workflow_definition(database_url)
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    with TestClient(app) as client:
        # viewer has evaluation:read (can read) but not experiment:run.
        denied = client.post(
            "/api/v1/experiments",
            json=_valid_body(),
            headers={"Authorization": f"Bearer {_token(['viewer'])}"},
        )
        assert denied.status_code == 403

        created = client.post(
            "/api/v1/experiments",
            json=_valid_body(),
            headers={"Authorization": f"Bearer {_token(['operator'])}"},
        )
    assert created.status_code == 201
    body = created.json()
    assert body["experiment_id"].startswith("exp_")
    assert body["status"] == "defined"
    # created_by comes from the authenticated principal, never the body.
    assert body["created_by"] == "integration-test-user"
    assert body["variables"] == {"model_alias": ["coding-strong", "coding-fast"]}
    assert body["pinned_conditions"] == {}


def test_a_created_experiment_reads_back_and_lists(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _register_workflow_definition(database_url)
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/experiments",
            json=_valid_body(),
            headers={"Authorization": f"Bearer {_token(['operator'])}"},
        )
        experiment_id = created.json()["experiment_id"]

        # viewer (evaluation:read) can read it back and list.
        got = client.get(
            f"/api/v1/experiments/{experiment_id}",
            headers={"Authorization": f"Bearer {_token(['viewer'])}"},
        )
        listed = client.get(
            "/api/v1/experiments",
            headers={"Authorization": f"Bearer {_token(['viewer'])}"},
        )

    assert got.status_code == 200
    assert got.json()["experiment_id"] == experiment_id
    assert experiment_id in {item["experiment_id"] for item in listed.json()["items"]}


def test_a_missing_experiment_is_a_real_404(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/experiments/exp_does_not_exist",
            headers={"Authorization": f"Bearer {_token(['viewer'])}"},
        )
    assert response.status_code == 404


def test_semantically_invalid_definitions_are_real_422s(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _register_workflow_definition(database_url)
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    headers = {"Authorization": f"Bearer {_token(['operator'])}"}
    with TestClient(app) as client:
        too_few_replicates = _valid_body() | {"runs_per_variant": 2}
        r1 = client.post("/api/v1/experiments", json=too_few_replicates, headers=headers)

        one_variant = _valid_body() | {"variables": {"model_alias": ["only-one"]}}
        r2 = client.post("/api/v1/experiments", json=one_variant, headers=headers)

    assert r1.status_code == 422
    assert r2.status_code == 422


def test_run_route_requires_authentication(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    with TestClient(app) as client:
        response = client.post("/api/v1/experiments/exp_whatever/run")
    assert response.status_code == 401


def test_a_viewer_cannot_run_but_an_operator_can(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _register_workflow_definition(database_url)
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/experiments",
            json=_runnable_body(),
            headers={"Authorization": f"Bearer {_token(['operator'])}"},
        )
        experiment_id = created.json()["experiment_id"]

        # viewer has evaluation:read but not experiment:run.
        denied = client.post(
            f"/api/v1/experiments/{experiment_id}/run",
            headers={"Authorization": f"Bearer {_token(['viewer'])}"},
        )
        assert denied.status_code == 403

        ran = client.post(
            f"/api/v1/experiments/{experiment_id}/run",
            headers={"Authorization": f"Bearer {_token(['operator'])}"},
        )

    assert ran.status_code == 200
    summary = ran.json()
    # Two aliases x three replicates = six real experiment_runs rows.
    assert summary["experiment_id"] == experiment_id
    assert summary["variant_count"] == 2
    assert summary["runs_per_variant"] == 3
    assert len(summary["run_ids"]) == 6
    assert summary["status"] == "complete"
    # Every run_id is a genuinely persisted row.
    assert _count_experiment_runs(database_url, experiment_id) == 6


def test_running_a_missing_experiment_is_a_real_404(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/experiments/exp_does_not_exist/run",
            headers={"Authorization": f"Bearer {_token(['operator'])}"},
        )
    assert response.status_code == 404


def test_running_a_non_model_experiment_is_a_real_422(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _register_workflow_definition(database_url)
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    with TestClient(app) as client:
        # Valid at definition time (two variants), but this synchronous
        # slice only runs experiments varying the `model_alias` dimension.
        created = client.post(
            "/api/v1/experiments",
            json=_valid_body() | {"variables": {"prompt_variant": ["a", "b"]}},
            headers={"Authorization": f"Bearer {_token(['operator'])}"},
        )
        experiment_id = created.json()["experiment_id"]
        response = client.post(
            f"/api/v1/experiments/{experiment_id}/run",
            headers={"Authorization": f"Bearer {_token(['operator'])}"},
        )
    assert response.status_code == 422


def test_comparison_and_runs_routes_require_authentication(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    with TestClient(app) as client:
        assert client.get("/api/v1/experiments/exp_x/comparison").status_code == 401
        assert client.get("/api/v1/experiments/exp_x/runs").status_code == 401


def test_comparison_and_runs_404_for_a_missing_experiment(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    headers = {"Authorization": f"Bearer {_token(['viewer'])}"}
    with TestClient(app) as client:
        assert (
            client.get("/api/v1/experiments/exp_missing/comparison", headers=headers).status_code
            == 404
        )
        assert (
            client.get("/api/v1/experiments/exp_missing/runs", headers=headers).status_code == 404
        )


def test_a_defined_but_unrun_experiment_has_an_empty_comparison_and_no_runs(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _register_workflow_definition(database_url)
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/experiments",
            json=_runnable_body(),
            headers={"Authorization": f"Bearer {_token(['operator'])}"},
        )
        experiment_id = created.json()["experiment_id"]
        # viewer (evaluation:read) can read both; an existing-but-unrun
        # experiment is a real, empty-but-valid report, never a 404.
        comparison = client.get(
            f"/api/v1/experiments/{experiment_id}/comparison",
            headers={"Authorization": f"Bearer {_token(['viewer'])}"},
        )
        runs = client.get(
            f"/api/v1/experiments/{experiment_id}/runs",
            headers={"Authorization": f"Bearer {_token(['viewer'])}"},
        )
    assert comparison.status_code == 200
    assert comparison.json() == {"experiment_id": experiment_id, "variants": []}
    assert runs.status_code == 200
    assert runs.json() == {"items": []}


def test_the_runs_route_lists_the_rows_a_real_run_produced(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _register_workflow_definition(database_url)
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/experiments",
            json=_runnable_body(),
            headers={"Authorization": f"Bearer {_token(['operator'])}"},
        )
        experiment_id = created.json()["experiment_id"]
        client.post(
            f"/api/v1/experiments/{experiment_id}/run",
            headers={"Authorization": f"Bearer {_token(['operator'])}"},
        )
        runs = client.get(
            f"/api/v1/experiments/{experiment_id}/runs",
            headers={"Authorization": f"Bearer {_token(['viewer'])}"},
        )
    assert runs.status_code == 200
    items = runs.json()["items"]
    # Two aliases x three replicates = six real rows, each fully populated.
    assert len(items) == 6
    assert {item["model_alias"] for item in items} == {"coding-strong", "coding-balanced"}
    assert all(item["experiment_id"] == experiment_id for item in items)
    assert all(item["run_id"].startswith("xr_") for item in items)


def test_the_comparison_route_returns_the_real_computed_report(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _register_workflow_definition(database_url)
    experiment_id = _seed_experiment_with_completed_runs_and_metrics(database_url)
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    with TestClient(app) as client:
        response = client.get(
            f"/api/v1/experiments/{experiment_id}/comparison",
            headers={"Authorization": f"Bearer {_token(['viewer'])}"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["experiment_id"] == experiment_id
    variants = {v["variant_key"]: v for v in body["variants"]}
    assert "model_alias=coding-strong" in variants
    strong = variants["model_alias=coding-strong"]
    metric = next(m for m in strong["metrics"] if m["metric_name"] == "cost_usd_total")
    # Values 1.0, 2.0, 3.0 → mean 2.0, sample variance 1.0 (Decimal-exact).
    assert metric["replicate_count"] == 3
    assert Decimal(str(metric["mean"])) == Decimal("2")
    assert Decimal(str(metric["variance"])) == Decimal("1")
    assert strong["excluded_cache_served_count"] == 0


def test_referencing_an_unknown_workflow_definition_is_a_real_404(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    with TestClient(app) as client:
        body = _valid_body() | {"definition_id": "does.not.exist"}
        response = client.post(
            "/api/v1/experiments",
            json=body,
            headers={"Authorization": f"Bearer {_token(['operator'])}"},
        )
    assert response.status_code == 404
