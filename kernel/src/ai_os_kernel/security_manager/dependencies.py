"""FastAPI dependency wiring for authentication + authorization —
composed here, not scattered across route modules, mirroring
:mod:`ai_os_kernel.routes.health` reading services off ``request.app.state``
rather than each route reconstructing them.

Two-stage dependency chain: :func:`authenticate` verifies the bearer
token and computes a :class:`~ai_os_kernel.security_manager.models.SecurityContext`;
:func:`require_permission` wraps it with one flat permission check. Both
fail closed (401/403/503) rather than default-allow, per
authentication_authorization.md §3.3/§4.3.

**``authenticate`` is exported directly (``P03-S03-M30-T06``), for a
route that needs real Bearer/JWT authentication but no *flat*
permission check — full authorization deferred entirely to a
resource-specific check of its own.** :mod:`ai_os_kernel.routes.approvals`
is the first such caller: whether a principal may decide *some*
approval genuinely cannot be expressed as one of this module's own
flat, exact-string role grants (a class-scoped role like
``approver:release`` does not imply the unscoped ``approver``) — see
:mod:`ai_os_kernel.security_manager.permissions`'s own docstring for
the real, concrete case this was found against.

**Real, persisted role grants now take effect here too (``P07-S02-M14-T02``,
"Full five-role model") — closing a real gap, not adding a new
mechanism.** Before this, a persisted grant of one of the five
documented roles (``viewer``/``operator``/``approver``/``maintainer``/
``admin``, via :class:`~ai_os_kernel.security_manager.role_administration.
RoleAdministrationService`) only ever took effect for
:meth:`~ai_os_kernel.workflow_engine.human_approval.ApprovalService.decide`'s
own narrow ``approver:<class>`` check — every other permission-checked
route (workflows, packs, config) read only a bearer token's own
``roles`` claim, so an admin-granted role had no real effect anywhere
else. :func:`~ai_os_kernel.security_manager.role_administration.resolve_effective_roles`
(the identical union `ApprovalService.decide` already used, now
shared, not duplicated) is applied here too, reading an optional
``request.app.state.role_grant_repository`` — ``None`` (any caller
with no real database) behaves exactly as before.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ai_os_kernel.observability import get_logger
from ai_os_kernel.security_manager.errors import InvalidTokenError
from ai_os_kernel.security_manager.models import SecurityContext
from ai_os_kernel.security_manager.permissions import permissions_for_roles
from ai_os_kernel.security_manager.role_administration import (
    RoleGrantRepository,
    resolve_effective_roles,
)
from ai_os_kernel.security_manager.token_verifier import TokenVerifier

logger = get_logger("ai_os_kernel.security_manager")

_bearer_scheme = HTTPBearer(auto_error=False)


async def authenticate(
    request: Request,
    # FastAPI's own documented Depends(...) idiom, not the
    # mutable-default-argument bug B008 otherwise correctly flags:
    # FastAPI evaluates each Depends() call once per request, not once
    # at function-definition time.
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),  # noqa: B008
) -> SecurityContext:
    verifier: TokenVerifier | None = getattr(request.app.state, "token_verifier", None)
    if verifier is None:
        # Fail closed: an unconfigured Security Manager must deny every
        # protected request, never default-allow. 503, not 401 — the
        # caller did nothing wrong; the service itself cannot
        # authenticate anyone right now.
        raise HTTPException(status_code=503, detail="security manager is not configured")

    if credentials is None:
        logger.warning("security_manager.authentication_failed", reason="missing_bearer_token")
        raise HTTPException(status_code=401, detail="missing bearer token")

    try:
        principal = await verifier.verify(credentials.credentials)
    except InvalidTokenError as exc:
        logger.warning("security_manager.authentication_failed", reason=str(exc))
        raise HTTPException(status_code=401, detail="invalid bearer token") from exc

    role_grant_repository: RoleGrantRepository | None = getattr(
        request.app.state, "role_grant_repository", None
    )
    principal = await resolve_effective_roles(principal, role_grant_repository)

    return SecurityContext(principal=principal, permissions=permissions_for_roles(principal.roles))


def require_permission(permission: str) -> Callable[..., Awaitable[SecurityContext]]:
    """Returns a FastAPI dependency that authenticates the caller and
    denies the request with ``403`` unless ``permission`` is in their
    computed :class:`SecurityContext`."""

    async def _check(
        security_context: SecurityContext = Depends(authenticate),  # noqa: B008
    ) -> SecurityContext:
        if not security_context.has_permission(permission):
            logger.warning(
                "security_manager.authorization_denied",
                principal_id=security_context.principal.principal_id,
                permission=permission,
            )
            raise HTTPException(
                status_code=403, detail=f"missing required permission: {permission}"
            )
        return security_context

    return _check
