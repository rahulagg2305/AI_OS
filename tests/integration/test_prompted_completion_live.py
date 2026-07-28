"""Opt-in, real-network, real-database verification of the full
"Agent / caller -> PromptEngine -> LLMGateway(AnthropicAdapter) ->
optional llm_calls recording" path this step approves — every piece
real at once: a real ``catalog.prompts`` row, a real Anthropic
completion, and a real ``evaluation.llm_calls`` row.

Skipped unless a real key is available at the documented local-dev
secret reference (``secret://env/llm/anthropic-api-key`` ->
``AIOS_SECRET_LLM_ANTHROPIC_API_KEY``), exactly mirroring
``tests/integration/llm_gateway/test_anthropic_adapter_live.py``. See
this step's own report for how to set this variable and run this file
directly to manually verify a real end-to-end call.
"""

import os
from collections.abc import Generator
from decimal import Decimal
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
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
_API_KEY_ENV_VAR = "AIOS_SECRET_LLM_ANTHROPIC_API_KEY"
_API_KEY_SECRET_REFERENCE = "secret://env/llm/anthropic-api-key"  # noqa: S105 — a reference URI, not a credential

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


async def _seed_workflow_agent_and_prompt(database_url: str) -> None:
    engine = build_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                sa.text(
                    "INSERT INTO catalog.workflow_definitions "
                    "(definition_id, pack_id, version, graph, inputs_schema, "
                    " outputs_schema, declared_permissions, validated_at) "
                    "VALUES ('def_prompted_completion_live', 'se.software_engineering', "
                    " '1.0.0', '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, '[]'::jsonb, now()) "
                    "ON CONFLICT (definition_id, version) DO NOTHING"
                )
            )
            await connection.execute(
                sa.text(
                    "INSERT INTO workflow.workflow_instances "
                    "(workflow_id, definition_id, definition_version, status, "
                    " inputs, principal_id, last_event_seq) "
                    "VALUES ('wf_prompted_completion_live', 'def_prompted_completion_live', "
                    " '1.0.0', 'created', '{}'::jsonb, 'user_test', 0)"
                )
            )
            await connection.execute(
                sa.text(
                    "INSERT INTO catalog.agents "
                    "(agent_id, pack_id, version, entrypoint, input_schema, output_schema, "
                    " required_permissions, required_tools) "
                    "VALUES ('se.software_engineering/prompted-completion-live-agent', "
                    " 'se.software_engineering', '1.0.0', 'pack.agents:Agent', "
                    " '{}'::jsonb, '{}'::jsonb, '[]'::jsonb, '[]'::jsonb)"
                )
            )
            await connection.execute(
                sa.text(
                    "INSERT INTO catalog.prompts "
                    "(prompt_id, pack_id, version, content, input_schema, content_hash) "
                    "VALUES ('prompt_prompted_completion_live', 'se.software_engineering', "
                    " '1.0.0', 'Reply with exactly the word: {{word}}', '{}'::jsonb, "
                    " 'sha256:abc')"
                )
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_real_prompt_is_rendered_completed_by_anthropic_and_recorded(
    database_url: str,
) -> None:
    await _seed_workflow_agent_and_prompt(database_url)
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

        result = await service.complete_from_prompt(
            prompt_id="prompt_prompted_completion_live",
            prompt_version="1.0.0",
            variables={"word": "pong"},
            model_alias="fast-cheap",
            max_output_tokens=16,
            workflow_id="wf_prompted_completion_live",
            step_id="step_1",
            agent_id="se.software_engineering/prompted-completion-live-agent",
        )

        assert result.render.content == "Reply with exactly the word: pong"
        assert result.response.provider == "anthropic"
        assert result.response.content.strip() != ""
        assert result.response.usage.cost_usd > Decimal("0")

        async with engine.connect() as connection:
            row_result = await connection.execute(
                sa.text(
                    "SELECT * FROM evaluation.llm_calls "
                    "WHERE workflow_id = 'wf_prompted_completion_live'"
                )
            )
            row = row_result.mappings().one()

        assert row["provider"] == "anthropic"
        assert row["prompt_id"] == "prompt_prompted_completion_live"
        assert row["agent_id"] == "se.software_engineering/prompted-completion-live-agent"
        assert row["cost_usd"] > Decimal("0")
    finally:
        await engine.dispose()
