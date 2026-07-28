"""Opt-in, real-network, real-database verification that
``POST /api/v1/workflows`` drives the demo workflow all the way to a
genuine Anthropic-backed completion, through the real HTTP layer (a
real bearer token, real authorization, the real composition root) —
not a direct call to ``app.state.trigger_prompted_agent_workflow`` as
``test_bootstrap_workflow_trigger_live.py`` uses.

Skipped unless a real key is available at the documented local-dev
secret reference, exactly mirroring the other opt-in live tests in this
suite.
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

from ai_os_kernel.bootstrap import _DEMO_WORKFLOW_PACK_ID, _DEMO_WORKFLOW_PROMPT_ID, build_app
from ai_os_kernel.configuration_manager import PlatformConfig
from ai_os_kernel.persistence.engine import build_engine
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
SCHEMA_PATH = "platform_sdk/schemas/manifest.schema.json"
_API_KEY_ENV_VAR = "AIOS_SECRET_LLM_ANTHROPIC_API_KEY"
_SIGNING_KEY = "live-test-signing-key-at-least-32-bytes-long"

pytestmark = pytest.mark.skipif(
    not os.environ.get(_API_KEY_ENV_VAR),
    reason=f"{_API_KEY_ENV_VAR} is not set — this live-provider suite is opt-in (ADR-0015)",
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


async def _seed_prompt(database_url: str) -> None:
    engine = build_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                sa.text(
                    "INSERT INTO catalog.prompts "
                    "(prompt_id, pack_id, version, content, input_schema, content_hash) "
                    "VALUES (:prompt_id, :pack_id, '1.0.0', "
                    " 'Reply with exactly the word: pong', '{}'::jsonb, 'sha256:abc') "
                    "ON CONFLICT (prompt_id, version) DO NOTHING"
                ),
                {"prompt_id": _DEMO_WORKFLOW_PROMPT_ID, "pack_id": _DEMO_WORKFLOW_PACK_ID},
            )
    finally:
        await engine.dispose()


def _config() -> PlatformConfig:
    return PlatformConfig(
        env="test",
        role="api",
        capability_pack_dirs=[],
        manifest_schema_path=SCHEMA_PATH,
    )


def _token(roles: list[str]) -> str:
    claims = {
        "sub": "live-test-user",
        "roles": roles,
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    return jwt.encode(claims, _SIGNING_KEY, algorithm="HS256")


def test_an_authorized_request_drives_the_demo_workflow_to_a_real_completion(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    asyncio.run(_seed_prompt(database_url))
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/workflows",
            json={"inputs": {}},
            headers={"Authorization": f"Bearer {_token(['operator'])}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "completed"
    assert body["error"] is None
