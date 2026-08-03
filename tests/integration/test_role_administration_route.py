"""The real, end-to-end proof this step exists for (``P03-S05-M14-T08``):
an ``admin`` principal can grant and revoke a real, persisted
``approver:<class>`` role for another principal through the real HTTP
route (``/api/v1/security/role-grants``), and a non-admin principal's
attempt is genuinely refused — closing
:mod:`ai_os_kernel.security_manager.role_administration`'s own
disclosed "service-layer only, no HTTP route" gap.

Deliberately the identical, lighter ``capability_pack_dirs=[]`` +
``TestClient(build_app(...))`` shape ``test_workflows_route.py`` already
establishes, not the heavier real-pipeline setup
``test_approvals_route.py`` needs — role administration has no
dependency on any Capability Pack at all, so standing one up here would
be unrelated setup weight, not a stronger proof.

Real Postgres via testcontainers (ADR-0015) — no mocking the database.
"""

import asyncio
import os
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from ai_os_kernel.bootstrap import build_app
from ai_os_kernel.configuration_manager import PlatformConfig
from ai_os_kernel.observability.audit import AuditOutcome, SqlAuditLogWriter
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.security_manager.role_administration import SqlRoleGrantRepository
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
SCHEMA_PATH = "platform_sdk/schemas/manifest.schema.json"
_SIGNING_KEY = "role-admin-route-test-signing-key-at-least-32-bytes"  # gitleaks:allow
_ROLE = "approver:approve-deployment"
_ROUTE = "/api/v1/security/role-grants"


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


def _config() -> PlatformConfig:
    return PlatformConfig(
        env="test",
        role="api",
        capability_pack_dirs=[],
        manifest_schema_path=SCHEMA_PATH,
    )


def _token(roles: list[str], *, sub: str = "role-admin-route-test-admin") -> str:
    claims = {
        "sub": sub,
        "roles": roles,
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    return jwt.encode(claims, _SIGNING_KEY, algorithm="HS256")


def test_an_admin_can_grant_and_revoke_a_role_via_the_real_http_route(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    admin_headers = {"Authorization": f"Bearer {_token(['admin'])}"}

    with TestClient(app) as client:
        grant_response = client.post(
            _ROUTE,
            json={
                "principal_id": "http-route-target",
                "role": _ROLE,
                "reason": "on-call rotation, granted via real HTTP",
            },
            headers=admin_headers,
        )
        assert grant_response.status_code == 200, grant_response.text
        granted = grant_response.json()
        assert granted["principal_id"] == "http-route-target"
        assert granted["role"] == _ROLE
        assert granted["status"] == "active"
        assert granted["granted_by"] == "role-admin-route-test-admin"

        revoke_response = client.request(
            "DELETE",
            _ROUTE,
            json={
                "principal_id": "http-route-target",
                "role": _ROLE,
                "reason": "rotation ended, revoked via real HTTP",
            },
            headers=admin_headers,
        )
        assert revoke_response.status_code == 200, revoke_response.text
        revoked = revoke_response.json()
        assert revoked["status"] == "revoked"
        assert revoked["revoked_by"] == "role-admin-route-test-admin"

    # Read the real, persisted end state directly — never trusted from
    # the response bodies alone.
    engine = build_engine(database_url)
    try:

        async def _check() -> None:
            active_roles = await SqlRoleGrantRepository(engine).active_roles_for(
                "http-route-target"
            )
            assert active_roles == frozenset()

            audit_rows = await SqlAuditLogWriter(engine).list_all()
            granted_rows = [
                row
                for row in audit_rows
                if row.event_type == "security.role_granted"
                and row.resource_id == "http-route-target"
            ]
            revoked_rows = [
                row
                for row in audit_rows
                if row.event_type == "security.role_revoked"
                and row.resource_id == "http-route-target"
            ]
            assert len(granted_rows) == 1
            assert granted_rows[0].outcome == AuditOutcome.SUCCESS
            assert len(revoked_rows) == 1
            assert revoked_rows[0].outcome == AuditOutcome.SUCCESS

        asyncio.run(_check())
    finally:
        asyncio.run(engine.dispose())


def test_a_non_admin_request_is_refused_and_no_real_grant_is_made(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    non_admin_headers = {"Authorization": f"Bearer {_token(['operator'], sub='non-admin-caller')}"}

    with TestClient(app) as client:
        grant_response = client.post(
            _ROUTE,
            json={
                "principal_id": "should-not-be-granted",
                "role": _ROLE,
                "reason": "should be refused",
            },
            headers=non_admin_headers,
        )
        assert grant_response.status_code == 403

        revoke_response = client.request(
            "DELETE",
            _ROUTE,
            json={
                "principal_id": "should-not-be-granted",
                "role": _ROLE,
                "reason": "should be refused",
            },
            headers=non_admin_headers,
        )
        assert revoke_response.status_code == 403

    engine = build_engine(database_url)
    try:

        async def _check() -> None:
            active_roles = await SqlRoleGrantRepository(engine).active_roles_for(
                "should-not-be-granted"
            )
            assert active_roles == frozenset()

        asyncio.run(_check())
    finally:
        asyncio.run(engine.dispose())
