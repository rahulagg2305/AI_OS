"""RFC 9457 (`application/problem+json`) error responses — the real,
consistent shape `api_architecture.md` §8 documents, replacing FastAPI's
default `{"detail": ...}` body (`P06-S01-M36-T02`).

**Every route in this codebase raises a plain `fastapi.HTTPException`
today — confirmed by direct inspection, no route imports `ai_os_sdk`'s
own `AiOsError` hierarchy at all.** Migrating every raise site onto
`AiOsError` so each could carry its own real, catalogued `error_code`
(`platform_sdk.md` §4.4's own documented field) is real, separate,
much larger work — a per-route contract change, not this ticket's own
narrow "any error -> a problem+json body" scope. This module instead
registers three real, generic exception handlers on the FastAPI `app`
itself: `HTTPException` (every current raise site), FastAPI's own
automatic `RequestValidationError` (422, with a real `violations`
array per §8: "Validation failures add a violations array"), and a
catch-all `Exception` (500, `api_architecture.md` §8: "trace_id always
present", and — separately, ADR-0016-adjacent — "never include
secrets, stack traces, SQL, or internal paths").

**`error_code`/`type`/`title` are honestly coarse, not the rich,
per-route values §8's own example shows (`"workflow.not_found"`).**
`StructuredError.error_code`'s own docstring already discloses why: "the
catalogue itself does not exist yet ... populating it needs real
producers." No route today raises anything carrying a real, specific
code to report — the input this generic handler receives is only ever
a bare HTTP status code plus whatever free-text `detail` the raise site
already wrote. `_PROBLEM_TYPES` below is therefore keyed by status code
only, deriving one real, deterministic, documented `error_code`/`type`
slug per status (`api_architecture.md` §8's own status table, verbatim)
— honest and consistent, never a fabricated per-route classification
this handler cannot actually know. A future step giving individual
routes their own `AiOsError`-derived codes is real, valuable, disclosed
follow-up work, not attempted here.

**`trace_id` is always real** — `~ai_os_kernel.observability.trace.
get_trace_id`, the same per-request id
:class:`~ai_os_kernel.observability.middleware.TraceIdMiddleware`
already binds before any route handler (or its own exception) runs.
Falls back to a freshly generated one only if genuinely unbound (no
middleware in front of this handler in some exotic caller) — never a
fixed placeholder string.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ai_os_kernel.observability.trace import generate_trace_id, get_trace_id

# api_architecture.md §8's own status table, verbatim — the one real,
# documented source for these three fields. Not exhaustive of every
# HTTP status a route could ever raise; `_problem_type_for_status`
# falls back to a real, honestly-generic entry for anything else.
_PROBLEM_TYPES: dict[int, tuple[str, str, str]] = {
    # status -> (type slug, title, error_code)
    400: ("malformed-request", "Malformed request", "http.malformed_request"),
    401: ("unauthenticated", "Unauthenticated", "http.unauthenticated"),
    403: ("forbidden", "Forbidden", "http.forbidden"),
    404: ("not-found", "Not found", "http.not_found"),
    409: ("conflict", "State conflict", "http.conflict"),
    422: ("invalid", "Semantically invalid", "http.invalid"),
    429: ("rate-limited", "Rate limited", "http.rate_limited"),
    500: ("internal-error", "Internal error", "http.internal_error"),
    503: ("unavailable", "Not ready or shutting down", "http.unavailable"),
}

_PROBLEM_BASE_URI = "https://ai-os.dev/problems"


def _problem_type_for_status(status_code: int) -> tuple[str, str, str]:
    return _PROBLEM_TYPES.get(
        status_code, (f"http-{status_code}", "Unclassified error", f"http.status_{status_code}")
    )


def _build_problem_body(
    *,
    status_code: int,
    detail: str,
    instance: str,
    violations: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    slug, title, error_code = _problem_type_for_status(status_code)
    body: dict[str, Any] = {
        "type": f"{_PROBLEM_BASE_URI}/{slug}",
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": instance,
        "error_code": error_code,
        "trace_id": get_trace_id() or generate_trace_id(),
    }
    if violations:
        body["violations"] = violations
    return body


def build_problem_response(
    *,
    status_code: int,
    detail: str,
    instance: str,
    violations: list[dict[str, str]] | None = None,
) -> JSONResponse:
    """The same real RFC 9457 body :func:`register_problem_detail_handlers`'s
    own three handlers build, exposed for the one other real caller
    that cannot go through FastAPI's own exception-handler dispatch:
    :class:`~ai_os_kernel.routes.idempotency.IdempotencyKeyMiddleware`'s
    own 409 conflict response. A `BaseHTTPMiddleware` wraps *outside*
    FastAPI's own exception-handling middleware (a real, verified
    Starlette/FastAPI limitation, not an assumption) — an
    `HTTPException` raised directly inside a middleware's own
    `dispatch()` never reaches `@app.exception_handler`. Reusing this
    one real builder, rather than a second, parallel one, is what keeps
    every problem+json body genuinely consistent regardless of which
    layer produced it."""
    body = _build_problem_body(
        status_code=status_code, detail=detail, instance=instance, violations=violations
    )
    return JSONResponse(
        status_code=status_code, content=body, media_type="application/problem+json"
    )


def register_problem_detail_handlers(app: FastAPI) -> None:
    """Registers the three real handlers on `app` — called once, from
    :func:`~ai_os_kernel.bootstrap.build_app`."""

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        body = _build_problem_body(
            status_code=exc.status_code, detail=detail, instance=request.url.path
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=body,
            headers=exc.headers,
            media_type="application/problem+json",
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        violations = [
            {"field": ".".join(str(part) for part in error["loc"]), "message": error["msg"]}
            for error in exc.errors()
        ]
        return build_problem_response(
            status_code=422,
            detail="Request validation failed.",
            instance=request.url.path,
            violations=violations,
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected_exception(request: Request, exc: Exception) -> JSONResponse:
        # Never the real exception message -- api_architecture.md §8:
        # "never include secrets, stack traces, SQL, or internal
        # paths." A real, correlatable trace_id is how this gets
        # diagnosed instead.
        return build_problem_response(
            status_code=500, detail="An internal error occurred.", instance=request.url.path
        )
