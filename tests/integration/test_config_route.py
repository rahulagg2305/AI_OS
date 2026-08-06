"""Deterministic, real-database verification of the configuration HTTP
routes (ai_os_kernel.routes.config): GET /config, PATCH /config, GET
/config/flags — through the real composition root
(``bootstrap.build_app()`` + ``_lifespan``), not the no-database unit
tests in ``tests/unit/kernel/routes/test_config.py``.

**``app.state.configuration_manager``/``app.state.runtime_override_store``
are injected directly after ``_lifespan`` startup, not left to
``_lifespan`` build them itself** — a real, structural gap this test
discovered rather than worked around silently:
:func:`~ai_os_kernel.bootstrap._build_configuration_manager` only
succeeds for one of the four real deployment environments
(``local``/``dev``/``staging``/``production``); every test/CI identity
(this repository's own CI sets ``AIOS_ENV=ci``; a test that sets none
at all defaults to something else not in that set either) makes it
raise ``ConfigurationError``, caught and logged as a warning inside
``_lifespan``, leaving both attributes genuinely unset. This is a
correct, disclosed pre-existing gap in test/CI *composition*, not a bug
in the routes this step adds — the identical real
``ConfigurationManager``/``RuntimeOverrideStore`` pair `_lifespan`
would build for a real ``local`` deployment is constructed here
directly, exactly mirroring `_build_configuration_manager`'s own real
path arguments, then attached to the already-running app's own state.
``app.state.config_change_writer`` needs no such workaround — it only
depends on the real database engine, unconditionally wired regardless
of ``AIOS_ENV``'s validity.

Real Postgres via testcontainers (ADR-0015) — no mocking the database.
"""

import asyncio
import os
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from ai_os_kernel.bootstrap import build_app
from ai_os_kernel.configuration_manager import (
    ConfigurationManager,
    PlatformConfig,
    RuntimeOverrideStore,
)
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.governance_schema import config_changes
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
SCHEMA_PATH = "platform_sdk/schemas/manifest.schema.json"
_SIGNING_KEY = "config-route-test-signing-key-at-least-32-bytes"


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


def _token(roles: list[str]) -> str:
    claims = {
        "sub": "config-route-test-user",
        "roles": roles,
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    return jwt.encode(claims, _SIGNING_KEY, algorithm="HS256")


def _attach_real_configuration_manager(app: object) -> None:
    """Mirrors `_build_configuration_manager`'s own real construction —
    see this module's own docstring for why `_lifespan` alone cannot do
    this under a test/CI identity."""
    app.state.configuration_manager = ConfigurationManager(  # type: ignore[attr-defined]
        environment="local",
        platform_config_path=REPO_ROOT / "config" / "platform.yaml",
        environments_dir=REPO_ROOT / "infra" / "environments",
    )
    app.state.runtime_override_store = RuntimeOverrideStore()  # type: ignore[attr-defined]


def test_a_maintainer_can_read_the_real_effective_config(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    headers = {"Authorization": f"Bearer {_token(['maintainer'])}"}

    with TestClient(app) as client:
        _attach_real_configuration_manager(app)
        response = client.get("/api/v1/config", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["env"] == "local"
    assert body["role"] == "api"
    assert "host" in body
    assert "port" in body


def test_a_maintainer_can_patch_config_and_it_is_genuinely_audited(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real proof this step exists for: `PATCH /config` genuinely
    writes a real `governance.config_changes` row (the writer this
    route calls into, real and unchanged) *and* the new value is
    genuinely reflected in the next `GET /config` — not a stand-in for
    either half."""
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    headers = {"Authorization": f"Bearer {_token(['maintainer'])}"}

    with TestClient(app) as client:
        _attach_real_configuration_manager(app)
        patch_response = client.patch(
            "/api/v1/config",
            json={"config_key": "log_level", "new_value": "DEBUG", "reason": "investigating"},
            headers=headers,
        )
        assert patch_response.status_code == 200
        assert patch_response.json()["log_level"] == "DEBUG"

        get_response = client.get("/api/v1/config", headers=headers)
        assert get_response.json()["log_level"] == "DEBUG"

    engine = build_engine(database_url)
    try:

        async def _read_rows() -> list[sa.RowMapping]:
            async with engine.connect() as connection:
                result = await connection.execute(
                    sa.select(config_changes).where(config_changes.c.config_key == "log_level")
                )
                return list(result.mappings().all())

        rows = asyncio.run(_read_rows())
    finally:
        asyncio.run(engine.dispose())

    assert len(rows) == 1
    assert rows[0]["changed_by"] == "config-route-test-user"
    assert rows[0]["reason"] == "investigating"


def test_patching_env_or_role_is_rejected_as_bootstrap_identity(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    headers = {"Authorization": f"Bearer {_token(['maintainer'])}"}

    with TestClient(app) as client:
        _attach_real_configuration_manager(app)
        response = client.patch(
            "/api/v1/config",
            json={"config_key": "env", "new_value": "production", "reason": "nope"},
            headers=headers,
        )

    assert response.status_code == 422


def test_patching_a_secret_reference_is_rejected(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    headers = {"Authorization": f"Bearer {_token(['maintainer'])}"}

    with TestClient(app) as client:
        _attach_real_configuration_manager(app)
        response = client.patch(
            "/api/v1/config",
            json={
                "config_key": "log_level",
                "new_value": "secret://vault/x",
                "reason": "sneaky",
            },
            headers=headers,
        )

    assert response.status_code == 422


def test_a_rejected_patch_writes_no_audit_row(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Proves the real "validate before commit" ordering: a rejected
    change leaves no trace in the real audit table, not just an
    in-memory one."""
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    headers = {"Authorization": f"Bearer {_token(['maintainer'])}"}

    with TestClient(app) as client:
        _attach_real_configuration_manager(app)
        response = client.patch(
            "/api/v1/config",
            json={"config_key": "role", "new_value": "worker", "reason": "nope"},
            headers=headers,
        )
        assert response.status_code == 422

    engine = build_engine(database_url)
    try:

        async def _read_rows() -> list[sa.RowMapping]:
            async with engine.connect() as connection:
                result = await connection.execute(
                    sa.select(config_changes).where(config_changes.c.config_key == "role")
                )
                return list(result.mappings().all())

        rows = asyncio.run(_read_rows())
    finally:
        asyncio.run(engine.dispose())

    assert rows == []


def test_a_viewer_cannot_read_or_manage_config(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    headers = {"Authorization": f"Bearer {_token(['viewer'])}"}

    with TestClient(app) as client:
        _attach_real_configuration_manager(app)
        get_response = client.get("/api/v1/config", headers=headers)
        patch_response = client.patch(
            "/api/v1/config",
            json={"config_key": "log_level", "new_value": "WARNING", "reason": "nope"},
            headers=headers,
        )

    assert get_response.status_code == 403
    assert patch_response.status_code == 403


def test_feature_flags_route_resolves_a_pack_declared_flag_through_a_runtime_override(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real proof `GET /config/flags` exists for: a flag declared by
    a real, activated pack's own manifest resolves to its pack-declared
    default first, then genuinely flips after a real `PATCH /config`
    sets a runtime override for that exact flag name — proving flags
    and `PATCH /config` share the identical, real `RuntimeOverrideStore`
    layer `feature_flags.py`'s own docstring documents, not two
    disconnected mechanisms."""
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    headers = {"Authorization": f"Bearer {_token(['maintainer'])}"}

    with TestClient(app) as client:
        _attach_real_configuration_manager(app)

        register_response = client.post(
            "/api/v1/packs",
            json={
                "pack_id": "test.flag_pack",
                "version": "1.0.0",
                "manifest": {
                    "featureFlags": [
                        {"name": "shiny_new_thing", "default": False, "description": "test flag"}
                    ]
                },
                "sdk_version": "1.0.0",
                "min_kernel_version": "1.0.0",
                "reason": "prove the flags route",
            },
            headers=headers,
        )
        assert register_response.status_code == 201
        activate_response = client.post(
            "/api/v1/packs/test.flag_pack/activate",
            json={"reason": "activate for the flags test"},
            headers=headers,
        )
        assert activate_response.status_code == 200

        before = client.get("/api/v1/config/flags", headers=headers)
        before_flags = {f["name"]: f["enabled"] for f in before.json()}
        assert before_flags.get("shiny_new_thing") is False

        patch_response = client.patch(
            "/api/v1/config",
            json={
                "config_key": "shiny_new_thing",
                "new_value": True,
                "reason": "flip it on",
            },
            headers=headers,
        )
        assert patch_response.status_code == 200

        after = client.get("/api/v1/config/flags", headers=headers)

    after_flags = {f["name"]: f["enabled"] for f in after.json()}
    assert after_flags["shiny_new_thing"] is True
