"""The second real, end-to-end proof in the `software-engineering`
pack's own history: the Build Agent, registered and activated through
the real `SqlPackLifecycleRepository`, resolved through the real
`SqlAgentRegistry` — the identical `PromptedAgent`/`SqlAgentRegistry`
construction pattern `test_architecture_agent_pack.py` already proved
for the Architecture Agent, now proved again for an agent that also
performs a real, sandboxed side effect.

Two tiers, against a real Postgres container (ADR-0015 — no mocking the
database):

1. **Deterministic, no live LLM call required** — registers the pack,
   seeds a real `catalog.agents` row naming this pack's real
   `BuildAgentEntrypoint`, and proves `SqlAgentRegistry` resolves it for
   real.
2. **Opt-in live** (skipped without `AIOS_SECRET_LLM_ANTHROPIC_API_KEY`,
   mirroring `test_prompted_agent_live.py`/`test_architecture_agent_pack.py`)
   — a real `WorkflowStep` of type `agent`, dispatched through the real
   `AgentStepExecutor`, resolved through the real `SqlAgentRegistry`,
   genuinely completes against the live Anthropic API *and* genuinely
   writes a real file to disk through the sandbox — the full chain this
   step exists to prove. Seeds a minimal, self-contained, test-only
   prompt (not this pack's own shipped `prompts/build_write_file.md`,
   which needs a real Context Manager-supplied `context` variable this
   focused proof does not stand up — the identical choice
   `test_architecture_agent_pack.py` itself already makes for the same
   reason).
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
from ai_os_pack_software_engineering.agents.build import BuildAgentEntrypoint, BuildAgentOutput
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

_PACK_ID = "software-engineering"
_PACK_VERSION = "0.1.0"
_AGENT_ID = f"{_PACK_ID}/build"
_AGENT_ENTRYPOINT = "ai_os_pack_software_engineering.agents.build:BuildAgentEntrypoint"
_LIVE_PROMPT_ID = "build.write_file.live_test"
_LIVE_PROMPT_VERSION = "0.1.0"
_LIVE_PROMPT_CONTENT = (
    "Produce exactly one file implementing this instruction: a Python script that, "
    "when run, prints exactly the text: hello from the build agent live test\n\n"
    "Respond in EXACTLY this format, and nothing else — no prose, no markdown fences:\n\n"
    "FILE_PATH: <a single relative file path>\n"
    "FILE_CONTENT_BEGIN\n"
    "<the complete file content, verbatim>\n"
    "FILE_CONTENT_END"
)
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
    """Idempotent — mirrors test_architecture_agent_pack.py's own
    helper exactly, including why: a second registration/activation of
    the same pack (by an earlier test in this module, or in
    test_architecture_agent_pack.py against the same container class)
    is expected, not an error worth failing over."""
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
                reason="build agent pack integration test",
            )
        with contextlib.suppress(CapabilityManagerError):
            await repository.activate(pack_id=_PACK_ID, actor="test", reason="integration test")
    finally:
        await engine.dispose()


async def _seed_agent_row(database_url: str) -> None:
    """No automated manifest -> catalog.agents installer exists yet —
    mirrors test_registry.py's/test_architecture_agent_pack.py's own
    direct seeding exactly."""
    engine = build_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                sa.text(
                    "INSERT INTO catalog.agents "
                    "(agent_id, pack_id, version, entrypoint, input_schema, output_schema, "
                    " required_permissions, required_tools) "
                    "VALUES (:agent_id, :pack_id, :version, :entrypoint, "
                    " '{}'::jsonb, '{}'::jsonb, "
                    " '[\"llm:invoke\", \"sandbox:execute\"]'::jsonb, '[]'::jsonb) "
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
                    "VALUES (:prompt_id, :pack_id, :version, :content, '{}'::jsonb, 'sha256:abc') "
                    "ON CONFLICT (prompt_id, version) DO NOTHING"
                ),
                {
                    "prompt_id": _LIVE_PROMPT_ID,
                    "pack_id": _PACK_ID,
                    "version": _LIVE_PROMPT_VERSION,
                    "content": _LIVE_PROMPT_CONTENT,
                },
            )
    finally:
        await engine.dispose()


def test_sql_agent_registry_genuinely_resolves_the_build_agent(database_url: str) -> None:
    """Deterministic — no live LLM call, no sandboxed write. Proves the
    Build Agent is genuinely resolvable through SqlAgentRegistry, the
    same tension test_architecture_agent_pack.py already closed for the
    Architecture Agent, now closed for an agent that also performs a
    real side effect."""

    async def _run() -> None:
        await _register_and_activate_pack(database_url)
        await _seed_agent_row(database_url)

        engine = build_engine(database_url)
        try:
            registry = SqlAgentRegistry(engine)
            resolved = await registry.resolve_agent(_AGENT_ID)

            assert isinstance(resolved, Agent)
            assert isinstance(resolved, BuildAgentEntrypoint)
            assert resolved.output_schema["required"] == [
                "workingDirectory",
                "filePath",
                "written",
                "exitCode",
                "stdout",
                "stderr",
                "instruction",
            ]
        finally:
            await engine.dispose()

    asyncio.run(_run())


@pytest.mark.skipif(
    not os.environ.get(_API_KEY_ENV_VAR),
    reason=f"{_API_KEY_ENV_VAR} is not set — this live-provider suite is opt-in (ADR-0015)",
)
def test_a_real_workflow_step_genuinely_writes_a_file_through_the_build_agent_live(
    database_url: str,
) -> None:
    """Opt-in live: the full chain this step exists to prove — a real
    `WorkflowStep` of type `agent`, resolved through the real
    `SqlAgentRegistry`, genuinely completes against the live Anthropic
    API *and* genuinely writes a real file to disk through the sandbox."""

    async def _run() -> None:
        await _register_and_activate_pack(database_url)
        await _seed_agent_row(database_url)
        await _seed_live_prompt(database_url)

        engine = build_engine(database_url)
        try:
            # A fresh SqlAgentRegistry.resolve_agent() call constructs a
            # brand-new BuildAgentEntrypoint every time (no caching) —
            # AgentStepExecutor resolves and uses its own instance
            # internally, so this test only ever inspects the *outputs*
            # of that call (workingDirectory + filePath together), never
            # a separately-resolved instance's own private directory,
            # which would be a different, never-executed instance.
            registry = SqlAgentRegistry(engine)
            executor = AgentStepExecutor(registry)
            step = WorkflowStep(
                id="write_file_live",
                type=StepType.AGENT,
                agent_id=_AGENT_ID,
                prompt_id=_LIVE_PROMPT_ID,
                prompt_version=_LIVE_PROMPT_VERSION,
                model_alias="coding-strong",
            )

            outputs = await executor.execute(step)

            BuildAgentOutput.model_validate(outputs)
            assert outputs["written"] is True

            written_file = Path(outputs["workingDirectory"]) / outputs["filePath"]
            assert written_file.is_file()
            assert written_file.read_text(encoding="utf-8").strip() != ""
        finally:
            await engine.dispose()

    asyncio.run(_run())
