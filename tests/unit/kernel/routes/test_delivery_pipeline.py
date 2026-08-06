"""Unit tests for the Software Engineering pack's own real HTTP trigger
route (``ai_os_kernel.routes.delivery_pipeline``): ``POST
/api/v1/workflows/se.delivery_pipeline``.

No real database and no real network: ``AIOS_DATABASE_URL`` is
deliberately left unset in every test here, so ``_lifespan`` never
attaches a real ``trigger_se_delivery_pipeline`` — these tests exercise
only the authentication/authorization boundary in front of it, plus the
honest 503 it returns when the pipeline itself is unavailable. The real
end-to-end path (real Postgres, a real trigger reached) is covered by
``tests/integration/test_delivery_pipeline_route.py`` and its opt-in
live counterpart — mirroring exactly how
``tests/unit/kernel/routes/test_workflows.py`` already splits this
same way for the platform demo route.
"""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from ai_os_kernel.bootstrap import build_app
from ai_os_kernel.configuration_manager import PlatformConfig

SCHEMA_PATH = "platform_sdk/schemas/manifest.schema.json"
_SIGNING_KEY = "unit-test-signing-key-at-least-32-bytes-long"
_ROUTE = "/api/v1/workflows/se.delivery_pipeline"


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


def test_bare_test_client_never_configures_the_security_manager() -> None:
    # No lifespan runs at all (see test_bootstrap.py's own identical
    # invariant test) — app.state.token_verifier never gets set.
    app = build_app(_config())
    client = TestClient(app)

    response = client.post(_ROUTE, json={"requirement": "x"})

    assert response.status_code == 503


def test_a_missing_bearer_token_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.post(_ROUTE, json={"requirement": "x"})

    assert response.status_code == 401


def test_an_invalid_bearer_token_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.post(
            _ROUTE,
            json={"requirement": "x"},
            headers={"Authorization": "Bearer not-a-real-token"},
        )

    assert response.status_code == 401


def test_a_principal_lacking_workflow_start_is_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.post(
            _ROUTE,
            json={"requirement": "x"},
            headers={"Authorization": f"Bearer {_token(['viewer'])}"},
        )

    assert response.status_code == 403


def test_a_missing_requirement_field_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.post(
            _ROUTE,
            json={},
            headers={"Authorization": f"Bearer {_token(['operator'])}"},
        )

    # Authentication/authorization both pass (an authorized principal) —
    # this is FastAPI's own request-body validation, proving the real
    # PipelineInput-mirroring schema is actually enforced.
    assert response.status_code == 422


def test_an_authorized_principal_reaches_the_route_and_gets_a_clear_unavailable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    monkeypatch.delenv("AIOS_DATABASE_URL", raising=False)
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.post(
            _ROUTE,
            json={"requirement": "print a friendly message"},
            headers={"Authorization": f"Bearer {_token(['operator'])}"},
        )

    # Authentication and authorization both passed — the 503 comes from
    # se.delivery_pipeline itself being unavailable (no real database
    # configured in this unit test), not from the security boundary.
    assert response.status_code == 503
    assert response.json()["detail"] == "se.delivery_pipeline is not available"


def test_an_optional_specification_field_is_accepted_alongside_requirement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-030 (`P03-S03-M30-T02`): the new, optional `specification`
    field is real request-body shape, not merely documented — proven by
    FastAPI accepting it (reaching the same honest 503, not a 422)."""
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    monkeypatch.delenv("AIOS_DATABASE_URL", raising=False)
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.post(
            _ROUTE,
            json={"requirement": "x", "specification": "- Shorten a URL\n"},
            headers={"Authorization": f"Bearer {_token(['operator'])}"},
        )

    assert response.status_code == 503
