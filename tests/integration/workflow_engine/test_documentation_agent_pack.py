"""The fourth real, end-to-end proof in the `software-engineering`
pack's own history: the Documentation Agent, registered and activated
through the real `SqlPackLifecycleRepository`, resolved through the
real `SqlAgentRegistry` — the identical pattern
`test_architecture_agent_pack.py`/`test_build_agent_pack.py`/
`test_verification_agent_pack.py` already proved for their own agents.

**Migrated onto the Platform SDK (step 13) — the fifth and final
migration.** `_build_real_llm_gateway_and_prompt_engine` below mirrors
every other migrated agent's own identical helper — this agent's own
pre-migration `_build_real_service` used to assemble this composition
internally; it now lives here, in this file's own composition root. The
same accepted `evaluation.llm_calls` capability loss applies here too
(see the agent's own module docstring) — the fourth and final
occurrence, closing out the full set of LLM-calling agents.

Two tiers, against a real Postgres container (ADR-0015 — no mocking the
database):

1. **Deterministic, no live LLM call required** — registers the pack,
   seeds a real `catalog.agents` row naming this pack's real
   `DocumentationAgentEntrypoint`, and proves `SqlAgentRegistry`
   resolves it for real. Now supplies a real, Echo-backed
   `llm_gateway`/`prompt_engine` to `SqlAgentRegistry` itself, since
   step 9a's own injection logic genuinely requires one the moment a
   resolved entrypoint's own declared permissions include `llm:invoke`
   — the identical, already-proven consequence steps 10-12 found for
   the other three.
2. **Opt-in live** (skipped without `AIOS_SECRET_LLM_ANTHROPIC_API_KEY`,
   mirroring this pack's own prior live tests) — a genuine, positive
   difference from Architecture's/Build's own live tests, discovered
   while writing this one: this agent's real structured input
   (`workingDirectory`/`filePath`/`instruction`/`passed`/`exitCode`/
   `output`) is supplied directly via `_extract_payload`'s own
   direct-keys path, never through a Context Manager round trip — so,
   unlike those two, **this live test seeds and uses this pack's own
   real shipped prompt** (`prompts/documentation_record_artifact.md`),
   not a self-contained test-only substitute. It genuinely completes
   against the live Anthropic API and genuinely writes a real Markdown
   file to disk through the sandbox — now through the new `ToolInvoker`
   path (`context.tools.invoke`), not a directly constructed
   `SandboxedCommandTool` — resolved through the real `SqlAgentRegistry`.
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
from ai_os_kernel.workflow_engine.registry import SqlAgentRegistry
from ai_os_pack_software_engineering.agents.documentation import (
    DocumentationAgentEntrypoint,
    DocumentationAgentOutput,
)
from ai_os_sdk.contracts import PackContextReceiver
from tests.integration._postgres_fixture import postgres_container

_CONFIG_PATH = Path.cwd() / "config" / "llm.yaml"
_API_KEY_SECRET_REFERENCE = "secret://env/llm/anthropic-api-key"  # noqa: S105 — a reference URI, not a credential


async def _build_real_llm_gateway_and_prompt_engine(
    engine: AsyncEngine,
) -> tuple[KernelLLMGatewayProtocol, PromptEngine]:
    """Mirrors every other migrated agent's own identical helper — the
    real composition `documentation.py`'s own pre-migration
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
PROMPT_FILE = (
    REPO_ROOT
    / "capability_packs"
    / "software-engineering"
    / "prompts"
    / "documentation_record_artifact.md"
)

_PACK_ID = "software-engineering"
_PACK_VERSION = "0.1.0"
_AGENT_ID = f"{_PACK_ID}/documentation"
_AGENT_ENTRYPOINT = (
    "ai_os_pack_software_engineering.agents.documentation:DocumentationAgentEntrypoint"
)
_PROMPT_ID = "documentation.record_artifact"
_PROMPT_VERSION = "0.1.0"
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
    """Idempotent — mirrors this pack's own prior integration tests
    exactly."""
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
                reason="documentation agent pack integration test",
            )
        with contextlib.suppress(CapabilityManagerError):
            await repository.activate(pack_id=_PACK_ID, actor="test", reason="integration test")
    finally:
        await engine.dispose()


async def _seed_agent_row(database_url: str) -> None:
    """No automated manifest -> catalog.agents installer exists yet —
    mirrors this pack's own prior integration tests exactly."""
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


async def _seed_real_prompt(database_url: str) -> None:
    """Seeds this pack's own real shipped prompt content — see this
    module's own docstring for why the Documentation Agent's live test,
    unlike its two pack-mates, can use the real prompt rather than a
    test-only substitute."""
    content = PROMPT_FILE.read_text(encoding="utf-8")
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
                    "prompt_id": _PROMPT_ID,
                    "pack_id": _PACK_ID,
                    "version": _PROMPT_VERSION,
                    "content": content,
                },
            )
    finally:
        await engine.dispose()


def test_sql_agent_registry_genuinely_resolves_the_documentation_agent(database_url: str) -> None:
    """Deterministic. Proves the Documentation Agent is genuinely
    resolvable through SqlAgentRegistry, the same tension already
    closed for its four pack-mates.

    **The identical, already-proven consequence of step 9a applies
    here too:** this agent's own `catalog.agents` row declares both
    `llm:invoke` and `sandbox:execute`, so `SqlAgentRegistry.resolve_agent()`'s
    own real `PackContext` injection genuinely requires a real
    `llm_gateway`/`prompt_engine` to back the first (its own default
    `sandbox` already backs the second, since step 9a) — supplying none
    here would raise `AgentRegistryError`, not silently resolve."""

    async def _run() -> None:
        await _register_and_activate_pack(database_url)
        await _seed_agent_row(database_url)

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
            assert isinstance(resolved, DocumentationAgentEntrypoint)
            assert resolved.output_schema["required"] == [
                "workingDirectory",
                "documentationPath",
                "written",
                "exitCode",
                "content",
            ]
        finally:
            await engine.dispose()

    asyncio.run(_run())


@pytest.mark.skipif(
    not os.environ.get(_API_KEY_ENV_VAR),
    reason=f"{_API_KEY_ENV_VAR} is not set — this live-provider suite is opt-in (ADR-0015)",
)
def test_a_real_build_and_test_result_genuinely_produces_a_documentation_file_live(
    tmp_path: Path, database_url: str
) -> None:
    """Opt-in live: the full chain this step exists to prove — a real
    Build+Test result, resolved through the real SqlAgentRegistry,
    genuinely completes against the live Anthropic API using this
    pack's own real shipped prompt, and genuinely writes a real
    Markdown file to disk through the sandbox."""

    async def _run() -> None:
        await _register_and_activate_pack(database_url)
        await _seed_agent_row(database_url)
        await _seed_real_prompt(database_url)

        (tmp_path / "hello.py").write_text(
            "print('hello from the documentation agent live test')\n", encoding="utf-8"
        )

        engine = build_engine(database_url)
        try:
            llm_gateway, prompt_engine = await _build_real_llm_gateway_and_prompt_engine(engine)
            registry = SqlAgentRegistry(
                engine, llm_gateway=llm_gateway, prompt_engine=prompt_engine
            )
            resolved = await registry.resolve_agent(_AGENT_ID)
            assert isinstance(resolved, DocumentationAgentEntrypoint)

            outputs = await resolved.execute(
                {
                    "promptId": _PROMPT_ID,
                    "promptVersion": _PROMPT_VERSION,
                    "modelAlias": "coding-strong",
                    "workingDirectory": str(tmp_path),
                    "filePath": "hello.py",
                    "instruction": "Write a script that prints a greeting.",
                    "passed": True,
                    "exitCode": 0,
                    "output": "hello from the documentation agent live test\n",
                }
            )

            DocumentationAgentOutput.model_validate(outputs)
            assert outputs["written"] is True

            written_file = Path(outputs["workingDirectory"]) / outputs["documentationPath"]
            assert written_file.is_file()
            assert written_file.read_text(encoding="utf-8").strip() != ""
        finally:
            await engine.dispose()

    asyncio.run(_run())
