"""The first real, end-to-end proof of a `tier1`-free, genuinely
sandbox-independent pipeline link: a real Capability Pack
(`capability_packs/software-engineering`), registered and activated
through the real `SqlPackLifecycleRepository`, resolved through the
real `SqlAgentRegistry` — not `InMemoryAgentRegistry`, the boundary this
step's own approved framing names as the thing to finally cross for a
`PromptedAgent`-backed agent.

Two tiers, against a real Postgres container (ADR-0015 — no mocking the
database):

1. **Deterministic, no live LLM call required** — registers the pack,
   seeds a real `catalog.agents` row naming this pack's real
   `ArchitectureAgentEntrypoint`, and proves `SqlAgentRegistry` resolves
   it for real: a real pack-activation gate, a real `EntrypointLoader`
   import, a real `isinstance(..., Agent)` check. This alone proves the
   PromptedAgent/SqlAgentRegistry construction tension is genuinely
   resolved — no live Anthropic call is needed to prove *resolution*.
2. **Opt-in live** (skipped without `AIOS_SECRET_LLM_ANTHROPIC_API_KEY`,
   exactly mirroring `test_prompted_agent_live.py`) — the same
   resolution, then a genuine `AgentStepExecutor.execute()` call that
   completes against the live Anthropic API and returns a real
   architecture proposal. Seeds a minimal, test-only prompt (not this
   pack's own shipped `prompts/architecture_proposal.md`, which needs a
   real Context Manager-supplied `context` variable this focused proof
   does not stand up — the identical "a small, self-contained prompt for
   this one proof" choice `test_prompted_agent_live.py` itself already
   makes).
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
from ai_os_pack_software_engineering.agents.architecture import (
    ArchitectureAgentEntrypoint,
    ArchitectureProposalOutput,
)
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

_PACK_ID = "software-engineering"
_PACK_VERSION = "0.1.0"
_AGENT_ID = f"{_PACK_ID}/architecture"
_AGENT_ENTRYPOINT = (
    "ai_os_pack_software_engineering.agents.architecture:ArchitectureAgentEntrypoint"
)
_LIVE_PROMPT_ID = "architecture.propose_design.live_test"
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
    """The one part of this proof that uses a real writer, per this
    step's own approved framing: "Register and activate the pack
    through the existing SqlPackLifecycleRepository/catalog.packs
    writer — no new lifecycle mechanism." Idempotent across the two
    test functions in this module, which share one Postgres container:
    a second registration/activation of the same pack is expected, not
    an error worth failing the test over."""
    engine = build_engine(database_url)
    try:
        repository = SqlPackLifecycleRepository(engine)
        with (REPO_ROOT / "capability_packs" / "software-engineering" / "manifest.yaml").open(
            encoding="utf-8"
        ) as fh:
            manifest = yaml.safe_load(fh)
        with contextlib.suppress(CapabilityManagerError):
            # Already registered by an earlier test in this module.
            await repository.register(
                pack_id=_PACK_ID,
                version=_PACK_VERSION,
                manifest=manifest,
                sdk_version=">=0.1.0,<1.0.0",
                min_kernel_version="0.1.0",
                actor="test",
                reason="architecture agent pack integration test",
            )
        with contextlib.suppress(CapabilityManagerError):
            # Already activated by an earlier test in this module.
            await repository.activate(pack_id=_PACK_ID, actor="test", reason="integration test")
    finally:
        await engine.dispose()


async def _seed_agent_row(database_url: str) -> None:
    """No automated manifest -> catalog.agents installer exists yet
    (a real, documented gap — see ai_os_kernel.capability_manager.
    pack_contract's own docstring) — this mirrors
    tests/integration/workflow_engine/test_registry.py's own direct
    seeding of a catalog.agents row exactly."""
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
                    ' \'{"type": "object", "properties": {"content": {"type": "string"}}, '
                    '   "required": ["content"], "additionalProperties": false}\'::jsonb, '
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
                    " 'Propose a concrete, brief technical architecture for a URL shortener "
                    "service. Cover components and data storage only.', "
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


def test_sql_agent_registry_genuinely_resolves_the_architecture_agent(
    database_url: str,
) -> None:
    """Deterministic — no live LLM call. Proves the exact thing this
    step's own approved framing named as the tension to resolve:
    PromptedAgent's real dependencies are no longer incompatible with
    SqlAgentRegistry's zero-argument entrypoint loading, for this one,
    genuinely zero-arg-constructible entrypoint."""

    async def _run() -> None:
        await _register_and_activate_pack(database_url)
        await _seed_agent_row(database_url)

        engine = build_engine(database_url)
        try:
            registry = SqlAgentRegistry(engine)
            resolved = await registry.resolve_agent(_AGENT_ID)

            assert isinstance(resolved, Agent)
            assert isinstance(resolved, ArchitectureAgentEntrypoint)
            assert resolved.output_schema == {
                "type": "object",
                "properties": {"content": {"type": "string"}},
                "required": ["content"],
                "additionalProperties": False,
            }
        finally:
            await engine.dispose()

    asyncio.run(_run())


@pytest.mark.skipif(
    not os.environ.get(_API_KEY_ENV_VAR),
    reason=f"{_API_KEY_ENV_VAR} is not set — this live-provider suite is opt-in (ADR-0015)",
)
def test_a_real_workflow_step_genuinely_invokes_the_architecture_agent_live(
    database_url: str,
) -> None:
    """Opt-in live: the full chain this step exists to prove — a real
    `WorkflowStep` of type `agent`, dispatched through the real
    `AgentStepExecutor`, resolved through the real `SqlAgentRegistry`
    (not `InMemoryAgentRegistry`), genuinely produces an architecture
    proposal from a real Anthropic completion."""

    async def _run() -> None:
        await _register_and_activate_pack(database_url)
        await _seed_agent_row(database_url)
        await _seed_live_prompt(database_url)

        engine = build_engine(database_url)
        try:
            registry = SqlAgentRegistry(engine)
            executor = AgentStepExecutor(registry)
            step = WorkflowStep(
                id="propose_architecture",
                type=StepType.AGENT,
                agent_id=_AGENT_ID,
                prompt_id=_LIVE_PROMPT_ID,
                prompt_version=_LIVE_PROMPT_VERSION,
                model_alias="coding-strong",
            )

            outputs = await executor.execute(step)

            ArchitectureProposalOutput.model_validate(outputs)
            assert outputs["content"].strip() != ""
        finally:
            await engine.dispose()

    asyncio.run(_run())
