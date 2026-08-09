"""Unit tests for the Cost and Quality Views HTTP route
(ai_os_kernel.routes.evaluation): ``GET /api/v1/evaluation/cost-and-quality``
(``P06-S03-M39-T03``).

No real database and no real network: ``AIOS_DATABASE_URL`` is
deliberately left unset in every test here, so ``_lifespan`` never
attaches a real ``cost_and_quality_views`` — these tests exercise only
the authentication/authorization boundary in front of it, plus the
honest 503 it returns when the aggregation itself is unavailable. The
real end-to-end path (real Postgres, real aggregated numbers) is
covered by ``tests/integration/evaluation_engine/test_cost_and_quality_views.py``.
"""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from ai_os_kernel.bootstrap import build_app
from ai_os_kernel.configuration_manager import PlatformConfig

SCHEMA_PATH = "platform_sdk/schemas/manifest.schema.json"
_SIGNING_KEY = "unit-test-signing-key-at-least-32-bytes-long"
_ROUTE_PATH = "/api/v1/evaluation/cost-and-quality"


def _config() -> PlatformConfig:
    return PlatformConfig(
        env="test",
        role="api",
        capability_pack_dirs=[],
        manifest_schema_path=SCHEMA_PATH,
    )


def _token(roles: list[str], *, signing_key: str = _SIGNING_KEY) -> str:
    claims = {
        "sub": "test-user",
        "roles": roles,
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    return jwt.encode(claims, signing_key, algorithm="HS256")


def test_a_missing_bearer_token_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.get(_ROUTE_PATH)

    assert response.status_code == 401


def test_a_principal_lacking_evaluation_read_is_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with TestClient(app) as client:
        # A role that grants nothing (see permissions_for_roles: an
        # unrecognised role name contributes no permissions).
        response = client.get(
            _ROUTE_PATH, headers={"Authorization": f"Bearer {_token(['nobody'])}"}
        )

    assert response.status_code == 403


def test_an_authorized_principal_gets_a_clear_reporting_unavailable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    monkeypatch.delenv("AIOS_DATABASE_URL", raising=False)
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.get(
            _ROUTE_PATH, headers={"Authorization": f"Bearer {_token(['viewer'])}"}
        )

    # viewer grants evaluation:read (see permissions.py) — authentication
    # and authorization both passed, so the 503 comes from there being no
    # real cost_and_quality_views configured, not from the security
    # boundary.
    assert response.status_code == 503
    body = response.json()
    assert body["detail"] == "evaluation reporting is not available"
    # P06-S01-M36-T02's own real RFC 9457 problem+json body, applied
    # here for free via the globally registered exception handler.
    assert response.headers["content-type"] == "application/problem+json"
    assert body["type"] == "https://ai-os.dev/problems/unavailable"
    assert body["status"] == 503
    assert body["instance"] == _ROUTE_PATH


@pytest.mark.parametrize(
    "roles", [["viewer"], ["operator"], ["approver"], ["maintainer"], ["admin"]]
)
def test_every_real_role_is_granted_evaluation_read(
    roles: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    monkeypatch.delenv("AIOS_DATABASE_URL", raising=False)
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.get(_ROUTE_PATH, headers={"Authorization": f"Bearer {_token(roles)}"})

    # Every one of the 5 real roles was granted evaluation:read this step
    # (authentication_authorization.md §4.2 already named "experiments,
    # gate results" under viewer's own grant) — so every role reaches the
    # same 503 (engine unavailable), never a 403.
    assert response.status_code == 503
