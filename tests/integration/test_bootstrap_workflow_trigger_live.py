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

**Drives a dedicated trigger, not ``app.state.trigger_prompted_agent_workflow``
directly** — the identical cross-event-loop fix
``test_bootstrap_pack_lifecycle.py``/``test_bootstrap_prompted_agent_live.py``
apply (see the former's own docstring for the full root cause: CI run
``30682840924`` and follow-ups). ``app.state.trigger_prompted_agent_workflow``
is built on ``TestClient``'s own background event loop; calling it from
this test's own separate ``asyncio.run()`` — a second,
independently-running event loop on the main thread — is the same
hazard, sharing the same real Postgres connection pool underneath.
Rebuilt here via the real composition-root functions
(:func:`~ai_os_kernel.bootstrap._build_prompted_agent_registry`,
:func:`~ai_os_kernel.bootstrap._build_workflow_trigger`), not a
hand-rolled duplicate, against a fresh, dedicated engine, entirely
within this test's own ``asyncio.run()`` call. **Not directly exercised
in this repository's CI** (credential-gated, skipped without a live
Anthropic key) — this fix is confirmed correct by code review and by
the identical pattern already proven live in
``test_bootstrap_pack_lifecycle.py``, not by a live run of this
specific file.
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
    _CONTEXT_TOKEN_BUDGET,
    _DEMO_WORKFLOW_PACK_ID,
    _DEMO_WORKFLOW_PROMPT_ID,
    _DEMO_WORKFLOW_PROMPT_VERSION,
    _build_prompted_agent_registry,
    _build_workflow_trigger,
    build_app,
)
from ai_os_kernel.configuration_manager import PlatformConfig
from ai_os_kernel.context_manager.manager import DefaultContextManager
from ai_os_kernel.context_manager.resolvers import WorkflowStateResolver
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.workflow_engine.advance_runner import WorkflowRunOutcome, WorkflowRunResult
from ai_os_kernel.workflow_engine.instance import WorkflowInstanceStatus
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
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
        # root's own env-driven wiring. Asserted here, synchronously,
        # never awaited from this test's own separate event loop below
        # (see this module's own docstring for the cross-event-loop
        # hazard that would create).
        assert app.state.trigger_prompted_agent_workflow is not None

    # A dedicated engine and freshly-built registry/context
    # manager/trigger — the real _build_prompted_agent_registry/
    # _build_workflow_trigger, never app.state's own copies — against
    # the same real, already-migrated database.
    engine = build_engine(database_url)

    async def _run() -> WorkflowRunResult:
        try:
            agent_registry = await _build_prompted_agent_registry(engine)
            context_manager = DefaultContextManager(
                resolvers=[WorkflowStateResolver(SqlWorkflowInstanceRepository(engine))],
                default_token_budget=_CONTEXT_TOKEN_BUDGET,
            )
            trigger = _build_workflow_trigger(engine, agent_registry, context_manager)
            return await trigger({}, "test-user")
        finally:
            await engine.dispose()

    result = asyncio.run(_run())

    assert result.outcome is WorkflowRunOutcome.COMPLETED
    assert result.last_instance is not None
    assert result.last_instance.status is WorkflowInstanceStatus.COMPLETED
