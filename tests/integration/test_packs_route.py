"""Deterministic, real-database verification of the Capability
Manager's pack lifecycle HTTP routes (ai_os_kernel.routes.packs)
through the real composition root (``bootstrap.build_app()`` +
``_lifespan``) — not a direct call to
``app.state.pack_lifecycle_repository`` as
``tests/integration/test_bootstrap_pack_lifecycle.py`` uses, and not
the no-database unit tests in ``tests/unit/kernel/routes/test_packs.py``.

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


def test_a_maintainer_can_register_activate_deactivate_and_get_a_pack(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    headers = {"Authorization": f"Bearer {_token(['maintainer'])}"}

    with TestClient(app) as client:
        register_response = client.post(
            "/api/v1/packs",
            json={
                "pack_id": "test.http_lifecycle",
                "version": "1.0.0",
                "manifest": {"name": "http-lifecycle-pack"},
                "sdk_version": "1.0.0",
                "min_kernel_version": "1.0.0",
                "reason": "initial install",
            },
            headers=headers,
        )
        assert register_response.status_code == 201
        assert register_response.json()["state"] == "installed"

        activate_response = client.post(
            "/api/v1/packs/test.http_lifecycle/activate",
            json={"reason": "go live"},
            headers=headers,
        )
        assert activate_response.status_code == 200
        assert activate_response.json()["state"] == "activated"

        deactivate_response = client.post(
            "/api/v1/packs/test.http_lifecycle/deactivate",
            json={"reason": "withdraw"},
            headers=headers,
        )
        assert deactivate_response.status_code == 200
        assert deactivate_response.json()["state"] == "deactivated"

        get_response = client.get("/api/v1/packs/test.http_lifecycle", headers=headers)
        assert get_response.status_code == 200
        assert get_response.json() == deactivate_response.json()


def test_registering_a_duplicate_pack_returns_409(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    headers = {"Authorization": f"Bearer {_token(['maintainer'])}"}
    body = {
        "pack_id": "test.duplicate_http",
        "version": "1.0.0",
        "manifest": {},
        "sdk_version": "1.0.0",
        "min_kernel_version": "1.0.0",
        "reason": "initial install",
    }

    with TestClient(app) as client:
        first = client.post("/api/v1/packs", json=body, headers=headers)
        assert first.status_code == 201

        second = client.post("/api/v1/packs", json=body, headers=headers)

    assert second.status_code == 409


def test_activating_an_unregistered_pack_returns_404(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    headers = {"Authorization": f"Bearer {_token(['maintainer'])}"}

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/packs/test.never_registered_http/activate",
            json={"reason": "go live"},
            headers=headers,
        )

    assert response.status_code == 404


def test_deactivating_a_pack_that_was_never_activated_returns_409(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    headers = {"Authorization": f"Bearer {_token(['maintainer'])}"}

    with TestClient(app) as client:
        register_response = client.post(
            "/api/v1/packs",
            json={
                "pack_id": "test.installed_only_http",
                "version": "1.0.0",
                "manifest": {},
                "sdk_version": "1.0.0",
                "min_kernel_version": "1.0.0",
                "reason": "initial install",
            },
            headers=headers,
        )
        assert register_response.status_code == 201

        response = client.post(
            "/api/v1/packs/test.installed_only_http/deactivate",
            json={"reason": "withdraw"},
            headers=headers,
        )

    assert response.status_code == 409


def test_getting_an_unregistered_pack_returns_404(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    headers = {"Authorization": f"Bearer {_token(['maintainer'])}"}

    with TestClient(app) as client:
        response = client.get("/api/v1/packs/test.never_existed_http", headers=headers)

    assert response.status_code == 404


def test_a_viewer_cannot_manage_or_read_packs(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    headers = {"Authorization": f"Bearer {_token(['viewer'])}"}

    with TestClient(app) as client:
        register_response = client.post(
            "/api/v1/packs",
            json={
                "pack_id": "test.viewer_denied",
                "version": "1.0.0",
                "manifest": {},
                "sdk_version": "1.0.0",
                "min_kernel_version": "1.0.0",
                "reason": "initial install",
            },
            headers=headers,
        )
        get_response = client.get("/api/v1/packs/test.viewer_denied", headers=headers)

    assert register_response.status_code == 403
    assert get_response.status_code == 403
