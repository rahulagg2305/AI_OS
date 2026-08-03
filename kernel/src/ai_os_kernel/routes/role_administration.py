"""The real, Bearer-authenticated HTTP route (``P03-S05-M14-T08``) that
lets an authorized operator grant/revoke an ``approver:<class>`` role
for a real principal — closing the last disclosed gap in the Human
Approval RBAC thread: :mod:`ai_os_kernel.security_manager.
role_administration`'s own module docstring named
``RoleAdministrationService`` as "service-layer only, no HTTP route" the
moment it was built (``P03-S05-M14-T07``).

**Authentication only at the route boundary — the identical shape
:mod:`ai_os_kernel.routes.approvals` (``P03-S03-M30-T06``) already
established, not a new pattern.** This route uses
:func:`~ai_os_kernel.security_manager.authenticate` directly (real
Bearer/JWT verification, no flat permission check) and defers the
entire ``admin``-only authorization decision to
:class:`~ai_os_kernel.security_manager.role_administration.
RoleAdministrationService`, which already gets this right — a flat
``require_permission()`` check would be redundant at best (``admin``
already bypasses every flat permission) and, per the approvals route's
own real, disclosed finding, flat checks cannot express this codebase's
class-scoped roles reliably; reusing the service's own real gate avoids
inventing a second, parallel authorization mechanism for the same
question.

**Revoke is a body-carrying ``DELETE``, not a path-parameter one.** A
role string (``approver:release``) is a legitimate resource identifier,
but embedding it in a URL path invites needless colon-encoding
questions; the identical (``principal_id``, ``role``, ``reason``) shape
:meth:`RoleAdministrationService.grant` already takes is reused as the
request body for both endpoints instead — one resource path
(``/security/role-grants``), the HTTP method distinguishing grant from
revoke.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.observability.audit import SqlAuditLogWriter
from ai_os_kernel.security_manager import SecurityContext, authenticate
from ai_os_kernel.security_manager.errors import (
    RoleAdministrationNotAuthorizedError,
    RoleGrantAlreadyActiveError,
    RoleGrantNotActiveError,
)
from ai_os_kernel.security_manager.role_administration import (
    RoleAdministrationService,
    RoleGrant,
    SqlRoleGrantRepository,
)

router = APIRouter(prefix="/api/v1", tags=["role-administration"])


class GrantRoleRequest(BaseModel):
    """Mirrors :meth:`RoleAdministrationService.grant`'s own keyword
    arguments exactly — no parallel request shape."""

    principal_id: str
    role: str
    reason: str


class RevokeRoleRequest(BaseModel):
    """Mirrors :meth:`RoleAdministrationService.revoke`'s own keyword
    arguments exactly — no parallel request shape."""

    principal_id: str
    role: str
    reason: str


def _get_engine(request: Request) -> AsyncEngine:
    engine: AsyncEngine | None = getattr(request.app.state, "database_engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="security manager is not available")
    return engine


def _service(request: Request) -> RoleAdministrationService:
    engine = _get_engine(request)
    return RoleAdministrationService(SqlRoleGrantRepository(engine), SqlAuditLogWriter(engine))


@router.post("/security/role-grants", response_model=RoleGrant)
async def grant_role(
    request: Request,
    body: GrantRoleRequest,
    # FastAPI's own documented Depends(...) idiom, not the
    # mutable-default-argument bug B008 otherwise correctly flags — see
    # ai_os_kernel.routes.approvals's identical pattern.
    security_context: SecurityContext = Depends(authenticate),  # noqa: B008
) -> RoleGrant:
    service = _service(request)
    try:
        return await service.grant(
            principal=security_context.principal,
            target_principal_id=body.principal_id,
            role=body.role,
            reason=body.reason,
        )
    except RoleAdministrationNotAuthorizedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RoleGrantAlreadyActiveError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/security/role-grants", response_model=RoleGrant)
async def revoke_role(
    request: Request,
    body: RevokeRoleRequest = Body(...),  # noqa: B008
    security_context: SecurityContext = Depends(authenticate),  # noqa: B008
) -> RoleGrant:
    service = _service(request)
    try:
        return await service.revoke(
            principal=security_context.principal,
            target_principal_id=body.principal_id,
            role=body.role,
            reason=body.reason,
        )
    except RoleAdministrationNotAuthorizedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RoleGrantNotActiveError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
