"""Deterministic, real-database verification of ``GET /api/v1/agents``
(``ai_os_kernel.routes.agents``, added 2026-08-10, `P06-S01-M36-T04`)
through the real composition root (``bootstrap.build_app()`` +
``_lifespan``) — not a direct call to
``ai_os_kernel.workflow_engine.registry.SqlAgentRegistry`` as
``tests/integration/workflow_engine/test_registry.py`` uses.

Real Postgres via testcontainers (ADR-0015) — no mocking the database.
"""

import asyncio
import json
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
from ai_os_kernel.configuration_manager import PlatformConfig
from ai_os_kernel.persistence.engine import build_engine
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
SCHEMA_PATH = "platform_sdk/schemas/manifest.schema.json"
_SIGNING_KEY = "integration-test-signing-key-at-least-32-bytes"
_ECHO_AGENT_ENTRYPOINT = "ai_os_kernel.workflow_engine.agent:EchoAgent"


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
        "sub": "integration-test-user",
        "roles": roles,
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    return jwt.encode(claims, _SIGNING_KEY, algorithm="HS256")


def _seed_real_agent(database_url: str, *, agent_id: str, pack_id: str) -> None:
    async def _seed() -> None:
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO catalog.packs "
                        "(pack_id, version, state, manifest, sdk_version, min_kernel_version) "
                        "VALUES (:pack_id, '1.0.0', 'activated', '{}'::jsonb, '1.0.0', '1.0.0') "
                        "ON CONFLICT (pack_id) DO NOTHING"
                    ),
                    {"pack_id": pack_id},
                )
                await connection.execute(
                    sa.text(
                        "INSERT INTO catalog.agents "
                        "(agent_id, pack_id, version, entrypoint, input_schema, output_schema, "
                        " required_permissions, required_tools) "
                        "VALUES (:agent_id, :pack_id, '1.0.0', :entrypoint, "
                        " '{}'::jsonb, '{}'::jsonb, :required_permissions, '[]'::jsonb)"
                    ),
                    {
                        "agent_id": agent_id,
                        "pack_id": pack_id,
                        "entrypoint": _ECHO_AGENT_ENTRYPOINT,
                        "required_permissions": json.dumps(["llm:invoke"]),
                    },
                )
        finally:
            await engine.dispose()

    asyncio.run(_seed())


def test_agents_route_requires_authentication(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.get("/api/v1/agents")

    assert response.status_code == 401


def test_agents_route_lists_a_real_registered_agent(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_real_agent(
        database_url, agent_id="se.agents_route_test_agent", pack_id="se.agents_route_test_pack"
    )

    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())
    with TestClient(app) as client:
        # workflow:read is granted to every real role (viewer included)
        # — permissions.py's own role table.
        response = client.get(
            "/api/v1/agents", headers={"Authorization": f"Bearer {_token(['viewer'])}"}
        )

    assert response.status_code == 200
    agents = response.json()
    matching = next(a for a in agents if a["agent_id"] == "se.agents_route_test_agent")
    assert matching["pack_id"] == "se.agents_route_test_pack"
    assert matching["entrypoint"] == _ECHO_AGENT_ENTRYPOINT
    assert matching["required_permissions"] == ["llm:invoke"]
    assert matching["pack_state"] == "activated"
