"""The first real, end-to-end proof of a `tier1`-free, genuinely
sandbox-independent pipeline link: a real Capability Pack
(`capability_packs/software-engineering`), registered and activated
through the real `SqlPackLifecycleRepository`, resolved through the
real `SqlAgentRegistry` — not `InMemoryAgentRegistry`, the boundary this
step's own approved framing names as the thing to finally cross for a
`PromptedAgent`-backed agent.

**Migrated onto the Platform SDK (step 11) — no more agent-internal lazy
build.** This agent used to compose its own real
`PromptedCompletionService` on first `execute()`; it now depends
entirely on a `PackContext` `SqlAgentRegistry` itself injects (step 9a),
built from real `llm_gateway`/`prompt_engine` objects this file now
supplies directly to `SqlAgentRegistry`'s own constructor —
`_build_real_llm_gateway_and_prompt_engine` below is the identical real
composition the agent's own pre-migration `_build_real_service` used to
assemble internally, moved to this file's own composition root, mirroring
`test_requirements_analyst_agent_pack.py`'s own identical step-10 move.
The same accepted capability loss applies: this test's own real, live
completion below is no longer recorded to `evaluation.llm_calls` (no SDK
Telemetry surface exists in v1.0.0 — see the agent's own module
docstring, and `feature_inventory.md`'s Platform SDK tracking, for the
full reasoning).

Two tiers, against a real Postgres container (ADR-0015 — no mocking the
database):

1. **Deterministic, no live LLM call required** — registers the pack,
   seeds a real `catalog.agents` row naming this pack's real
   `ArchitectureAgentEntrypoint`, and proves `SqlAgentRegistry` resolves
   it for real. Now supplies a real, Echo-backed `llm_gateway`/
   `prompt_engine` to `SqlAgentRegistry` itself, since step 9a's own
   injection logic genuinely requires one the moment a resolved
   entrypoint's own declared permissions include `llm:invoke` — the
   identical, already-proven consequence step 10 found for
   `requirements-analyst`.
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
from ai_os_pack_software_engineering.agents.architecture import (
    ArchitectureAgentEntrypoint,
    ArchitectureProposalOutput,
)
from ai_os_sdk.contracts import PackContextReceiver
from tests.integration._postgres_fixture import postgres_container

_CONFIG_PATH = Path.cwd() / "config" / "llm.yaml"
_API_KEY_SECRET_REFERENCE = "secret://env/llm/anthropic-api-key"  # noqa: S105 — a reference URI, not a credential


async def _build_real_llm_gateway_and_prompt_engine(
    engine: AsyncEngine,
) -> tuple[KernelLLMGatewayProtocol, PromptEngine]:
    """The identical real composition
    `ai_os_pack_software_engineering.agents.architecture`'s own
    pre-migration `_build_real_service` used to assemble internally —
    moved here, to this file's own composition root, since the migrated
    agent no longer builds anything itself. Mirrors
    `test_requirements_analyst_agent_pack.py`'s own identical helper."""
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
_AGENT_ID = f"{_PACK_ID}/architecture"
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
    an error worth failing the test over.

    **``pack_root=PACK_ROOT`` (added this step) genuinely derives and
    writes this pack's real ``catalog.agents``/``catalog.prompts``/
    ``catalog.tools`` rows** — see
    ``ai_os_kernel.capability_manager.manifest_catalog_installer``.
    This replaces the hand-written ``catalog.agents`` row a prior
    version of this file inserted via raw SQL (``_seed_agent_row``,
    removed) — that row is now a real, correct-per-agent by-product of
    registration itself, not a second, hand-maintained copy."""
    engine = build_engine(database_url)
    try:
        repository = SqlPackLifecycleRepository(engine)
        with (PACK_ROOT / "manifest.yaml").open(encoding="utf-8") as fh:
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
                pack_root=PACK_ROOT,
            )
        with contextlib.suppress(CapabilityManagerError):
            # Already activated by an earlier test in this module.
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
    """Deterministic — no live LLM call. Proves this pack's third real
    `PackContextReceiver`-migrated agent resolves through the real
    `SqlAgentRegistry` exactly as `qa-test` (step 9) and
    `requirements-analyst` (step 10) already did.

    **The identical, already-proven consequence of step 9a applies
    here too:** this agent's own `catalog.agents` row declares
    `llm:invoke`, so `SqlAgentRegistry.resolve_agent()`'s own real
    `PackContext` injection genuinely requires a real `llm_gateway`/
    `prompt_engine` to back it — supplying none here would raise
    `AgentRegistryError`, not silently resolve. A real, Echo-backed pair
    is enough to prove resolution deterministically; the live tier below
    is what proves a real Anthropic completion."""

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
        await _seed_live_prompt(database_url)

        engine = build_engine(database_url)
        try:
            llm_gateway, prompt_engine = await _build_real_llm_gateway_and_prompt_engine(engine)
            registry = SqlAgentRegistry(
                engine, llm_gateway=llm_gateway, prompt_engine=prompt_engine
            )
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
