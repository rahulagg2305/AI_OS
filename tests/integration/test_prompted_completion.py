"""The "one real end-to-end path" this step approves — proven against a
real Postgres container (ADR-0015): a real ``catalog.prompts`` row is
genuinely rendered by :class:`SqlPromptCatalog`, completed, and (when
workflow/step context is supplied) genuinely recorded as a real
``evaluation.llm_calls`` row by :class:`SqlLLMCallRecorder`.

The LLM call itself uses :class:`EchoLLMGateway` here — deterministic,
no live credentials, no network — so this file proves the two *real*,
database-backed halves of the pipeline (`PromptEngine` render,
`LLMCallRecorder` write) end to end. The third real half —
:class:`AnthropicAdapter` actually completing against the live Anthropic
API — is proven by the separate, opt-in
``test_prompted_completion_live.py``, exactly mirroring the split
already established for `AnthropicAdapter` itself
(``tests/unit/kernel/llm_gateway/adapters/test_anthropic_adapter.py``
for the deterministic half, ``tests/integration/llm_gateway/
test_anthropic_adapter_live.py`` for the opt-in live half).
"""

import asyncio
import os
from collections.abc import Generator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from ai_os_kernel.llm_gateway.call_recorder import SqlLLMCallRecorder
from ai_os_kernel.llm_gateway.gateway import EchoLLMGateway
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.prompt_engine.catalog import SqlPromptCatalog
from ai_os_kernel.prompted_completion import PromptedCompletionService
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"


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


async def _seed_workflow_instance(database_url: str, workflow_id: str) -> None:
    engine = build_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                sa.text(
                    "INSERT INTO catalog.workflow_definitions "
                    "(definition_id, pack_id, version, graph, inputs_schema, "
                    " outputs_schema, declared_permissions, validated_at) "
                    "VALUES ('def_prompted_completion_test', 'se.software_engineering', "
                    " '1.0.0', '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, '[]'::jsonb, now()) "
                    "ON CONFLICT (definition_id, version) DO NOTHING"
                )
            )
            await connection.execute(
                sa.text(
                    "INSERT INTO workflow.workflow_instances "
                    "(workflow_id, definition_id, definition_version, status, "
                    " inputs, principal_id, last_event_seq) "
                    "VALUES (:workflow_id, 'def_prompted_completion_test', '1.0.0', 'created', "
                    " '{}'::jsonb, 'user_test', 0)"
                ),
                {"workflow_id": workflow_id},
            )
    finally:
        await engine.dispose()


async def _seed_agent_and_prompt(
    database_url: str, *, agent_id: str, prompt_id: str, content: str
) -> None:
    engine = build_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                sa.text(
                    "INSERT INTO catalog.agents "
                    "(agent_id, pack_id, version, entrypoint, input_schema, output_schema, "
                    " required_permissions, required_tools) "
                    "VALUES (:agent_id, 'se.software_engineering', '1.0.0', 'pack.agents:Agent', "
                    " '{}'::jsonb, '{}'::jsonb, '[]'::jsonb, '[]'::jsonb)"
                ),
                {"agent_id": agent_id},
            )
            await connection.execute(
                sa.text(
                    "INSERT INTO catalog.prompts "
                    "(prompt_id, pack_id, version, content, input_schema, content_hash) "
                    "VALUES (:prompt_id, 'se.software_engineering', '1.0.0', "
                    " :content, '{}'::jsonb, 'sha256:abc')"
                ),
                {"prompt_id": prompt_id, "content": content},
            )
    finally:
        await engine.dispose()


def test_a_real_catalog_prompt_is_rendered_completed_and_recorded(database_url: str) -> None:
    async def _run() -> None:
        await _seed_workflow_instance(database_url, "wf_prompted_completion_real")
        await _seed_agent_and_prompt(
            database_url,
            agent_id="se.software_engineering/prompted-completion-agent",
            prompt_id="prompt_prompted_completion_greeting",
            content="Hello, {{name}}! Please respond briefly.",
        )
        engine = build_engine(database_url)
        try:
            service = PromptedCompletionService(
                prompt_engine=SqlPromptCatalog(engine),
                llm_gateway=EchoLLMGateway(),
                call_recorder=SqlLLMCallRecorder(engine),
            )

            result = await service.complete_from_prompt(
                prompt_id="prompt_prompted_completion_greeting",
                prompt_version="1.0.0",
                variables={"name": "Ada"},
                model_alias="fast-cheap",
                max_output_tokens=200,
                workflow_id="wf_prompted_completion_real",
                step_id="step_1",
                agent_id="se.software_engineering/prompted-completion-agent",
            )

            # The rendered content came from the real catalog.prompts row,
            # not an in-process template — proving the real render half.
            assert result.render.content == "Hello, Ada! Please respond briefly."
            # EchoLLMGateway echoes the rendered content back, deterministically.
            assert result.response.content == "Hello, Ada! Please respond briefly."

            async with engine.connect() as connection:
                row_result = await connection.execute(
                    sa.text(
                        "SELECT * FROM evaluation.llm_calls "
                        "WHERE workflow_id = 'wf_prompted_completion_real'"
                    )
                )
                row = row_result.mappings().one()

            assert row["agent_id"] == "se.software_engineering/prompted-completion-agent"
            assert row["prompt_id"] == "prompt_prompted_completion_greeting"
            assert row["prompt_version"] == "1.0.0"
            assert row["model_alias"] == "fast-cheap"
            assert row["provider"] == "echo"
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_no_recording_happens_without_workflow_and_step_context(database_url: str) -> None:
    async def _run() -> None:
        await _seed_agent_and_prompt(
            database_url,
            agent_id="se.software_engineering/prompted-completion-unrecorded-agent",
            prompt_id="prompt_prompted_completion_unrecorded",
            content="Unrecorded prompt.",
        )
        engine = build_engine(database_url)
        try:
            service = PromptedCompletionService(
                prompt_engine=SqlPromptCatalog(engine),
                llm_gateway=EchoLLMGateway(),
                call_recorder=SqlLLMCallRecorder(engine),
            )

            await service.complete_from_prompt(
                prompt_id="prompt_prompted_completion_unrecorded",
                prompt_version="1.0.0",
                model_alias="fast-cheap",
                max_output_tokens=50,
            )

            async with engine.connect() as connection:
                count_result = await connection.execute(
                    sa.text(
                        "SELECT count(*) FROM evaluation.llm_calls "
                        "WHERE prompt_id = 'prompt_prompted_completion_unrecorded'"
                    )
                )
                assert count_result.scalar_one() == 0
        finally:
            await engine.dispose()

    asyncio.run(_run())
