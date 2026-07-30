"""Real, end-to-end proof of this step's own deliverable: the Health
Service's new ``database_check`` (``ai_os_kernel.bootstrap._build_health_service``)
genuinely tests database *reachability* — a real ``SELECT 1`` against
the real, pooled engine ``_lifespan`` builds — not merely "was a URL
configured."

Two real scenarios:

1. A real, reachable Postgres container (ADR-0015, testcontainers):
   `/health/ready` reports the database component ``"ok"``, the overall
   report ``"ready"``, and HTTP 200 — unaffected by this step's own
   addition, proving zero regression to the healthy path.
2. A genuinely unreachable database — a well-formed
   ``AIOS_DATABASE_URL`` pointing at a real host with nothing listening
   on the given port (connection refused, not a slow timeout, so this
   test stays fast) — proves the resolved hard-vs-soft decision for
   real: the database component reports ``"error"``/``critical: true``,
   the overall report escalates to ``"not_ready"``, and the route
   returns HTTP 503, not 200 — exactly what a Kubernetes readiness probe
   needs to stop routing traffic to an instance whose every functional
   route (``POST /api/v1/workflows``, ``.../se.delivery_pipeline``,
   ``.../packs``) already independently 503s without a working database
   anyway (confirmed by reading each route's own source — see
   ``ai_os_kernel.health.service``'s own docstring for the full
   evidence).
"""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from ai_os_kernel.bootstrap import build_app
from ai_os_kernel.configuration_manager import PlatformConfig
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
SCHEMA_PATH = "platform_sdk/schemas/manifest.schema.json"

# Port 1 is a reserved, privileged port essentially never bound by any
# real service — connecting to it fails immediately with "connection
# refused", not a slow OS-level TCP timeout, keeping this test fast
# without needing to wait out _DATABASE_CHECK_TIMEOUT_SECONDS for real.
_UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://user:pass@127.0.0.1:1/nonexistent"


def _config() -> PlatformConfig:
    return PlatformConfig(
        env="test",
        role="api",
        capability_pack_dirs=[],
        manifest_schema_path=SCHEMA_PATH,
    )


def test_health_ready_is_unaffected_when_the_database_is_genuinely_reachable() -> None:
    with postgres_container() as postgres:
        url = postgres.get_connection_url()
        previous = os.environ.get("AIOS_DATABASE_URL")
        os.environ["AIOS_DATABASE_URL"] = url
        try:
            command.upgrade(Config(str(ALEMBIC_INI)), "head")

            app = build_app(_config())
            with TestClient(app) as client:
                response = client.get("/api/v1/health/ready")
        finally:
            if previous is None:
                os.environ.pop("AIOS_DATABASE_URL", None)
            else:
                os.environ["AIOS_DATABASE_URL"] = previous

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"

    database_component = next(c for c in body["components"] if c["name"] == "database")
    assert database_component["status"] == "ok"
    assert database_component["critical"] is True
    assert database_component["detail"] == "reachable"


def test_health_ready_reports_503_when_the_database_is_genuinely_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIOS_DATABASE_URL", _UNREACHABLE_DATABASE_URL)

    app = build_app(_config())
    with TestClient(app) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"

    database_component = next(c for c in body["components"] if c["name"] == "database")
    assert database_component["status"] == "error"
    assert database_component["critical"] is True
    assert "unreachable" in database_component["detail"]

    # Every other, non-critical check is entirely unaffected — a hard
    # dependency's failure escalates the *overall* status without
    # hiding or corrupting any other component's own real report.
    configuration_component = next(
        c for c in body["components"] if c["name"] == "configuration_manager"
    )
    assert configuration_component["status"] == "ok"
