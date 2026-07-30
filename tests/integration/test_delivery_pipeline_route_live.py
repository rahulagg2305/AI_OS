"""Opt-in, real-network, real-database verification that ``POST
/api/v1/workflows/se.delivery_pipeline`` drives the real, full 5-agent
Software Engineering pipeline (Requirements Analyst -> Architecture ->
Build -> Test -> Documentation) all the way to a genuine
Anthropic-backed completion, through the real HTTP layer (a real
bearer token, real authorization, the real composition root) — not a
direct call to ``build_pipeline_trigger`` as
``tests/integration/workflow_engine/test_delivery_pipeline.py``'s own
live test uses.

Reuses that same test's own real ``catalog.*`` seeding helpers
(``_register_and_activate_pack``/``_seed_agent_rows``/``_seed_real_prompts``)
directly — the identical raw-SQL seeding this codebase uses everywhere
until a real manifest -> catalog installer exists (a known, separately
tracked gap) — rather than a second, duplicate copy.

Skipped unless a real key is available at the documented local-dev
secret reference, exactly mirroring every other opt-in live test in
this suite.
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
from tests.integration._postgres_fixture import postgres_container
from tests.integration.workflow_engine.test_delivery_pipeline import (
    _register_and_activate_pack,
    _seed_agent_rows,
    _seed_real_prompts,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
SCHEMA_PATH = "platform_sdk/schemas/manifest.schema.json"
_API_KEY_ENV_VAR = "AIOS_SECRET_LLM_ANTHROPIC_API_KEY"
_SIGNING_KEY = "live-test-signing-key-at-least-32-bytes-long"
_ROUTE = "/api/v1/workflows/se.delivery_pipeline"

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


async def _seed_the_real_pack(database_url: str) -> None:
    await _register_and_activate_pack(database_url)
    await _seed_agent_rows(database_url)
    await _seed_real_prompts(database_url)


def test_an_authorized_request_drives_the_real_five_agent_pipeline_to_completion(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    asyncio.run(_seed_the_real_pack(database_url))
    monkeypatch.setenv("AIOS_SECRET_SECURITY_JWT_SIGNING_KEY", _SIGNING_KEY)
    app = build_app(_config())

    with TestClient(app) as client:
        response = client.post(
            _ROUTE,
            json={
                "requirement": (
                    "Write a Python script that prints exactly: hello from the pipeline"
                )
            },
            headers={"Authorization": f"Bearer {_token(['operator'])}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "completed", body["error"]
    assert body["error"] is None
    # The real value this route adds over the platform-generic
    # /workflows route: this pipeline's own real, known output field,
    # read back from the real, persisted `documentation` step.
    assert body["documentation_path"]
    assert body["documentation_path"].endswith(".md")
