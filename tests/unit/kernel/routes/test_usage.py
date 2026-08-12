"""Unit tests for the Usage HTTP route (ai_os_kernel.routes.usage):
``GET /api/v1/usage/tokens`` (``P06-S01-M36-T04``, api_architecture.md
§6.4).

No real database and no real network: ``AIOS_DATABASE_URL`` is
deliberately left unset, so ``_lifespan`` never attaches a real
``token_usage_views`` — these tests exercise the
authentication/authorization boundary in front of it plus the honest 503
when the aggregation is unavailable. The real end-to-end path (real
Postgres, real aggregated cache-split numbers) is covered by
``tests/integration/evaluation_engine/test_token_usage_views.py``.

Mirrors ``test_evaluation.py`` deliberately: this route reuses the same
``evaluation:read`` permission over the same ``evaluation.llm_calls``
data, so it should be provably gated the same way rather than merely
assumed to be.
"""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from ai_os_kernel.bootstrap import build_app
from ai_os_kernel.configuration_manager import PlatformConfig

SCHEMA_PATH = "platform_sdk/schemas/manifest.schema.json"
_SIGNING_KEY = "unit-test-signing-key-at-least-32-bytes-long"  # gitleaks:allow
_ROUTE_PATH = "/api/v1/usage/tokens"


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

    # Authentication and authorization both passed, so the 503 is the
    # honest "no aggregation configured" answer, not the security
    # boundary refusing.
    assert response.status_code == 503
    body = response.json()
    assert body["detail"] == "usage reporting is not available"
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
    """`evaluation:read` is granted to every role (permissions.py), and
    this read-only analytical report reuses it rather than inventing a
    usage-specific permission §5's own table does not document."""
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    monkeypatch.delenv("AIOS_DATABASE_URL", raising=False)
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.get(_ROUTE_PATH, headers={"Authorization": f"Bearer {_token(roles)}"})

    # 503 (not 403) proves authorization passed for this role.
    assert response.status_code == 503


def test_the_route_is_published_in_the_openapi_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    """The documented path must be the real path — api_architecture.md
    §6.4 names `/api/v1/usage/tokens` exactly, and previous steps in this
    module have repeatedly had to disclose shape deviations. This one has
    none, and that is asserted rather than claimed."""
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    schema = app.openapi()

    assert _ROUTE_PATH in schema["paths"]
    assert "get" in schema["paths"][_ROUTE_PATH]
