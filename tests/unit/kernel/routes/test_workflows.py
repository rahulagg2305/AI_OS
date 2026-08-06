"""Unit tests for the Workflow Engine's HTTP routes
(ai_os_kernel.routes.workflows): the previous step's authenticated
write (``POST /api/v1/workflows``) plus this step's three read-only
routes (``GET /api/v1/workflows/{id}``, ``.../steps``, ``.../events``).

No real database and no real network: ``AIOS_DATABASE_URL`` is
deliberately left unset in every test here, so ``_lifespan`` never
attaches a real ``trigger_prompted_agent_workflow`` or
``workflow_instance_repository`` — these tests exercise only the
authentication/authorization boundary in front of both, plus the
honest 503 each returns when the workflow engine itself is
unavailable. The real end-to-end path (real Postgres, real reads after
a real write) is covered by ``tests/integration/test_workflows_route.py``
and its live counterpart.
"""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from ai_os_kernel.bootstrap import build_app
from ai_os_kernel.configuration_manager import PlatformConfig

SCHEMA_PATH = "platform_sdk/schemas/manifest.schema.json"
_SIGNING_KEY = "unit-test-signing-key-at-least-32-bytes-long"
_READ_ROUTE_PATHS = [
    "/api/v1/workflows",
    "/api/v1/workflows/wf_does_not_exist",
    "/api/v1/workflows/wf_does_not_exist/steps",
    "/api/v1/workflows/wf_does_not_exist/events",
]


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
    # invariant test) — app.state.token_verifier never gets set, so this
    # exercises the dependency's own getattr(..., None) fallback, not
    # just the "secret unset" degrade path below.
    app = build_app(_config())
    client = TestClient(app)

    response = client.post("/api/v1/workflows", json={"inputs": {}})

    assert response.status_code == 503


def test_an_unconfigured_signing_secret_denies_every_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", raising=False)
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/workflows",
            json={"inputs": {}},
            headers={"Authorization": f"Bearer {_token(['operator'])}"},
        )

    assert response.status_code == 503


def test_a_missing_bearer_token_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.post("/api/v1/workflows", json={"inputs": {}})

    assert response.status_code == 401


def test_an_invalid_bearer_token_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/workflows",
            json={"inputs": {}},
            headers={"Authorization": "Bearer not-a-real-token"},
        )

    assert response.status_code == 401


def test_a_principal_lacking_workflow_start_is_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/workflows",
            json={"inputs": {}},
            headers={"Authorization": f"Bearer {_token(['viewer'])}"},
        )

    assert response.status_code == 403


def test_an_authorized_principal_reaches_the_route_and_gets_a_clear_engine_unavailable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    monkeypatch.delenv("AIOS_DATABASE_URL", raising=False)
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/workflows",
            json={"inputs": {}},
            headers={"Authorization": f"Bearer {_token(['operator'])}"},
        )

    # Authentication and authorization both passed — the 503 comes from
    # the Workflow Engine itself being unavailable (no real database
    # configured in this unit test), not from the security boundary.
    assert response.status_code == 503
    body = response.json()
    assert body["detail"] == "workflow engine is not available"
    # P06-S01-M36-T02's own real proof: every error is now a real,
    # consistent RFC 9457 body, not just FastAPI's bare {"detail": ...}.
    assert response.headers["content-type"] == "application/problem+json"
    assert body["type"] == "https://ai-os.dev/problems/unavailable"
    assert body["title"] == "Not ready or shutting down"
    assert body["status"] == 503
    assert body["instance"] == "/api/v1/workflows"
    assert body["error_code"] == "http.unavailable"
    assert isinstance(body["trace_id"], str) and body["trace_id"]


@pytest.mark.parametrize("path", _READ_ROUTE_PATHS)
def test_a_read_route_without_a_bearer_token_is_rejected(
    path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.get(path)

    assert response.status_code == 401


@pytest.mark.parametrize("path", _READ_ROUTE_PATHS)
def test_a_read_route_for_a_principal_lacking_workflow_read_is_denied(
    path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with TestClient(app) as client:
        # A role that grants nothing (see permissions_for_roles: an
        # unrecognised role name contributes no permissions).
        response = client.get(path, headers={"Authorization": f"Bearer {_token(['nobody'])}"})

    assert response.status_code == 403


@pytest.mark.parametrize("path", _READ_ROUTE_PATHS)
def test_a_read_route_reports_the_workflow_engine_as_unavailable_without_a_real_database(
    path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    monkeypatch.delenv("AIOS_DATABASE_URL", raising=False)
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.get(path, headers={"Authorization": f"Bearer {_token(['viewer'])}"})

    # workflow:read (granted to viewer) passed authorization — the 503
    # comes from there being no real workflow_instance_repository, not
    # from the security boundary.
    assert response.status_code == 503
    assert response.json()["detail"] == "workflow engine is not available"


@pytest.mark.parametrize("limit", [0, -1, 101])
def test_list_workflows_rejects_a_limit_outside_the_allowed_range(
    limit: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    # Never connected — engine construction is lazy (see test_bootstrap.py's
    # identical technique) — needed so `_get_repository` succeeds and this
    # test genuinely exercises FastAPI's own `Query(gt=0, le=...)`
    # validation, rather than always losing a race against the repository
    # dependency's own 503 when no database is configured at all.
    monkeypatch.setenv("AIOS_DATABASE_URL", "postgresql+asyncpg://fake:fake@127.0.0.1:1/fake")
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/workflows",
            params={"limit": limit},
            headers={"Authorization": f"Bearer {_token(['viewer'])}"},
        )

    assert response.status_code == 422
    # P06-S01-M36-T02's own real proof: a genuine FastAPI
    # RequestValidationError now also gets the real RFC 9457 shape,
    # with a real violations array naming the actual invalid field.
    body = response.json()
    assert response.headers["content-type"] == "application/problem+json"
    assert body["status"] == 422
    assert body["error_code"] == "http.invalid"
    violations = body["violations"]
    assert len(violations) == 1
    assert violations[0]["field"] == "query.limit"
