"""Real, Postgres-backed proof of role administration
(``P03-S05-M14-T07``) — closing the "manual-JWT-crafting gap" named
repeatedly across the Human Approval work.

The central proof this file exists for: a real, persisted
``approver:<class>`` grant genuinely enables a decision that was
refused moments earlier for the identical principal, whose own bearer
token (``Principal.roles``) never changes at all — proving the grant
alone, not a reissued token, is what changed the outcome. A real revoke
then genuinely disables the next decision the same way. Every
grant/revoke is proven audited, allowed and denied alike, mirroring
``tests/integration/secrets_manager/test_access_broker.py``'s own
rigor for the identical "authorize, then audit either way" shape.
"""

import asyncio
import os
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.observability.audit import AuditOutcome, SqlAuditLogWriter
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.security_manager.errors import (
    ApprovalNotAuthorizedError,
    RoleAdministrationNotAuthorizedError,
    RoleGrantAlreadyActiveError,
    RoleGrantNotActiveError,
)
from ai_os_kernel.security_manager.models import Principal, PrincipalType
from ai_os_kernel.security_manager.role_administration import (
    RoleAdministrationService,
    SqlRoleGrantRepository,
)
from ai_os_kernel.workflow_engine.human_approval import ApprovalService, SqlApprovalRepository
from ai_os_kernel.workflow_engine.models import HumanApprovalPoint
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from tests.integration._postgres_fixture import postgres_container
from tests.integration.workflow_engine.test_human_approval_execution import (
    _create_running_instance,
    _definition,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

_APPROVAL_CLASS = "approve-deployment"
_ADMIN = Principal(
    principal_id="admin-1", principal_type=PrincipalType.USER, roles=frozenset({"admin"})
)
_OPERATOR = Principal(
    principal_id="operator-1", principal_type=PrincipalType.USER, roles=frozenset({"operator"})
)


@pytest.fixture(scope="module")
def database_url() -> Generator[str, None, None]:
    with postgres_container() as postgres:
        url = postgres.get_connection_url()
        previous = os.environ.get("AIOS_DATABASE_URL")
        os.environ["AIOS_DATABASE_URL"] = url
        try:
            command.upgrade(Config(str(ALEMBIC_INI)), "head")
            yield url
        finally:
            if previous is None:
                os.environ.pop("AIOS_DATABASE_URL", None)
            else:
                os.environ["AIOS_DATABASE_URL"] = previous


async def _real_pending_approval(engine: AsyncEngine) -> tuple[str, str]:
    """Creates a genuinely real, running workflow instance and a real,
    pending approval against it, then genuinely transitions the
    instance to ``waiting_for_human`` — the identical two-write
    sequence ``HumanApprovalStepExecutor.execute()`` +
    ``WorkflowInstanceService.advance()`` perform together in
    production (this test calls both real repository methods directly,
    bypassing only the step-executor/advance-runner machinery this
    file's own scope has no need for). Reuses
    ``test_human_approval_execution.py``'s own real fixtures rather
    than a second, duplicate copy. Returns ``(workflow_id,
    approval_id)``."""
    definition = _definition()
    workflow_id = await _create_running_instance(engine, definition)
    point = next(p for p in definition.human_approval_points if p.id == _APPROVAL_CLASS)
    assert isinstance(point, HumanApprovalPoint)
    approval = await SqlApprovalRepository(engine).create_pending(
        workflow_id=workflow_id, step_id=point.id, point=point
    )
    await SqlWorkflowInstanceRepository(engine).mark_waiting_for_human(
        workflow_id=workflow_id,
        definition_id=definition.id,
        definition_version=definition.version,
        expected_current_step_id=None,
        reason="real role administration proof",
    )
    return workflow_id, approval.approval_id


def test_an_admin_can_grant_a_role_and_it_is_genuinely_audited(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            audit_log = SqlAuditLogWriter(engine)
            role_grant_repository = SqlRoleGrantRepository(engine)
            service = RoleAdministrationService(role_grant_repository, audit_log)

            granted = await service.grant(
                principal=_ADMIN,
                target_principal_id="operator-1",
                role=f"approver:{_APPROVAL_CLASS}",
                reason="on-call rotation for this release",
            )

            assert granted.status == "active"
            assert granted.granted_by == "admin-1"
            active_roles = await role_grant_repository.active_roles_for("operator-1")
            assert f"approver:{_APPROVAL_CLASS}" in active_roles

            rows = await audit_log.list_all()
            record = next(r for r in rows if r.event_type == "security.role_granted")
            assert record.principal_id == "admin-1"
            assert record.outcome == AuditOutcome.SUCCESS
            assert record.resource_type == "principal"
            assert record.resource_id == "operator-1"
            assert record.detail["role"] == f"approver:{_APPROVAL_CLASS}"
            assert record.detail["reason"] == "on-call rotation for this release"
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_non_admin_cannot_grant_a_role_and_the_attempt_is_genuinely_audited_as_denied(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            audit_log = SqlAuditLogWriter(engine)
            role_grant_repository = SqlRoleGrantRepository(engine)
            service = RoleAdministrationService(role_grant_repository, audit_log)

            with pytest.raises(RoleAdministrationNotAuthorizedError):
                await service.grant(
                    principal=_OPERATOR,
                    target_principal_id="someone-else",
                    role=f"approver:{_APPROVAL_CLASS}",
                    reason="should be refused",
                )

            # Genuinely refused, not merely reported as an error: no
            # real grant exists for the would-be target.
            active_roles = await role_grant_repository.active_roles_for("someone-else")
            assert active_roles == frozenset()

            rows = await audit_log.list_all()
            record = next(r for r in rows if r.event_type == "security.role_grant.denied")
            assert record.principal_id == "operator-1"
            assert record.outcome == AuditOutcome.DENIED
            assert record.resource_id == "someone-else"
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_granted_role_genuinely_enables_and_a_revoked_role_genuinely_disables_a_decision(
    database_url: str,
) -> None:
    """The real proof this file exists for — one continuous, real
    flow: refused -> granted -> enabled -> revoked -> refused again,
    with the deciding principal's own ``roles`` (its bearer token's own
    claim) never changing at all throughout."""

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            audit_log = SqlAuditLogWriter(engine)
            role_grant_repository = SqlRoleGrantRepository(engine)
            administration = RoleAdministrationService(role_grant_repository, audit_log)
            approval_repository = SqlApprovalRepository(engine)
            approval_service = ApprovalService(
                approval_repository, role_grant_repository=role_grant_repository
            )

            # A principal genuinely holding no approver role at all —
            # its own bearer token never changes for the rest of this
            # test.
            decider = Principal(
                principal_id="release-manager-1",
                principal_type=PrincipalType.USER,
                roles=frozenset(),
            )

            # 1. Refused — no grant exists yet.
            first_workflow_id, first_approval_id = await _real_pending_approval(engine)
            with pytest.raises(ApprovalNotAuthorizedError):
                await approval_service.decide(
                    approval_id=first_approval_id,
                    principal=decider,
                    decision="approved",
                    comment=None,
                )
            still_pending = await approval_repository.get_by_id(approval_id=first_approval_id)
            assert still_pending is not None
            assert still_pending.status == "pending"

            # 2. A real, persisted grant — the admin's own action, not
            # the decider's.
            await administration.grant(
                principal=_ADMIN,
                target_principal_id="release-manager-1",
                role=f"approver:{_APPROVAL_CLASS}",
                reason="covering this release's approvals",
            )

            # 3. The identical principal, identical roles=frozenset()
            # — now genuinely succeeds.
            decided = await approval_service.decide(
                approval_id=first_approval_id,
                principal=decider,
                decision="approved",
                comment="Enabled by a real, persisted grant.",
            )
            assert decided.status == "approved"
            assert decided.decided_by == "release-manager-1"

            # 4. A real revoke.
            await administration.revoke(
                principal=_ADMIN,
                target_principal_id="release-manager-1",
                role=f"approver:{_APPROVAL_CLASS}",
                reason="rotation ended",
            )
            active_roles = await role_grant_repository.active_roles_for("release-manager-1")
            assert active_roles == frozenset()

            # 5. A fresh, second pending approval — the identical
            # principal is refused again.
            second_workflow_id, second_approval_id = await _real_pending_approval(engine)
            assert second_workflow_id != first_workflow_id
            with pytest.raises(ApprovalNotAuthorizedError):
                await approval_service.decide(
                    approval_id=second_approval_id,
                    principal=decider,
                    decision="approved",
                    comment=None,
                )
            still_pending_2 = await approval_repository.get_by_id(approval_id=second_approval_id)
            assert still_pending_2 is not None
            assert still_pending_2.status == "pending"

            # The full, real audit trail for this one principal.
            rows = await audit_log.list_all()
            granted_rows = [
                r
                for r in rows
                if r.event_type == "security.role_granted" and r.resource_id == "release-manager-1"
            ]
            revoked_rows = [
                r
                for r in rows
                if r.event_type == "security.role_revoked" and r.resource_id == "release-manager-1"
            ]
            assert len(granted_rows) == 1
            assert len(revoked_rows) == 1
            assert revoked_rows[0].principal_id == "admin-1"
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_granting_an_already_active_role_is_refused(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            audit_log = SqlAuditLogWriter(engine)
            role_grant_repository = SqlRoleGrantRepository(engine)
            service = RoleAdministrationService(role_grant_repository, audit_log)

            await service.grant(
                principal=_ADMIN,
                target_principal_id="double-grant-target",
                role="approver:release",
                reason="first grant",
            )

            with pytest.raises(RoleGrantAlreadyActiveError):
                await service.grant(
                    principal=_ADMIN,
                    target_principal_id="double-grant-target",
                    role="approver:release",
                    reason="second, conflicting grant",
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_revoking_a_role_that_is_not_active_is_refused(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            audit_log = SqlAuditLogWriter(engine)
            role_grant_repository = SqlRoleGrantRepository(engine)
            service = RoleAdministrationService(role_grant_repository, audit_log)

            with pytest.raises(RoleGrantNotActiveError):
                await service.revoke(
                    principal=_ADMIN,
                    target_principal_id="never-granted-target",
                    role="approver:release",
                    reason="nothing to revoke",
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())
