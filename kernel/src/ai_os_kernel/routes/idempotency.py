"""`Idempotency-Key` support for mutating requests (`api_architecture.md`
§9: "mutating endpoints accept `Idempotency-Key`. Keys are retained 24
hours; a replay returns the original response. A key reused with a
different body returns `409`.") — `P06-S01-M36-T03`.

**A real ASGI middleware, not a per-route dependency** — the same
"needs to see both the request and the eventual response" shape
:class:`~ai_os_kernel.observability.middleware.TraceIdMiddleware`
already establishes. A FastAPI dependency runs *before* the route and
has no way to intercept what the handler returns; middleware's own
`call_next(request)` genuinely receives it, which is what "write the
row once the response is known" (`platform_schema.py`'s own
`idempotency_keys` docstring) requires.

**Resolves its own `principal_id`, independently of `require_permission`'s
own `Depends(authenticate)`.** By the time a route's own dependencies
run, this middleware's `dispatch()` has already had to decide whether
to short-circuit with a replay/conflict — there is no principal yet to
borrow. Reuses the identical real `TokenVerifier`
(`request.app.state.token_verifier`) and the identical `Authorization:
Bearer <token>` extraction `~ai_os_kernel.security_manager.
dependencies.authenticate` already performs — not a second, competing
authentication mechanism, the same real verification called from a
second real call site. An unauthenticated request (missing/invalid
token, or no Security Manager configured) is not idempotency-handled
at all — passed straight through unchanged, so `authenticate`'s own
dependency still refuses it normally with a real `401`/`503`.

**`request_digest` covers method + path + body, not just the body** —
stricter than §9's own words require, but a real, sensible extension:
the same client-supplied key reused against a genuinely different
route would otherwise be treated as "the same request," which it
manifestly is not.

**A stored key's own `principal_id` mismatching the current request's
is treated as a conflict (`409`), the identical consequence a body
mismatch already gets.** Not documented in so many words by §9, but a
real, deliberate extension: `key` is client-supplied and globally
unique only by convention (the schema's own primary key enforces
uniqueness on `key` alone, `principal_id` is stored but not part of
it) — silently replaying principal A's own previously-computed
response to principal B under a key B never earned would be a real
cross-principal data leak, not a narrower reading of the same rule.

**A real, disclosed, narrow race window, not solved here**: two
concurrent requests presenting the identical, brand-new key can both
pass the "not yet stored" check before either writes its own row. The
store's own `INSERT ... ON CONFLICT DO NOTHING` means only the first
write to actually commit wins the stored row; the other request still
returns its own, locally-computed response to its own caller instead
of the winner's — a real, narrow inconsistency under genuine
concurrency, not a crash, and disclosed here rather than solved with
distributed locking this ticket's own scope does not call for.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from ai_os_kernel.persistence.platform_schema import idempotency_keys
from ai_os_kernel.routes.problem_details import build_problem_response
from ai_os_kernel.security_manager.errors import InvalidTokenError
from ai_os_kernel.security_manager.token_verifier import TokenVerifier

_IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"
_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# api_architecture.md §9's own stated retention window, verbatim.
_RETENTION = timedelta(hours=24)


class SqlIdempotencyKeyStore:
    """The only implementation at this stage: SQLAlchemy 2.0 Core
    against Postgres (ADR-0011), against the real, already-migrated
    `platform.idempotency_keys` table."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def get(self, key: str) -> sa.RowMapping | None:
        now = datetime.now(UTC)
        async with self._engine.connect() as connection:
            result = await connection.execute(
                sa.select(idempotency_keys).where(
                    idempotency_keys.c.key == key, idempotency_keys.c.expires_at > now
                )
            )
            return result.mappings().one_or_none()

    async def put(
        self,
        *,
        key: str,
        principal_id: str,
        request_digest: str,
        response: dict[str, Any],
        status_code: int,
    ) -> None:
        now = datetime.now(UTC)
        async with self._engine.begin() as connection:
            await connection.execute(
                pg_insert(idempotency_keys)
                .values(
                    key=key,
                    principal_id=principal_id,
                    request_digest=request_digest,
                    response=response,
                    status_code=status_code,
                    created_at=now,
                    expires_at=now + _RETENTION,
                )
                .on_conflict_do_nothing(index_elements=["key"])
            )


async def _resolve_principal_id(request: Request) -> str | None:
    """The identical real extraction+verification
    `~ai_os_kernel.security_manager.dependencies.authenticate` already
    performs — never enforced here (a failure just means "not
    idempotency-handled," not a 401 this middleware itself decides)."""
    verifier: TokenVerifier | None = getattr(request.app.state, "token_verifier", None)
    if verifier is None:
        return None
    authorization = request.headers.get("authorization")
    if authorization is None or not authorization.lower().startswith("bearer "):
        return None
    token = authorization[len("bearer ") :]
    try:
        principal = await verifier.verify(token)
    except InvalidTokenError:
        return None
    return principal.principal_id


def _request_digest(*, method: str, path: str, body: bytes) -> str:
    hasher = hashlib.sha256()
    hasher.update(f"{method}\n{path}\n".encode())
    hasher.update(body)
    return hasher.hexdigest()


class IdempotencyKeyMiddleware(BaseHTTPMiddleware):
    """Takes no `engine` at construction — unlike most of this file's
    other real collaborators, this middleware is registered by
    :func:`~ai_os_kernel.bootstrap.build_app` before any real database
    engine exists (mirroring `TraceIdMiddleware`'s own registration
    point). Resolves `request.app.state.idempotency_key_store` lazily,
    at dispatch time, the identical `getattr(..., None)` -> "not
    available yet, pass through unchanged" shape every route's own
    `_get_repository`-style dependency already uses — set once, inside
    `_lifespan`, the moment a real engine exists."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        key = request.headers.get(_IDEMPOTENCY_KEY_HEADER)
        if key is None or request.method not in _MUTATING_METHODS:
            return await call_next(request)

        store: SqlIdempotencyKeyStore | None = getattr(
            request.app.state, "idempotency_key_store", None
        )
        if store is None:
            return await call_next(request)

        principal_id = await _resolve_principal_id(request)
        if principal_id is None:
            return await call_next(request)

        body = await request.body()
        digest = _request_digest(method=request.method, path=request.url.path, body=body)

        existing = await store.get(key)
        if existing is not None:
            if existing["request_digest"] != digest or existing["principal_id"] != principal_id:
                return build_problem_response(
                    status_code=409,
                    detail=(f"Idempotency-Key {key!r} was already used for a different request."),
                    instance=request.url.path,
                )
            return Response(
                content=_encode_json(existing["response"]),
                status_code=existing["status_code"],
                media_type="application/json",
            )

        response = await call_next(request)
        response_body = b""
        async for chunk in response.body_iterator:  # type: ignore[attr-defined]
            response_body += chunk

        if 200 <= response.status_code < 500:
            await store.put(
                key=key,
                principal_id=principal_id,
                request_digest=digest,
                response=_decode_json(response_body),
                status_code=response.status_code,
            )

        return Response(
            content=response_body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )


def _decode_json(raw: bytes) -> Any:
    return json.loads(raw) if raw else None


def _encode_json(value: Any) -> bytes:
    return json.dumps(value).encode("utf-8")
