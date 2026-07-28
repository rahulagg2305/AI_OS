"""The real, end-to-end proof of the Requirements Analyst Agent —
mirrors ``test_architecture_agent_pack.py`` exactly (the identical
zero-arg/lazy-build ``PromptedAgent`` resolution tension, resolved the
identical way): a real Capability Pack
(`capability_packs/software-engineering`), registered and activated
through the real `SqlPackLifecycleRepository`, resolved through the
real `SqlAgentRegistry` — not `InMemoryAgentRegistry`.

Two tiers, against a real Postgres container (ADR-0015 — no mocking the
database):

1. **Deterministic, no live LLM call required** — registers the pack,
   seeds a real `catalog.agents` row naming this pack's real
   `RequirementsAnalystAgentEntrypoint`, and proves `SqlAgentRegistry`
   resolves it for real.
2. **Opt-in live** (skipped without `AIOS_SECRET_LLM_ANTHROPIC_API_KEY`,
   exactly mirroring `test_architecture_agent_pack.py`) — the same
   resolution, then a genuine `AgentStepExecutor.execute()` call that
   completes against the live Anthropic API and returns a real
   requirements analysis. Seeds a minimal, test-only prompt (not this
   pack's own shipped `prompts/requirements_analysis.md`, which needs a
   real Context Manager-supplied `context` variable this focused proof
   does not stand up).
"""

import asyncio
import contextlib
import os
from collections.abc import Generator
from pathlib import Path

import pytest
import sqlalchemy as sa
import yaml
from alembic import command
from alembic.config import Config

from ai_os_kernel.capability_manager.errors import CapabilityManagerError
from ai_os_kernel.capability_manager.repository import SqlPackLifecycleRepository
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.workflow_engine.agent import Agent
from ai_os_kernel.workflow_engine.models import StepType, WorkflowStep
from ai_os_kernel.workflow_engine.registry import SqlAgentRegistry
from ai_os_kernel.workflow_engine.step_executor import AgentStepExecutor
from ai_os_pack_software_engineering.agents.requirements_analyst import (
    RequirementsAnalysisOutput,
    RequirementsAnalystAgentEntrypoint,
)
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

_PACK_ID = "software-engineering"
_PACK_VERSION = "0.1.0"
_AGENT_ID = f"{_PACK_ID}/requirements-analyst"
_AGENT_ENTRYPOINT = (
    "ai_os_pack_software_engineering.agents.requirements_analyst:RequirementsAnalystAgentEntrypoint"
)
_LIVE_PROMPT_ID = "requirements.analyze.live_test"
_LIVE_PROMPT_VERSION = "0.1.0"
_API_KEY_ENV_VAR = "AIOS_SECRET_LLM_ANTHROPIC_API_KEY"


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


async def _register_and_activate_pack(database_url: str) -> None:
    """Idempotent across the two test functions in this module, which
    share one Postgres container — mirrors
    `test_architecture_agent_pack.py`'s own helper exactly."""
    engine = build_engine(database_url)
    try:
        repository = SqlPackLifecycleRepository(engine)
        with (REPO_ROOT / "capability_packs" / "software-engineering" / "manifest.yaml").open(
            encoding="utf-8"
        ) as fh:
            manifest = yaml.safe_load(fh)
        with contextlib.suppress(CapabilityManagerError):
            await repository.register(
                pack_id=_PACK_ID,
                version=_PACK_VERSION,
                manifest=manifest,
                sdk_version=">=0.1.0,<1.0.0",
                min_kernel_version="0.1.0",
                actor="test",
                reason="requirements analyst agent pack integration test",
            )
        with contextlib.suppress(CapabilityManagerError):
            await repository.activate(pack_id=_PACK_ID, actor="test", reason="integration test")
    finally:
        await engine.dispose()


async def _seed_agent_row(database_url: str) -> None:
    """No automated manifest -> catalog.agents installer exists yet —
    mirrors `test_architecture_agent_pack.py`'s own direct seeding."""
    engine = build_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                sa.text(
                    "INSERT INTO catalog.agents "
                    "(agent_id, pack_id, version, entrypoint, input_schema, output_schema, "
                    " required_permissions, required_tools) "
                    "VALUES (:agent_id, :pack_id, :version, :entrypoint, "
                    " '{}'::jsonb, "
                    ' \'{"type": "object", "properties": {"analysis": {"type": "string"}}, '
                    '   "required": ["analysis"], "additionalProperties": false}\'::jsonb, '
                    " '[\"llm:invoke\"]'::jsonb, '[]'::jsonb) "
                    "ON CONFLICT (agent_id) DO NOTHING"
                ),
                {
                    "agent_id": _AGENT_ID,
                    "pack_id": _PACK_ID,
                    "version": _PACK_VERSION,
                    "entrypoint": _AGENT_ENTRYPOINT,
                },
            )
    finally:
        await engine.dispose()


async def _seed_live_prompt(database_url: str) -> None:
    engine = build_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                sa.text(
                    "INSERT INTO catalog.prompts "
                    "(prompt_id, pack_id, version, content, input_schema, content_hash) "
                    "VALUES (:prompt_id, :pack_id, :version, "
                    " 'Analyze and refine the following raw requirement for a URL shortener "
                    "service into functional requirements and acceptance criteria. Be concise.', "
                    " '{}'::jsonb, 'sha256:abc') "
                    "ON CONFLICT (prompt_id, version) DO NOTHING"
                ),
                {
                    "prompt_id": _LIVE_PROMPT_ID,
                    "pack_id": _PACK_ID,
                    "version": _LIVE_PROMPT_VERSION,
                },
            )
    finally:
        await engine.dispose()


def test_sql_agent_registry_genuinely_resolves_the_requirements_analyst_agent(
    database_url: str,
) -> None:
    """Deterministic — no live LLM call. Proves the exact thing this
    step's own approved framing named: the `PromptedAgent`/
    `SqlAgentRegistry` construction tension is resolved the same way for
    a second, distinct `PromptedAgent`-backed entrypoint, not just the
    one this pack happened to build first."""

    async def _run() -> None:
        await _register_and_activate_pack(database_url)
        await _seed_agent_row(database_url)

        engine = build_engine(database_url)
        try:
            registry = SqlAgentRegistry(engine)
            resolved = await registry.resolve_agent(_AGENT_ID)

            assert isinstance(resolved, Agent)
            assert isinstance(resolved, RequirementsAnalystAgentEntrypoint)
            assert resolved.output_schema == {
                "type": "object",
                "properties": {"analysis": {"type": "string"}},
                "required": ["analysis"],
                "additionalProperties": False,
            }
        finally:
            await engine.dispose()

    asyncio.run(_run())


@pytest.mark.skipif(
    not os.environ.get(_API_KEY_ENV_VAR),
    reason=f"{_API_KEY_ENV_VAR} is not set — this live-provider suite is opt-in (ADR-0015)",
)
def test_a_real_workflow_step_genuinely_invokes_the_requirements_analyst_agent_live(
    database_url: str,
) -> None:
    """Opt-in live: the full chain this step exists to prove — a real
    `WorkflowStep` of type `agent`, dispatched through the real
    `AgentStepExecutor`, resolved through the real `SqlAgentRegistry`,
    genuinely produces a requirements analysis from a real Anthropic
    completion."""

    async def _run() -> None:
        await _register_and_activate_pack(database_url)
        await _seed_agent_row(database_url)
        await _seed_live_prompt(database_url)

        engine = build_engine(database_url)
        try:
            registry = SqlAgentRegistry(engine)
            executor = AgentStepExecutor(registry)
            step = WorkflowStep(
                id="analyze_requirements",
                type=StepType.AGENT,
                agent_id=_AGENT_ID,
                prompt_id=_LIVE_PROMPT_ID,
                prompt_version=_LIVE_PROMPT_VERSION,
                model_alias="coding-strong",
            )

            outputs = await executor.execute(step)

            RequirementsAnalysisOutput.model_validate(outputs)
            assert outputs["analysis"].strip() != ""
        finally:
            await engine.dispose()

    asyncio.run(_run())
