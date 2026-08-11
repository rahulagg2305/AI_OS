"""Real-database verification of the §6.6 Traceability read routes
(``ai_os_kernel.routes.traceability``, ``P04-S02-M16-T05``) through the
real composition root (``bootstrap.build_app()`` + ``_lifespan``).

Closes the read half of risk register R-018's Traceability instance: the
writer half landed in ``P04-S02-M16-T04``, so real trace links now
exist to read. Data is seeded through the real ``SqlTraceLinkWriter``
(not raw SQL), so these routes are proven over genuinely-written rows,
the same shape a real ``se.delivery_pipeline`` run produces.

Real Postgres via testcontainers (ADR-0015) — no mocking the database.
"""

import asyncio
import os
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from ai_os_kernel.bootstrap import build_app
from ai_os_kernel.configuration_manager import PlatformConfig
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.traceability_engine.link_writer import SqlTraceLinkWriter
from ai_os_kernel.traceability_engine.models import ArtifactInput
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
SCHEMA_PATH = "platform_sdk/schemas/manifest.schema.json"
_SIGNING_KEY = "integration-test-signing-key-at-least-32-bytes"  # gitleaks:allow


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


def _artifact(artifact_type: str, external_id: str) -> ArtifactInput:
    return ArtifactInput(
        artifact_type=artifact_type,
        external_id=external_id,
        title=f"{artifact_type} {external_id}",
        location=external_id,
        version="1.0",
    )


def _seed_produced_documentation_link(database_url: str, workflow_id: str, doc_path: str) -> None:
    async def _seed() -> None:
        engine = build_engine(database_url)
        try:
            await SqlTraceLinkWriter(engine).record_link(
                source=_artifact("workflow_run", workflow_id),
                relationship="produced",
                target=_artifact("documentation", doc_path),
                confidence="confirmed",
                created_by="se.delivery_pipeline",
                created_by_type="process",
            )
        finally:
            await engine.dispose()

    asyncio.run(_seed())


def _seed_verifies_link(
    database_url: str, *, requirement_id: str, test_case_id: str, confidence: str
) -> None:
    async def _seed() -> None:
        engine = build_engine(database_url)
        try:
            await SqlTraceLinkWriter(engine).record_link(
                source=_artifact("test_case", test_case_id),
                relationship="verifies",
                target=_artifact("requirement", requirement_id),
                confidence=confidence,
                created_by="test",
                created_by_type="process",
            )
        finally:
            await engine.dispose()

    asyncio.run(_seed())


def test_impact_route_requires_authentication(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/traceability/impact/wf-x", params={"artifact_type": "workflow_run"}
        )
    assert response.status_code == 401


def test_impact_route_returns_a_real_produced_documentation_artifact(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    workflow_id = "wf_traceability_route_impact"
    doc_path = "workspace/docs/generated/impact.md"
    _seed_produced_documentation_link(database_url, workflow_id, doc_path)

    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    with TestClient(app) as client:
        # evaluation:read is granted to every real role (viewer included).
        response = client.get(
            f"/api/v1/traceability/impact/{workflow_id}",
            params={"artifact_type": "workflow_run"},
            headers={"Authorization": f"Bearer {_token(['viewer'])}"},
        )

    assert response.status_code == 200
    items = response.json()["items"]
    assert [(i["artifact_type"], i["external_id"]) for i in items] == [("documentation", doc_path)]


def test_impact_route_requires_the_artifact_type_query_param(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/traceability/impact/wf-x",
            headers={"Authorization": f"Bearer {_token(['viewer'])}"},
        )
    # A required query param with no default is a real 422, not a silent
    # empty answer over an unspecified artifact.
    assert response.status_code == 422


def test_coverage_route_reports_a_requirement_lacking_a_confirmed_verifying_test(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # One requirement covered by a real confirmed test, one only by a
    # provisional guess (which must NOT discharge coverage).
    _seed_verifies_link(
        database_url,
        requirement_id="FR-COVERED",
        test_case_id="test_covered",
        confidence="confirmed",
    )
    _seed_verifies_link(
        database_url,
        requirement_id="FR-UNCOVERED",
        test_case_id="test_provisional",
        confidence="provisional",
    )

    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/traceability/coverage",
            headers={"Authorization": f"Bearer {_token(['viewer'])}"},
        )

    assert response.status_code == 200
    reported = {i["external_id"] for i in response.json()["items"]}
    assert "FR-UNCOVERED" in reported
    assert "FR-COVERED" not in reported
