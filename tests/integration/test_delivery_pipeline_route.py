"""Deterministic, real-database verification that the Software
Engineering pack's own real HTTP trigger route
(``POST /api/v1/workflows/se.delivery_pipeline``) genuinely fronts the
real production composition (``ai_os_kernel.bootstrap.build_app()`` +
``_lifespan``'s own ``_build_se_delivery_pipeline_registry``/
``build_pipeline_trigger`` wiring) — not a hand-assembled equivalent,
and not the no-database unit tests in
``tests/unit/kernel/routes/test_delivery_pipeline.py``.

No real Anthropic credential and no seeded ``catalog.agents``/
``catalog.prompts`` rows are used here: the real
``SqlAgentRegistry``-resolved agents can therefore never actually run,
so an authorized request reaches all the way through authentication,
authorization, and the real Workflow Engine machinery, and gets a real,
structured ``failed`` outcome back — proving the security boundary and
the real trigger wiring both work, without needing a live credential or
any real pack registration at all.
Mirrors exactly how ``tests/integration/test_workflows_route.py``'s own
``test_an_authorized_request_reaches_the_real_workflow_engine`` proves
the platform demo route's identical plumbing.

The opt-in live counterpart,
``tests/integration/test_delivery_pipeline_route_live.py``, proves the
full path all the way to a genuine, completed 5-agent run, reusing the
same real ``_register_and_activate_pack`` helper
``tests/integration/workflow_engine/test_delivery_pipeline.py``'s own
live test already established (now backed by the real manifest -> catalog
installer, ``ai_os_kernel.capability_manager.manifest_catalog_installer``).

Real Postgres via testcontainers (ADR-0015) — no mocking the database.
"""

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
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
SCHEMA_PATH = "platform_sdk/schemas/manifest.schema.json"
_SIGNING_KEY = "integration-test-signing-key-at-least-32-bytes"
_ROUTE = "/api/v1/workflows/se.delivery_pipeline"


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


def test_an_authorized_request_reaches_the_real_pipeline_trigger(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    monkeypatch.delenv("AIOS_SECRET_LLM_ANTHROPIC_API_KEY", raising=False)
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.post(
            _ROUTE,
            json={"requirement": "print a friendly message"},
            headers={"Authorization": f"Bearer {_token(['operator'])}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["workflow_id"]
    # No real Anthropic credential and no seeded catalog rows, so
    # Requirements Analyst (the pipeline's own real first step) cannot
    # actually resolve/run — a real, structured failure, not a security
    # boundary rejection (401/403) or an unhandled crash.
    assert body["outcome"] == "failed"
    assert body["error"]
    assert body["documentation_path"] is None


def test_an_unauthorized_request_never_reaches_the_real_pipeline_trigger(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.post(
            _ROUTE,
            json={"requirement": "print a friendly message"},
            headers={"Authorization": f"Bearer {_token(['viewer'])}"},
        )

    assert response.status_code == 403
