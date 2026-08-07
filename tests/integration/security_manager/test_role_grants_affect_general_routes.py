"""Real, Postgres-backed proof that a persisted role grant now affects
a *general*, permission-checked route — not only
:meth:`~ai_os_kernel.workflow_engine.human_approval.ApprovalService.decide`
(``P07-S02-M14-T02``, "Full five-role model").

Before this ticket, ``authenticate()``
(:mod:`ai_os_kernel.security_manager.dependencies`) computed a
principal's permissions from its bearer token's own ``roles`` claim
alone; a real, persisted grant from
:class:`~ai_os_kernel.security_manager.role_administration.RoleAdministrationService`
took effect only inside ``ApprovalService.decide``'s own narrower
check. ``GET /api/v1/packs`` (gated on ``pack:read``, granted only to
``maintainer``/``admin`` — see
:mod:`ai_os_kernel.security_manager.permissions`) is the proof target
here: a principal whose bearer token carries *no* roles at all is
refused, a real, persisted ``maintainer`` grant (the deciding
principal's own token never changes) then genuinely enables the
identical request, and a real revoke disables it again — the same
"refused -> granted -> enabled -> revoked -> refused again" shape
``tests/integration/security_manager/test_role_administration.py``
already established for ``ApprovalService.decide``.

Real Postgres via testcontainers (ADR-0015) — no mocking the database.
"""

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
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
SCHEMA_PATH = "platform_sdk/schemas/manifest.schema.json"
_SIGNING_KEY = "general-route-role-grant-test-signing-key-32b"  # gitleaks:allow
_PACKS_ROUTE = "/api/v1/packs"
_GRANTS_ROUTE = "/api/v1/security/role-grants"
_TARGET_PRINCIPAL = "general-route-target"


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


def _token(roles: list[str], *, sub: str) -> str:
    claims = {
        "sub": sub,
        "roles": roles,
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    return jwt.encode(claims, _SIGNING_KEY, algorithm="HS256")


def test_a_persisted_grant_enables_and_a_revoke_disables_a_general_route(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    admin_headers = {"Authorization": f"Bearer {_token(['admin'], sub='general-route-admin')}"}
    # The deciding principal's own bearer token never changes for the
    # rest of this test — roles=[] throughout.
    target_headers = {"Authorization": f"Bearer {_token([], sub=_TARGET_PRINCIPAL)}"}

    with TestClient(app) as client:
        # 1. Refused — no grant exists yet, and the bearer token itself
        # carries no roles.
        first_response = client.get(_PACKS_ROUTE, headers=target_headers)
        assert first_response.status_code == 403

        # 2. A real, persisted grant, via the real HTTP route — the
        # admin's own action, not the target's.
        grant_response = client.post(
            _GRANTS_ROUTE,
            json={
                "principal_id": _TARGET_PRINCIPAL,
                "role": "maintainer",
                "reason": "temporary pack-read access for this test",
            },
            headers=admin_headers,
        )
        assert grant_response.status_code == 200, grant_response.text

        # 3. The identical bearer token — still roles=[] — now
        # genuinely succeeds, because authenticate() unions the real,
        # persisted grant into the computed permission set.
        second_response = client.get(_PACKS_ROUTE, headers=target_headers)
        assert second_response.status_code == 200, second_response.text

        # 4. A real revoke, via the real HTTP route.
        revoke_response = client.request(
            "DELETE",
            _GRANTS_ROUTE,
            json={
                "principal_id": _TARGET_PRINCIPAL,
                "role": "maintainer",
                "reason": "temporary access ended",
            },
            headers=admin_headers,
        )
        assert revoke_response.status_code == 200, revoke_response.text

        # 5. The identical bearer token is refused again.
        third_response = client.get(_PACKS_ROUTE, headers=target_headers)
        assert third_response.status_code == 403
