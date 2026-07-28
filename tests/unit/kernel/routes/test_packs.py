"""Unit tests for the Capability Manager's pack lifecycle HTTP routes
(ai_os_kernel.routes.packs): register/install, activate, deactivate,
and get one pack.

No real database and no real network: ``AIOS_DATABASE_URL`` is
deliberately left unset in every test here, so ``_lifespan`` never
attaches a real ``pack_lifecycle_repository`` — these tests exercise
only the authentication/authorization boundary in front of it, plus the
honest 503 it returns when the Capability Manager itself is
unavailable. The real end-to-end path (real Postgres, a real
register/activate/deactivate/get sequence) is covered by
``tests/integration/test_packs_route.py``.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient

from ai_os_kernel.bootstrap import build_app
from ai_os_kernel.configuration_manager import PlatformConfig

SCHEMA_PATH = "platform_sdk/schemas/manifest.schema.json"
_SIGNING_KEY = "unit-test-signing-key-at-least-32-bytes-long"

_REGISTER_BODY = {
    "pack_id": "test.pack",
    "version": "1.0.0",
    "manifest": {},
    "sdk_version": "1.0.0",
    "min_kernel_version": "1.0.0",
    "reason": "initial install",
}
_ACTION_BODY = {"reason": "because"}

# (method, path, json body or None) for every pack route this step adds.
_ROUTES = [
    ("POST", "/api/v1/packs", _REGISTER_BODY),
    ("POST", "/api/v1/packs/test.pack/activate", _ACTION_BODY),
    ("POST", "/api/v1/packs/test.pack/deactivate", _ACTION_BODY),
    ("GET", "/api/v1/packs/test.pack", None),
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
    return client.post(path, json=body, headers=headers)


@pytest.mark.parametrize("method,path,body", _ROUTES)
def test_a_pack_route_without_a_bearer_token_is_rejected(
    method: str, path: str, body: dict[str, object] | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with TestClient(app) as client:
        response = _call(client, method, path, body)

    assert response.status_code == 401


@pytest.mark.parametrize("method,path,body", _ROUTES)
def test_a_pack_route_for_a_principal_lacking_pack_permissions_is_denied(
    method: str, path: str, body: dict[str, object] | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with TestClient(app) as client:
        # viewer's documented grants never mention packs at all (see
        # permissions.py) — neither pack:read nor pack:manage.
        response = _call(
            client, method, path, body, headers={"Authorization": f"Bearer {_token(['viewer'])}"}
        )

    assert response.status_code == 403


@pytest.mark.parametrize("method,path,body", _ROUTES)
def test_a_pack_route_reports_the_capability_manager_as_unavailable_without_a_real_database(
    method: str, path: str, body: dict[str, object] | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    monkeypatch.delenv("AIOS_DATABASE_URL", raising=False)
    app = build_app(_config())

    with TestClient(app) as client:
        # maintainer holds both pack:read and pack:manage — authorization
        # passes for every route in _ROUTES regardless of which
        # permission it individually requires.
        response = _call(
            client,
            method,
            path,
            body,
            headers={"Authorization": f"Bearer {_token(['maintainer'])}"},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "capability manager is not available"


def test_bare_test_client_never_configures_the_pack_routes_security() -> None:
    app = build_app(_config())
    client = TestClient(app)

    response = client.get("/api/v1/packs/test.pack")

    assert response.status_code == 503
