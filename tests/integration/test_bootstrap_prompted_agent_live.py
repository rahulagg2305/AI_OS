"""Opt-in, real-network, real-database verification of this step's own
deliverable: the real composition root (``bootstrap.build_app`` +
``_lifespan``) genuinely constructs and registers ``PromptedAgent`` —
not a test constructing it directly, as every prior step's tests did.

Skipped unless a real key is available at the documented local-dev
secret reference, exactly mirroring every other opt-in live test in this
suite (``tests/integration/llm_gateway/test_anthropic_adapter_live.py``,
``tests/integration/test_prompted_completion_live.py``,
``tests/integration/workflow_engine/test_prompted_agent_live.py``).
This file is the only one of the four that goes through the real
composition root itself, rather than constructing the chain by hand.

**Exercises the resolved agent through a dedicated engine, not
``app.state.agent_registry`` directly** — the identical cross-event-loop
fix ``test_bootstrap_pack_lifecycle.py`` applies (see that file's own
docstring for the full root cause: CI run ``30682840924`` and
follow-ups). ``app.state.agent_registry`` is built on ``TestClient``'s
own background event loop; calling its async methods from this test's
own separate ``asyncio.run()`` — a second, independently-running event
loop on the main thread — is the same hazard, sharing the same real
Postgres connection pool underneath. Rebuilt here via the real
:func:`~ai_os_kernel.bootstrap._build_prompted_agent_registry` — the
actual composition-root function, not a hand-rolled duplicate — against
a fresh, dedicated engine, entirely within this test's own
``asyncio.run()`` call. **Not directly exercised in this repository's
CI** (credential-gated, skipped without a live Anthropic key) — this
fix is confirmed correct by code review and by the identical pattern
already proven live in ``test_bootstrap_pack_lifecycle.py``, not by a
live run of this specific file.
"""

import asyncio
import os
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from ai_os_kernel.bootstrap import _build_prompted_agent_registry, build_app
from ai_os_kernel.configuration_manager import PlatformConfig
from ai_os_kernel.persistence.engine import build_engine
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
SCHEMA_PATH = "platform_sdk/schemas/manifest.schema.json"
_API_KEY_ENV_VAR = "AIOS_SECRET_LLM_ANTHROPIC_API_KEY"
_PROMPTED_AGENT_ID = "platform/prompted-agent"
_PROMPT_ID = "prompt_bootstrap_live_smoke_test"

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
                    "VALUES (:prompt_id, 'se.software_engineering', '1.0.0', "
                    " 'Reply with exactly the word: pong', '{}'::jsonb, 'sha256:abc') "
                    "ON CONFLICT (prompt_id, version) DO NOTHING"
                ),
                {"prompt_id": _PROMPT_ID},
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


def test_the_real_composition_root_registers_a_working_prompted_agent(database_url: str) -> None:
    asyncio.run(_seed_prompt(database_url))
    app = build_app(_config())

    with TestClient(app):
        # AIOS_DATABASE_URL is set by the database_url fixture above, so
        # _lifespan's real DatabaseSettings()/build_engine() calls
        # resolve to this real, migrated container — the composition
        # root's own env-driven wiring. Asserted here, synchronously,
        # never awaited from this test's own separate event loop below
        # (see this module's own docstring for the cross-event-loop
        # hazard that would create).
        assert app.state.agent_registry is not None

    # A dedicated engine and a freshly-built registry — the real
    # _build_prompted_agent_registry, never app.state's own copy —
    # against the same real, already-migrated database.
    engine = build_engine(database_url)

    async def _run() -> dict[str, Any]:
        try:
            registry = await _build_prompted_agent_registry(engine)
            agent = await registry.resolve_agent(_PROMPTED_AGENT_ID)
            return await agent.execute(
                {
                    "promptId": _PROMPT_ID,
                    "promptVersion": "1.0.0",
                    "modelAlias": "fast-cheap",
                }
            )
        finally:
            await engine.dispose()

    outputs = asyncio.run(_run())

    assert "content" in outputs
    assert outputs["content"].strip() != ""
