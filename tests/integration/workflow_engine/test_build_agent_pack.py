"""The second real, end-to-end proof in the `software-engineering`
pack's own history: the Build Agent, registered and activated through
the real `SqlPackLifecycleRepository`, resolved through the real
`SqlAgentRegistry` — the identical `PromptedAgent`/`SqlAgentRegistry`
construction pattern `test_architecture_agent_pack.py` already proved
for the Architecture Agent, now proved again for an agent that also
performs a real, sandboxed side effect.

**Migrated onto the Platform SDK (step 12) — the third migration, and
the first needing real `llm_gateway`/`prompt_engine` AND a real sandbox
together.** `_build_real_llm_gateway_and_prompt_engine` below mirrors
`test_requirements_analyst_agent_pack.py`'s own identical helper — this
agent's own pre-migration `_build_real_service` used to assemble this
composition internally; it now lives here, in this file's own
composition root, since the migrated agent no longer builds anything
itself. The same accepted `evaluation.llm_calls` capability loss applies
here too (see the agent's own module docstring).

Two tiers, against a real Postgres container (ADR-0015 — no mocking the
database):

1. **Deterministic, no live LLM call required** — registers the pack,
   seeds a real `catalog.agents` row naming this pack's real
   `BuildAgentEntrypoint`, and proves `SqlAgentRegistry` resolves it for
   real. Now supplies a real, Echo-backed `llm_gateway`/`prompt_engine`
   to `SqlAgentRegistry` itself, since step 9a's own injection logic
   genuinely requires one the moment a resolved entrypoint's own
   declared permissions include `llm:invoke` — the identical,
   already-proven consequence steps 10/11 found for
   `requirements-analyst`/`architecture`.
2. **Opt-in live** (skipped without `AIOS_SECRET_LLM_ANTHROPIC_API_KEY`,
   mirroring `test_prompted_agent_live.py`/`test_architecture_agent_pack.py`)
   — a real `WorkflowStep` of type `agent`, dispatched through the real
   `AgentStepExecutor`, resolved through the real `SqlAgentRegistry`,
   genuinely completes against the live Anthropic API *and* genuinely
   writes a real file to disk through the sandbox — the full chain this
   step exists to prove, now through the new `ToolInvoker` sandbox path
   (`context.tools.invoke`), not a directly constructed
   `SandboxedCommandTool`. This is this pack's most important real proof
   of the ToolInvoker migration, since Build is the pipeline's real
   file-writer. Seeds a minimal, self-contained, test-only prompt (not
   this pack's own shipped `prompts/build_write_file.md`, which needs a
   real Context Manager-supplied `context` variable this focused proof
   does not stand up — the identical choice `test_architecture_agent_pack.py`
   itself already makes for the same reason). `SqlAgentRegistry`'s own
   default `sandbox` (a real `build_default_sandbox_executor()`, since
   step 9a) resolves to the real, config-driven default backend — this
   test's own `BuildAgentEntrypoint` therefore also relies on its own
   `python_command` constructor default (`("python3",)`, matching
   `DockerSandbox`, the real system-wide default) being correct for
   whatever backend that default actually resolves to today.
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
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.capability_manager.errors import CapabilityManagerError
from ai_os_kernel.capability_manager.repository import SqlPackLifecycleRepository
from ai_os_kernel.llm_gateway.adapters.anthropic_adapter import (
    PROVIDER_NAME,
    build_anthropic_adapter,
)
from ai_os_kernel.llm_gateway.adapters.model_config import load_provider_config
from ai_os_kernel.llm_gateway.gateway import DispatchingLLMGateway, EchoLLMGateway
from ai_os_kernel.llm_gateway.gateway import LLMGateway as KernelLLMGatewayProtocol
from ai_os_kernel.llm_gateway.router import RoutingDecision, StaticRouter
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.prompt_engine.catalog import SqlPromptCatalog
from ai_os_kernel.prompt_engine.renderer import InMemoryPromptEngine, PromptEngine
from ai_os_kernel.secrets_manager.env_provider import EnvSecretProvider
from ai_os_kernel.workflow_engine.agent import Agent
from ai_os_kernel.workflow_engine.models import StepType, WorkflowStep
from ai_os_kernel.workflow_engine.registry import SqlAgentRegistry
from ai_os_kernel.workflow_engine.step_executor import AgentStepExecutor
from ai_os_pack_software_engineering.agents.build import BuildAgentEntrypoint, BuildAgentOutput
from ai_os_sdk.contracts import PackContextReceiver
from tests.integration._postgres_fixture import postgres_container

_CONFIG_PATH = Path.cwd() / "config" / "llm.yaml"
_API_KEY_SECRET_REFERENCE = "secret://env/llm/anthropic-api-key"  # noqa: S105 — a reference URI, not a credential


async def _build_real_llm_gateway_and_prompt_engine(
    engine: AsyncEngine,
) -> tuple[KernelLLMGatewayProtocol, PromptEngine]:
    """Mirrors `test_requirements_analyst_agent_pack.py`'s own identical
    helper — the real composition `build.py`'s own pre-migration
    `_build_real_service` used to assemble internally."""
    provider_config = load_provider_config(_CONFIG_PATH)
    router = StaticRouter(
        routes={
            alias: RoutingDecision(
                provider=provider_config.providers.get(alias, PROVIDER_NAME), model_id=model_id
            )
            for alias, model_id in provider_config.model_ids.items()
        }
    )
    anthropic_gateway = await build_anthropic_adapter(
        secret_provider=EnvSecretProvider(),
        api_key_secret_reference=_API_KEY_SECRET_REFERENCE,
        router=router,
        pricing=provider_config.pricing,
    )
    llm_gateway = DispatchingLLMGateway(router=router, gateways={PROVIDER_NAME: anthropic_gateway})
    return llm_gateway, SqlPromptCatalog(engine)


REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
PACK_ROOT = REPO_ROOT / "capability_packs" / "software-engineering"

_PACK_ID = "software-engineering"
_PACK_VERSION = "0.1.0"
_AGENT_ID = f"{_PACK_ID}/build"
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
    is expected, not an error worth failing over.

    **``pack_root=PACK_ROOT`` (added this step) genuinely derives and
    writes this pack's real ``catalog.agents``/``catalog.prompts``/
    ``catalog.tools`` rows** — see
    ``ai_os_kernel.capability_manager.manifest_catalog_installer``.
    Replaces the hand-written ``catalog.agents`` row a prior version of
    this file inserted via raw SQL (``_seed_agent_row``, removed)."""
    engine = build_engine(database_url)
    try:
        repository = SqlPackLifecycleRepository(engine)
        with (PACK_ROOT / "manifest.yaml").open(encoding="utf-8") as fh:
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
                pack_root=PACK_ROOT,
            )
        with contextlib.suppress(CapabilityManagerError):
            await repository.activate(pack_id=_PACK_ID, actor="test", reason="integration test")
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
    real side effect.

    **The identical, already-proven consequence of step 9a applies
    here too:** this agent's own `catalog.agents` row declares both
    `llm:invoke` and `sandbox:execute`, so `SqlAgentRegistry.resolve_agent()`'s
    own real `PackContext` injection genuinely requires a real
    `llm_gateway`/`prompt_engine` to back the first (its own default
    `sandbox` already backs the second, since step 9a) — supplying none
    here would raise `AgentRegistryError`, not silently resolve."""

    async def _run() -> None:
        await _register_and_activate_pack(database_url)

        engine = build_engine(database_url)
        try:
            registry = SqlAgentRegistry(
                engine,
                llm_gateway=EchoLLMGateway(),
                prompt_engine=InMemoryPromptEngine(templates={}),
            )
            resolved = await registry.resolve_agent(_AGENT_ID)

            assert isinstance(resolved, Agent)
            assert isinstance(resolved, PackContextReceiver)
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
            llm_gateway, prompt_engine = await _build_real_llm_gateway_and_prompt_engine(engine)
            registry = SqlAgentRegistry(
                engine, llm_gateway=llm_gateway, prompt_engine=prompt_engine
            )
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
