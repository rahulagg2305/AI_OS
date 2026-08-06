"""``register_problem_detail_handlers`` — real FastAPI exception
handlers, tested against a real, minimal `FastAPI` app + `TestClient`
(a real request/response cycle through the real handler functions,
not a mock) — the identical, isolated-plumbing-test shape this
codebase already uses for `TraceIdMiddleware` itself.

The real, production-composition proof — these same handlers wired
into the real Kernel app, firing for real 503/422 responses from real
routes — lives in `test_workflows.py`'s own extended assertions
(`P06-S01-M36-T02`)."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from ai_os_kernel.observability.middleware import TraceIdMiddleware
from ai_os_kernel.routes.problem_details import register_problem_detail_handlers


class _Body(BaseModel):
    name: str


def _build_test_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(TraceIdMiddleware)
    register_problem_detail_handlers(app)

    @app.get("/boom-http/{status_code}")
    async def _boom_http(status_code: int) -> None:
        raise HTTPException(status_code=status_code, detail="a real, deliberate test failure")

    @app.get("/boom-unhandled")
    async def _boom_unhandled() -> None:
        raise RuntimeError("a secret value that must never reach the response")

    @app.post("/validate")
    async def _validate(body: _Body) -> dict[str, str]:
        return {"name": body.name}

    return app


def test_an_http_exception_becomes_a_real_rfc9457_body() -> None:
    app = _build_test_app()

    with TestClient(app) as client:
        response = client.get("/boom-http/404")

    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body == {
        "type": "https://ai-os.dev/problems/not-found",
        "title": "Not found",
        "status": 404,
        "detail": "a real, deliberate test failure",
        "instance": "/boom-http/404",
        "error_code": "http.not_found",
        "trace_id": body["trace_id"],
    }
    assert isinstance(body["trace_id"], str) and body["trace_id"]


def test_every_documented_status_gets_its_own_real_type_title_and_error_code() -> None:
    app = _build_test_app()
    expected = {
        400: ("malformed-request", "Malformed request", "http.malformed_request"),
        401: ("unauthenticated", "Unauthenticated", "http.unauthenticated"),
        403: ("forbidden", "Forbidden", "http.forbidden"),
        404: ("not-found", "Not found", "http.not_found"),
        409: ("conflict", "State conflict", "http.conflict"),
        429: ("rate-limited", "Rate limited", "http.rate_limited"),
        503: ("unavailable", "Not ready or shutting down", "http.unavailable"),
    }

    with TestClient(app) as client:
        for status_code, (slug, title, error_code) in expected.items():
            response = client.get(f"/boom-http/{status_code}")
            body = response.json()
            assert response.status_code == status_code
            assert body["type"] == f"https://ai-os.dev/problems/{slug}"
            assert body["title"] == title
            assert body["error_code"] == error_code


def test_an_undocumented_status_still_gets_a_real_honest_fallback_not_a_crash() -> None:
    app = _build_test_app()

    with TestClient(app) as client:
        response = client.get("/boom-http/418")

    body = response.json()
    assert response.status_code == 418
    assert body["type"] == "https://ai-os.dev/problems/http-418"
    assert body["error_code"] == "http.status_418"


def test_an_unhandled_exception_becomes_a_real_500_that_never_leaks_its_own_message() -> None:
    app = _build_test_app()

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom-unhandled")

    assert response.status_code == 500
    body = response.json()
    assert response.headers["content-type"] == "application/problem+json"
    assert body["status"] == 500
    assert body["error_code"] == "http.internal_error"
    # api_architecture.md §8: never leak the real exception message.
    assert "secret value" not in body["detail"]
    assert body["detail"] == "An internal error occurred."
    # api_architecture.md §8: "trace_id always present."
    assert isinstance(body["trace_id"], str) and body["trace_id"]


def test_a_validation_error_carries_a_real_violations_array() -> None:
    app = _build_test_app()

    with TestClient(app) as client:
        response = client.post("/validate", json={})

    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "http.invalid"
    violations = body["violations"]
    assert len(violations) == 1
    assert violations[0]["field"] == "body.name"
    assert violations[0]["message"]


def test_a_genuinely_valid_request_is_completely_unaffected() -> None:
    app = _build_test_app()

    with TestClient(app) as client:
        response = client.post("/validate", json={"name": "real"})

    assert response.status_code == 200
    assert response.json() == {"name": "real"}
