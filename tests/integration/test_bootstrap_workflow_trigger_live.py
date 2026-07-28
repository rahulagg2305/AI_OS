"""Opt-in, real-network, real-database verification of this step's own
deliverable through the *real* composition root: ``bootstrap.build_app``
+ ``_lifespan`` genuinely construct ``app.state.trigger_prompted_agent_workflow``,
and calling it drives the demo workflow to a real, Anthropic-backed
completion — not a substituted Echo agent, as
``test_bootstrap_workflow_trigger.py`` uses.

Skipped unless a real key is available at the documented local-dev
secret reference, exactly mirroring
``tests/integration/test_bootstrap_prompted_agent_live.py`` and the
other opt-in live tests in this suite.
"""

import asyncio
import os
from collections.abc import Generator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from ai_os_kernel.bootstrap import (
    _DEMO_WORKFLOW_PACK_ID,
    _DEMO_WORKFLOW_PROMPT_ID,
    _DEMO_WORKFLOW_PROMPT_VERSION,
    build_app,
)
from ai_os_kernel.configuration_manager import PlatformConfig
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.workflow_engine.advance_runner import WorkflowRunOutcome
from ai_os_kernel.workflow_engine.instance import WorkflowInstanceStatus
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
SCHEMA_PATH = "platform_sdk/schemas/manifest.schema.json"
_API_KEY_ENV_VAR = "AIOS_SECRET_LLM_ANTHROPIC_API_KEY"

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
                    "VALUES (:prompt_id, :pack_id, :version, "
                    " 'Reply with exactly the word: pong', '{}'::jsonb, 'sha256:abc') "
                    "ON CONFLICT (prompt_id, version) DO NOTHING"
                ),
                {
                    "prompt_id": _DEMO_WORKFLOW_PROMPT_ID,
                    "pack_id": _DEMO_WORKFLOW_PACK_ID,
                    "version": _DEMO_WORKFLOW_PROMPT_VERSION,
                },
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


def test_the_real_trigger_drives_the_demo_workflow_to_a_real_completion(
    database_url: str,
) -> None:
    asyncio.run(_seed_prompt(database_url))
    app = build_app(_config())

    with TestClient(app):
        # AIOS_DATABASE_URL is set by the database_url fixture above, so
        # _lifespan's real DatabaseSettings()/build_engine() calls
        # resolve to this real, migrated container — the composition
        # root's own env-driven wiring, not a test-supplied override.
        trigger = app.state.trigger_prompted_agent_workflow
        result = asyncio.run(trigger({}, "test-user"))

    assert result.outcome is WorkflowRunOutcome.COMPLETED
    assert result.last_instance is not None
    assert result.last_instance.status is WorkflowInstanceStatus.COMPLETED
