"""Opt-in, real-network, real-database verification of the full "wire
one thin real Agent" path: a real `WorkflowStep` declaring `promptId`/
`promptVersion`/`modelAlias` is executed by the real
`AgentStepExecutor`, which resolves `PromptedAgent` through a real
`AgentRegistry` and forwards those three fields as `inputs` — the agent
then renders a real `catalog.prompts` row and completes it against the
live Anthropic API.

Skipped unless a real key is available at the documented local-dev
secret reference, exactly mirroring
``tests/integration/test_prompted_completion_live.py`` and
``tests/integration/llm_gateway/test_anthropic_adapter_live.py``. This
is the top of the chain those two files prove the middle and bottom of:
Workflow Engine step -> AgentStepExecutor -> registry -> PromptedAgent
-> PromptedCompletionService -> AnthropicAdapter.
"""

import os
from collections.abc import Generator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from ai_os_kernel.llm_gateway.adapters.anthropic_adapter import PROVIDER_NAME
from ai_os_kernel.llm_gateway.adapters.model_config import load_provider_config
from ai_os_kernel.llm_gateway.router import RoutingDecision, StaticRouter
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.prompted_completion import build_anthropic_prompted_completion_service
from ai_os_kernel.secrets_manager.env_provider import EnvSecretProvider
from ai_os_kernel.workflow_engine.models import StepType, WorkflowStep
from ai_os_kernel.workflow_engine.prompted_agent import PromptedAgent
from ai_os_kernel.workflow_engine.registry import InMemoryAgentRegistry
from ai_os_kernel.workflow_engine.step_executor import AgentStepExecutor
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
_API_KEY_ENV_VAR = "AIOS_SECRET_LLM_ANTHROPIC_API_KEY"
_API_KEY_SECRET_REFERENCE = "secret://env/llm/anthropic-api-key"  # noqa: S105 — a reference URI, not a credential
_AGENT_ID = "se.software_engineering/prompted-agent-live"

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
                    "VALUES ('prompt_prompted_agent_live', 'se.software_engineering', '1.0.0', "
                    " 'Reply with exactly the word: pong', '{}'::jsonb, 'sha256:abc') "
                    "ON CONFLICT (prompt_id, version) DO NOTHING"
                )
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_an_agent_step_genuinely_calls_anthropic_through_the_registry(
    database_url: str,
) -> None:
    await _seed_prompt(database_url)
    config = load_provider_config(REPO_ROOT / "config" / "llm.yaml")
    engine = build_engine(database_url)
    try:
        service = await build_anthropic_prompted_completion_service(
            engine=engine,
            secret_provider=EnvSecretProvider(),
            api_key_secret_reference=_API_KEY_SECRET_REFERENCE,
            router=StaticRouter(
                routes={
                    alias: RoutingDecision(
                        provider=config.providers.get(alias, PROVIDER_NAME), model_id=model_id
                    )
                    for alias, model_id in config.model_ids.items()
                }
            ),
            pricing=config.pricing,
        )
        agent = PromptedAgent(service=service, max_output_tokens=16)
        registry = InMemoryAgentRegistry({_AGENT_ID: agent})
        executor = AgentStepExecutor(registry)
        step = WorkflowStep(
            id="ask_anthropic",
            type=StepType.AGENT,
            agent_id=_AGENT_ID,
            prompt_id="prompt_prompted_agent_live",
            prompt_version="1.0.0",
            model_alias="fast-cheap",
        )

        outputs = await executor.execute(step)

        assert "content" in outputs
        assert outputs["content"].strip() != ""
    finally:
        await engine.dispose()
