"""Real, persisted role administration (``P03-S05-M14-T07``) — closes
the gap named repeatedly across the Human Approval work
(``P03-S05-M14-T04`` through ``T06``): every role has come solely from
a bearer token's own ``roles`` claim
(:mod:`ai_os_kernel.security_manager.token_verifier`), with no
persisted way to grant or revoke one — an operator who wants to grant
``approver:release`` to a real principal had to hand-mint a new JWT
naming it, the "manual-JWT-crafting gap" this ticket's own name closes.

**Investigated first, not assumed: augment the token's own claimed
roles, never replace them.** ``JWTBearerTokenVerifier``'s existing
behaviour — a token's own ``roles`` claim genuinely grants those roles
— is real, tested, and depended on by every existing route and test;
changing that would be a real regression, not an improvement. Instead,
:class:`RoleAdministrationService`'s own real, persisted grants are
*unioned* with whatever a token already claims, at the one real call
site that needs the class-scoped ``approver:<approval_class>`` check
(:class:`~ai_os_kernel.workflow_engine.human_approval.ApprovalService`).
A principal with no persisted grants at all behaves exactly as before
this step — "absent means unaffected," the identical shape every other
optional capability in this codebase already establishes.

**Scoped to the ``approver:<class>`` role family this ticket's own
Input/Output names — not a general RBAC administration system.**
``permissions_for_roles()``'s flat 5-role dict (``viewer``/``operator``/
``maintainer``/``admin``, and the un-classed half of ``approver``)
still comes solely from the token, unchanged; only the class-scoped
half — the one role family with no flat-permission equivalent at all
(:mod:`ai_os_kernel.security_manager.permissions`'s own docstring) —
gains real, persisted administration. Building this generally, for
every role, would be real, speculative scope beyond what this ticket
asks for.

**Who may grant/revoke: reuses ``admin`` unchanged, the identical
bypass :func:`~ai_os_kernel.security_manager.approval_authorization.
is_authorized_to_decide_approval` already grants** — authentication_authorization.md
§4.2's own role table names only ``admin`` in connection with "role
assignment" at all ("All, including security policy, role assignment,
and secret management. Every action audited."), the same reading
:mod:`ai_os_kernel.security_manager.permissions`'s own docstring
already gives ``secret:access``. No new permission, no parallel
authorization mechanism — a direct ``ADMIN_ROLE in principal.roles``
check, imported from :mod:`~ai_os_kernel.security_manager.
approval_authorization` rather than a second literal ``"admin"``.

**Audit reuses the existing, hash-chained ``governance.audit_log``
writer** — the identical "authorization decisions get audited, real
DB writes too, allowed and denied alike" shape
:class:`~ai_os_kernel.secrets_manager.access_broker.AccessBroker`
already establishes, mirrored here almost exactly: an unauthorized
attempt is audited as ``DENIED`` *before* being refused; a real
grant/revoke is audited as ``SUCCESS`` after the real write commits.

**Service-layer only, no HTTP route — the identical "Workflow-Engine-
level mechanism first, HTTP wiring is separate, later work" precedent
``P03-S05-M14-T04``/``T05`` already established for Human Approval
itself** (``P03-S03-M30-T06`` added that HTTP route as its own, later
step). Real, tested, callable — not wired to any transport yet.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.observability.audit import AuditLogWriter, AuditOutcome
from ai_os_kernel.security_manager.approval_authorization import ADMIN_ROLE
from ai_os_kernel.security_manager.errors import (
    RoleAdministrationNotAuthorizedError,
    RoleGrantAlreadyActiveError,
    RoleGrantNotActiveError,
)
from ai_os_kernel.security_manager.ids import new_role_grant_id
from ai_os_kernel.security_manager.models import Principal
from ai_os_kernel.security_manager.schema import role_grants


class RoleGrant(BaseModel):
    """One ``security.role_grants`` row (data_model.md §9a.1)."""

    model_config = ConfigDict(frozen=True)

    grant_id: str
    principal_id: str
    role: str
    status: str
    granted_by: str
    granted_reason: str
    granted_at: datetime
    revoked_by: str | None
    revoked_reason: str | None
    revoked_at: datetime | None


class RoleGrantRepository(Protocol):
    """Persistence boundary for ``security.role_grants`` — the seam a
    fake implementation substitutes in unit tests (ADR-0004:
    interface-driven, configuration over code)."""

    async def active_roles_for(self, principal_id: str) -> frozenset[str]: ...

    async def grant(
        self, *, principal_id: str, role: str, granted_by: str, reason: str
    ) -> RoleGrant: ...

    async def revoke(
        self, *, principal_id: str, role: str, revoked_by: str, reason: str
    ) -> RoleGrant: ...


class SqlRoleGrantRepository:
    """The only implementation of :class:`RoleGrantRepository` at this
    stage: SQLAlchemy 2.0 Core against Postgres (ADR-0011)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def active_roles_for(self, principal_id: str) -> frozenset[str]:
        """A plain, unguarded read — the identical "no leasing/locking
        here" shape every other real read in this codebase already
        establishes; the real exclusivity guard for the one write that
        matters (:meth:`grant`'s own atomic partial unique index) lives
        there, not here."""
        async with self._engine.connect() as connection:
            result = await connection.execute(
                sa.select(role_grants.c.role).where(
                    role_grants.c.principal_id == principal_id,
                    role_grants.c.status == "active",
                )
            )
            return frozenset(row.role for row in result)

    async def grant(
        self, *, principal_id: str, role: str, granted_by: str, reason: str
    ) -> RoleGrant:
        """Inserts a real, active grant — refuses (never silently
        no-ops) if one already exists for this exact ``(principal_id,
        role)`` pair, enforced atomically by ``security.role_grants``'s
        own partial unique index, never a separate, race-prone
        pre-check read."""
        grant_id = new_role_grant_id()
        granted_at = datetime.now(UTC)
        try:
            async with self._engine.begin() as connection:
                result = await connection.execute(
                    sa.insert(role_grants)
                    .values(
                        grant_id=grant_id,
                        principal_id=principal_id,
                        role=role,
                        status="active",
                        granted_by=granted_by,
                        granted_reason=reason,
                        granted_at=granted_at,
                        revoked_by=None,
                        revoked_reason=None,
                        revoked_at=None,
                    )
                    .returning(*role_grants.columns)
                )
                row = result.mappings().one()
        except sa.exc.IntegrityError as exc:
            raise RoleGrantAlreadyActiveError(
                f"principal {principal_id!r} already has an active grant of role {role!r}"
            ) from exc
        return RoleGrant.model_validate(dict(row))

    async def revoke(
        self, *, principal_id: str, role: str, revoked_by: str, reason: str
    ) -> RoleGrant:
        """Transitions a real, active grant to ``revoked`` — guarded by
        ``WHERE status = 'active'``: a revoke against an already-revoked
        (or never-granted) pair affects zero rows, raising
        :class:`RoleGrantNotActiveError` rather than silently
        no-opping, the identical guarded-``UPDATE`` shape
        :meth:`~ai_os_kernel.workflow_engine.human_approval.
        SqlApprovalRepository.decide` already establishes for the
        identical "act on real, current state or refuse" reason."""
        revoked_at = datetime.now(UTC)
        async with self._engine.begin() as connection:
            result = await connection.execute(
                sa.update(role_grants)
                .where(
                    role_grants.c.principal_id == principal_id,
                    role_grants.c.role == role,
                    role_grants.c.status == "active",
                )
                .values(
                    status="revoked",
                    revoked_by=revoked_by,
                    revoked_reason=reason,
                    revoked_at=revoked_at,
                )
                .returning(*role_grants.columns)
            )
            row = result.mappings().one_or_none()
        if row is None:
            raise RoleGrantNotActiveError(
                f"principal {principal_id!r} has no active grant of role {role!r} to revoke"
            )
        return RoleGrant.model_validate(dict(row))


class RoleAdministrationService:
    """The real authorization + audit boundary in front of
    :class:`RoleGrantRepository` — mirrors
    :class:`~ai_os_kernel.workflow_engine.human_approval.ApprovalService`'s
    own shape (a thin service in front of a pure-persistence
    repository) and :class:`~ai_os_kernel.secrets_manager.access_broker.
    AccessBroker`'s own shape (authorize, then audit either way) at
    once — see this module's own docstring for the full reasoning
    behind both halves.
    """

    def __init__(
        self, role_grant_repository: RoleGrantRepository, audit_log: AuditLogWriter
    ) -> None:
        self._role_grant_repository = role_grant_repository
        self._audit_log = audit_log

    async def grant(
        self,
        *,
        principal: Principal,
        target_principal_id: str,
        role: str,
        reason: str,
    ) -> RoleGrant:
        """``principal`` (the caller) must hold ``admin``; the real
        grant is then made for ``target_principal_id``, and audited
        either way — denied or succeeded — before returning or
        raising."""
        await self._require_admin(
            principal,
            event_type="security.role_grant.denied",
            detail={
                "target_principal_id": target_principal_id,
                "role": role,
            },
        )

        granted = await self._role_grant_repository.grant(
            principal_id=target_principal_id,
            role=role,
            granted_by=principal.principal_id,
            reason=reason,
        )
        await self._audit_log.record(
            event_type="security.role_granted",
            principal_id=principal.principal_id,
            principal_type=principal.principal_type,
            outcome=AuditOutcome.SUCCESS,
            detail={"target_principal_id": target_principal_id, "role": role, "reason": reason},
            resource_type="principal",
            resource_id=target_principal_id,
        )
        return granted

    async def revoke(
        self,
        *,
        principal: Principal,
        target_principal_id: str,
        role: str,
        reason: str,
    ) -> RoleGrant:
        """The identical shape as :meth:`grant`, for revocation."""
        await self._require_admin(
            principal,
            event_type="security.role_revoke.denied",
            detail={
                "target_principal_id": target_principal_id,
                "role": role,
            },
        )

        revoked = await self._role_grant_repository.revoke(
            principal_id=target_principal_id,
            role=role,
            revoked_by=principal.principal_id,
            reason=reason,
        )
        await self._audit_log.record(
            event_type="security.role_revoked",
            principal_id=principal.principal_id,
            principal_type=principal.principal_type,
            outcome=AuditOutcome.SUCCESS,
            detail={"target_principal_id": target_principal_id, "role": role, "reason": reason},
            resource_type="principal",
            resource_id=target_principal_id,
        )
        return revoked

    async def _require_admin(
        self, principal: Principal, *, event_type: str, detail: dict[str, str]
    ) -> None:
        if ADMIN_ROLE in principal.roles:
            return
        await self._audit_log.record(
            event_type=event_type,
            principal_id=principal.principal_id,
            principal_type=principal.principal_type,
            outcome=AuditOutcome.DENIED,
            detail=detail,
            resource_type="principal",
            resource_id=detail["target_principal_id"],
        )
        raise RoleAdministrationNotAuthorizedError(
            f"principal {principal.principal_id!r} (roles: {sorted(principal.roles)}) is not "
            f"authorized to administer roles — requires 'admin'"
        )
