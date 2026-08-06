"""The real, end-to-end proof of the Requirements Analyst Agent —
mirrors ``test_architecture_agent_pack.py`` exactly: a real Capability
Pack (`capability_packs/software-engineering`), registered and activated
through the real `SqlPackLifecycleRepository`, resolved through the
real `SqlAgentRegistry` — not `InMemoryAgentRegistry`.

**Migrated onto the Platform SDK (step 10) — no more agent-internal lazy
build.** This agent used to compose its own real
`PromptedCompletionService` on first `execute()`; it now depends
entirely on a `PackContext` `SqlAgentRegistry` itself injects (step 9a),
built from real `llm_gateway`/`prompt_engine` objects this file now
supplies directly to `SqlAgentRegistry`'s own constructor —
`_build_real_llm_gateway_and_prompt_engine` below is the identical real
composition the agent's own pre-migration `_build_real_service` used to
assemble internally, moved to this file's own composition root since
the agent no longer builds anything itself.

**The "no call-recording surface in v1.0.0" capability loss this
docstring used to name here is now closed (`P04-S01-M12-T10`).**
`SqlAgentRegistry` now accepts an optional `call_recorder`, threaded
through `build_pack_context`/`LLMGatewayAdapter`; every real completion
through this agent's own real `TraceContext` (`workflow_id`/`step_id`/
`agent_id`/`prompt_id`/`prompt_version`, all real by the time the
entrypoint builds it) is recorded to `evaluation.llm_calls` again, the
identical row shape `SqlLLMCallRecorder` always wrote before migration
— reusing that class unchanged, not a new mechanism.
`test_a_deterministic_completion_genuinely_records_a_real_llm_calls_row`
below proves it without a live credential.

Two tiers, against a real Postgres container (ADR-0015 — no mocking the
database):

1. **Deterministic, no live LLM call required** — registers the pack,
   seeds a real `catalog.agents` row naming this pack's real
   `RequirementsAnalystAgentEntrypoint`, and proves `SqlAgentRegistry`
   resolves it for real. Now supplies a real, Echo-backed
   `llm_gateway`/`prompt_engine` to `SqlAgentRegistry` itself, since
   step 9a's own injection logic genuinely requires one the moment a
   resolved entrypoint's own declared permissions include `llm:invoke`
   — a real, discovered consequence of step 9a proven here, not assumed.
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
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.capability_manager.errors import CapabilityManagerError
from ai_os_kernel.capability_manager.repository import SqlPackLifecycleRepository
from ai_os_kernel.llm_gateway.adapters.anthropic_adapter import (
    PROVIDER_NAME,
    build_anthropic_adapter,
)
from ai_os_kernel.llm_gateway.adapters.model_config import load_provider_config
from ai_os_kernel.llm_gateway.call_recorder import SqlLLMCallRecorder
from ai_os_kernel.llm_gateway.gateway import DispatchingLLMGateway, EchoLLMGateway
from ai_os_kernel.llm_gateway.gateway import LLMGateway as KernelLLMGatewayProtocol
from ai_os_kernel.llm_gateway.router import RoutingDecision, StaticRouter
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.evaluation_schema import llm_calls
from ai_os_kernel.prompt_engine.catalog import SqlPromptCatalog
from ai_os_kernel.prompt_engine.renderer import InMemoryPromptEngine, PromptEngine
from ai_os_kernel.secrets_manager.env_provider import EnvSecretProvider
from ai_os_kernel.workflow_engine.agent import Agent
from ai_os_kernel.workflow_engine.models import StepType, WorkflowStep
from ai_os_kernel.workflow_engine.registry import SqlAgentRegistry
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from ai_os_kernel.workflow_engine.step_executor import AgentStepExecutor
from ai_os_pack_software_engineering.agents.requirements_analyst import (
    RequirementsAnalysisOutput,
    RequirementsAnalystAgentEntrypoint,
)
from ai_os_sdk.contracts import PackContextReceiver
from tests.integration._postgres_fixture import postgres_container

_CONFIG_PATH = Path.cwd() / "config" / "llm.yaml"
_API_KEY_SECRET_REFERENCE = "secret://env/llm/anthropic-api-key"  # noqa: S105 — a reference URI, not a credential


async def _build_real_llm_gateway_and_prompt_engine(
    engine: AsyncEngine,
) -> tuple[KernelLLMGatewayProtocol, PromptEngine]:
    """The identical real composition
    `ai_os_pack_software_engineering.agents.requirements_analyst`'s own
    pre-migration `_build_real_service` used to assemble internally —
    moved here, to this file's own composition root, since the migrated
    agent no longer builds anything itself. Mirrors `architecture.py`'s
    own `_build_real_service` exactly, minus the
    `PromptedCompletionService`/call-recorder wrapper this agent no
    longer needs (see this module's own docstring for that real,
    accepted capability loss)."""
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
_AGENT_ID = f"{_PACK_ID}/requirements-analyst"
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
    `test_architecture_agent_pack.py`'s own helper exactly.

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
                reason="requirements analyst agent pack integration test",
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
    """Deterministic — no live LLM call. Proves this pack's second real
    `PackContextReceiver`-migrated agent resolves through the real
    `SqlAgentRegistry` exactly as its first (`qa-test`, step 9) did.

    **A real, discovered consequence of step 9a, proven here rather than
    assumed:** this agent's own `catalog.agents` row declares
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
            assert isinstance(resolved, RequirementsAnalystAgentEntrypoint)
            assert resolved.output_schema == {
                "type": "object",
                "properties": {
                    "analysis": {"type": "string"},
                    "specificationItems": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["analysis"],
                "additionalProperties": False,
            }
        finally:
            await engine.dispose()

    asyncio.run(_run())


async def _seed_workflow_instance_for_recording(engine: AsyncEngine) -> str:
    """A real `workflow_instances` row — `evaluation.llm_calls.workflow_id`
    is a real foreign key to it, the identical dependency
    `test_run_manifest_recorder.py`'s own `_seed_workflow_definition`
    already establishes for the same reason."""
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                "INSERT INTO catalog.workflow_definitions "
                "(definition_id, version, pack_id, graph, inputs_schema, "
                " outputs_schema, declared_permissions, validated_at) "
                "VALUES ('test.call-recording-workflow', '1.0.0', :pack_id, '{}'::jsonb, "
                " '{}'::jsonb, '{}'::jsonb, '[]'::jsonb, now()) "
                "ON CONFLICT (definition_id, version) DO NOTHING"
            ),
            {"pack_id": _PACK_ID},
        )
    instance = await SqlWorkflowInstanceRepository(engine).create(
        definition_id="test.call-recording-workflow",
        definition_version="1.0.0",
        inputs={},
        principal_id="test-principal",
    )
    return instance.workflow_id


def test_a_deterministic_completion_genuinely_records_a_real_llm_calls_row(
    database_url: str,
) -> None:
    """Real proof for `P04-S01-M12-T10`: a genuine completion through
    this pack's own real `RequirementsAnalystAgentEntrypoint` — resolved
    through the real `SqlAgentRegistry`, backed by real `catalog.agents`/
    `catalog.prompts` rows the real pack installer already wrote — now
    produces a real, populated `evaluation.llm_calls` row. Echo-backed
    for determinism (no live credential); the mechanism itself does not
    depend on which provider is behind `LLMGatewayAdapter`.

    Calls the resolved entrypoint's own `execute()` directly, not
    through `AgentStepExecutor` — this focused proof does not need a
    full `WorkflowStep`/Context Manager assembly, only the same real
    `workflowId`/`stepId`/`agentId`/`promptId`/`promptVersion` fields
    `AgentStepExecutor` itself would supply (`P04-S01-M12-T09`), plus an
    explicit `variables["context"]` satisfying `requirements_analysis.md`'s
    own real `{{context}}` placeholder (`render_template` is strict —
    a missing placeholder raises, not silently blanks)."""

    async def _run() -> None:
        await _register_and_activate_pack(database_url)

        engine = build_engine(database_url)
        try:
            workflow_id = await _seed_workflow_instance_for_recording(engine)
            registry = SqlAgentRegistry(
                engine,
                llm_gateway=EchoLLMGateway(),
                prompt_engine=SqlPromptCatalog(engine),
                call_recorder=SqlLLMCallRecorder(engine),
            )
            resolved = await registry.resolve_agent(_AGENT_ID)

            outputs = await resolved.execute(
                {
                    "workflowId": workflow_id,
                    "stepId": "analyze_requirements",
                    "agentId": _AGENT_ID,
                    "promptId": "requirements.analyze",
                    "promptVersion": "0.1.0",
                    "modelAlias": "fast-cheap",
                    "variables": {"context": "Build a URL shortener service."},
                }
            )

            RequirementsAnalysisOutput.model_validate(outputs)

            async with engine.connect() as connection:
                call_row = (
                    (
                        await connection.execute(
                            sa.select(llm_calls).where(llm_calls.c.workflow_id == workflow_id)
                        )
                    )
                    .mappings()
                    .one()
                )

            # Before P04-S01-M12-T10, LLMGatewayAdapter.complete() never
            # recorded anything -- this row would not exist at all.
            assert call_row["step_id"] == "analyze_requirements"
            assert call_row["agent_id"] == _AGENT_ID
            assert call_row["prompt_id"] == "requirements.analyze"
            assert call_row["prompt_version"] == "0.1.0"
            assert call_row["provider"] == "echo"
            assert call_row["model_id"] == "echo-1"
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
        await _seed_live_prompt(database_url)

        engine = build_engine(database_url)
        try:
            llm_gateway, prompt_engine = await _build_real_llm_gateway_and_prompt_engine(engine)
            registry = SqlAgentRegistry(
                engine, llm_gateway=llm_gateway, prompt_engine=prompt_engine
            )
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
