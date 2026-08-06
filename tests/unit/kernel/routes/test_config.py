"""Unit tests for the configuration HTTP routes
(ai_os_kernel.routes.config): GET /config, PATCH /config, GET
/config/flags.

No real database and no real network: ``AIOS_DATABASE_URL`` is
deliberately left unset in every test here, so ``_lifespan`` never
attaches a real ``configuration_manager``/``runtime_override_store``/
``config_change_writer`` — these tests exercise only the
authentication/authorization boundary in front of them, plus the
honest 503 each returns when unavailable, the identical shape
``tests/unit/kernel/routes/test_packs.py`` already establishes. The
real end-to-end path (real Postgres, a real GET/PATCH/flags sequence)
is covered by ``tests/integration/test_config_route.py``.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient

from ai_os_kernel.bootstrap import build_app
from ai_os_kernel.configuration_manager import PlatformConfig

SCHEMA_PATH = "platform_sdk/schemas/manifest.schema.json"
_SIGNING_KEY = "unit-test-config-signing-key-at-least-32-bytes"

_PATCH_BODY = {"config_key": "log_level", "new_value": "DEBUG", "reason": "debugging"}

# (method, path, json body or None) for every config route this step adds.
_ROUTES = [
    ("GET", "/api/v1/config", None),
    ("PATCH", "/api/v1/config", _PATCH_BODY),
    ("GET", "/api/v1/config/flags", None),
]


def _config() -> PlatformConfig:
    return PlatformConfig(
        env="test",
        role="api",
        capability_pack_dirs=[],
        manifest_schema_path=SCHEMA_PATH,
    )


def _token(roles: list[str]) -> str:
    claims = {
        "sub": "test-user",
        "roles": roles,
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    return jwt.encode(claims, _SIGNING_KEY, algorithm="HS256")


def _call(
    client: TestClient,
    method: str,
    path: str,
    body: dict[str, object] | None,
    *,
    headers: dict[str, str] | None = None,
) -> Any:
    if method == "GET":
        return client.get(path, headers=headers)
    return client.patch(path, json=body, headers=headers)


@pytest.mark.parametrize("method,path,body", _ROUTES)
def test_a_config_route_without_a_bearer_token_is_rejected(
    method: str, path: str, body: dict[str, object] | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with TestClient(app) as client:
        response = _call(client, method, path, body)

    assert response.status_code == 401


@pytest.mark.parametrize("method,path,body", _ROUTES)
def test_a_config_route_for_a_principal_lacking_config_permissions_is_denied(
    method: str, path: str, body: dict[str, object] | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with TestClient(app) as client:
        # viewer's documented grants never mention configuration at all
        # (see permissions.py) — neither config:read nor config:manage.
        response = _call(
            client, method, path, body, headers={"Authorization": f"Bearer {_token(['viewer'])}"}
        )

    assert response.status_code == 403


@pytest.mark.parametrize("method,path,body", _ROUTES)
def test_a_config_route_reports_itself_unavailable_without_a_real_database(
    method: str, path: str, body: dict[str, object] | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    monkeypatch.delenv("AIOS_DATABASE_URL", raising=False)
    app = build_app(_config())

    with TestClient(app) as client:
        # maintainer holds both config:read and config:manage —
        # authorization passes for every route in _ROUTES regardless of
        # which permission it individually requires.
        response = _call(
            client,
            method,
            path,
            body,
            headers={"Authorization": f"Bearer {_token(['maintainer'])}"},
        )

    assert response.status_code == 503


def test_bare_test_client_never_configures_the_config_routes_security() -> None:
    app = build_app(_config())
    client = TestClient(app)

    response = client.get("/api/v1/config")

    assert response.status_code == 503
