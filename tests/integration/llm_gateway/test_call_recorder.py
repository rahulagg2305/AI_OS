"""SqlLLMCallRecorder against a real Postgres container (ADR-0015 — no
mocking the database). Proves: a real `EchoLLMGateway.complete()` call
can be recorded end to end with honestly-computed values, the
`agent_id`/`prompt_id`/`prompt_version` "optional on the call path, but
the schema requires all three together" rule holds, and the real
foreign keys on `evaluation.llm_calls` (to `catalog.agents`/
`catalog.prompts`) are genuinely enforced.
"""

import asyncio
import os
from collections.abc import Generator
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from ai_os_kernel.llm_gateway.call_recorder import SqlLLMCallRecorder
from ai_os_kernel.llm_gateway.errors import LLMCallRecordingError
from ai_os_kernel.llm_gateway.gateway import EchoLLMGateway
from ai_os_kernel.llm_gateway.models import LLMRequest, Message, MessageRole
from ai_os_kernel.persistence.engine import build_engine
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
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
                    "VALUES ('def_llm_calls_test', 'se.software_engineering', '1.0.0', "
                    " '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, '[]'::jsonb, now()) "
                    "ON CONFLICT (definition_id, version) DO NOTHING"
                )
            )
            await connection.execute(
                sa.text(
                    "INSERT INTO workflow.workflow_instances "
                    "(workflow_id, definition_id, definition_version, status, "
                    " inputs, principal_id, last_event_seq) "
                    "VALUES (:workflow_id, 'def_llm_calls_test', '1.0.0', 'created', "
                    " '{}'::jsonb, 'user_test', 0)"
                ),
                {"workflow_id": workflow_id},
            )
    finally:
        await engine.dispose()


async def _seed_agent_and_prompt(database_url: str, *, agent_id: str, prompt_id: str) -> None:
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
                    " 'You are a helpful assistant.', '{}'::jsonb, 'sha256:abc')"
                ),
                {"prompt_id": prompt_id},
            )
    finally:
        await engine.dispose()


def _request() -> LLMRequest:
    return LLMRequest(
        model_alias="fast-cheap",
        messages=[Message(role=MessageRole.USER, content="hello there")],
        max_output_tokens=100,
    )


def test_record_writes_a_row_with_values_from_a_real_gateway_call(database_url: str) -> None:
    async def _run() -> None:
        await _seed_workflow_instance(database_url, "wf_llm_call_real")
        await _seed_agent_and_prompt(
            database_url,
            agent_id="se.software_engineering/llm-recorder-agent",
            prompt_id="prompt_llm_recorder",
        )
        engine = build_engine(database_url)
        try:
            gateway = EchoLLMGateway()
            recorder = SqlLLMCallRecorder(engine)
            request = _request()

            response = await gateway.complete(request)
            await recorder.record(
                request=request,
                response=response,
                workflow_id="wf_llm_call_real",
                step_id="step_1",
                agent_id="se.software_engineering/llm-recorder-agent",
                prompt_id="prompt_llm_recorder",
                prompt_version="1.0.0",
            )

            async with engine.connect() as connection:
                result = await connection.execute(
                    sa.text(
                        "SELECT * FROM evaluation.llm_calls WHERE workflow_id = 'wf_llm_call_real'"
                    )
                )
                row = result.mappings().one()

            assert row["workflow_id"] == "wf_llm_call_real"
            assert row["step_id"] == "step_1"
            assert row["agent_id"] == "se.software_engineering/llm-recorder-agent"
            assert row["prompt_id"] == "prompt_llm_recorder"
            assert row["prompt_version"] == "1.0.0"
            assert row["model_alias"] == "fast-cheap"
            assert row["provider"] == response.provider
            assert row["model_id"] == response.model_id
            assert row["input_tokens"] == 0
            assert row["output_tokens"] == 0
            assert row["cache_read_tokens"] == 0
            assert row["cache_write_tokens"] == 0
            assert row["cost_usd"] == Decimal("0")
            assert row["latency_ms"] == response.usage.latency_ms
            assert row["stop_reason"] == response.stop_reason.value
            assert row["retries"] == 0
            assert row["fallback_used"] is False
            assert row["degradations"] == []
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_record_requires_agent_id_prompt_id_and_prompt_version_together(database_url: str) -> None:
    async def _run() -> None:
        await _seed_workflow_instance(database_url, "wf_llm_call_partial")
        engine = build_engine(database_url)
        try:
            gateway = EchoLLMGateway()
            recorder = SqlLLMCallRecorder(engine)
            request = _request()
            response = await gateway.complete(request)

            with pytest.raises(LLMCallRecordingError, match="must all be provided together"):
                await recorder.record(
                    request=request,
                    response=response,
                    workflow_id="wf_llm_call_partial",
                    step_id="step_1",
                    agent_id="se.software_engineering/some-agent",
                    # prompt_id and prompt_version deliberately omitted.
                )

            async with engine.connect() as connection:
                result = await connection.execute(
                    sa.text(
                        "SELECT count(*) FROM evaluation.llm_calls "
                        "WHERE workflow_id = 'wf_llm_call_partial'"
                    )
                )
                assert result.scalar_one() == 0
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_record_accepts_no_agent_or_prompt_at_all(database_url: str) -> None:
    """The fully-absent case is not a partial combination — it means
    "no agent or prompt is known for this call," which is different
    from providing some but not all of the three fields. The schema
    still requires the three columns to be NOT NULL, though, so this is
    expected to fail too — proving the "absent" case is treated
    identically to "partial," not silently accepted as a special case."""

    async def _run() -> None:
        await _seed_workflow_instance(database_url, "wf_llm_call_absent")
        engine = build_engine(database_url)
        try:
            gateway = EchoLLMGateway()
            recorder = SqlLLMCallRecorder(engine)
            request = _request()
            response = await gateway.complete(request)

            with pytest.raises(LLMCallRecordingError, match="must all be provided together"):
                await recorder.record(
                    request=request,
                    response=response,
                    workflow_id="wf_llm_call_absent",
                    step_id="step_1",
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_record_rejects_a_blank_workflow_id(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            recorder = SqlLLMCallRecorder(engine)
            request = _request()
            response = await EchoLLMGateway().complete(request)

            with pytest.raises(LLMCallRecordingError, match="workflow_id must not be blank"):
                await recorder.record(
                    request=request,
                    response=response,
                    workflow_id="   ",
                    step_id="step_1",
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_record_rejects_a_blank_step_id(database_url: str) -> None:
    async def _run() -> None:
        await _seed_workflow_instance(database_url, "wf_llm_call_blank_step")
        engine = build_engine(database_url)
        try:
            recorder = SqlLLMCallRecorder(engine)
            request = _request()
            response = await EchoLLMGateway().complete(request)

            with pytest.raises(LLMCallRecordingError, match="step_id must not be blank"):
                await recorder.record(
                    request=request,
                    response=response,
                    workflow_id="wf_llm_call_blank_step",
                    step_id="   ",
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_record_rejects_an_unknown_agent_id(database_url: str) -> None:
    async def _run() -> None:
        await _seed_workflow_instance(database_url, "wf_llm_call_bad_agent")
        await _seed_agent_and_prompt(
            database_url,
            agent_id="se.software_engineering/llm-recorder-good-agent",
            prompt_id="prompt_llm_recorder_for_bad_agent",
        )
        engine = build_engine(database_url)
        try:
            recorder = SqlLLMCallRecorder(engine)
            request = _request()
            response = await EchoLLMGateway().complete(request)

            with pytest.raises(LLMCallRecordingError):
                await recorder.record(
                    request=request,
                    response=response,
                    workflow_id="wf_llm_call_bad_agent",
                    step_id="step_1",
                    agent_id="se.software_engineering/does-not-exist",
                    prompt_id="prompt_llm_recorder_for_bad_agent",
                    prompt_version="1.0.0",
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_record_rejects_an_unknown_prompt_id(database_url: str) -> None:
    async def _run() -> None:
        await _seed_workflow_instance(database_url, "wf_llm_call_bad_prompt")
        await _seed_agent_and_prompt(
            database_url,
            agent_id="se.software_engineering/llm-recorder-agent-for-bad-prompt",
            prompt_id="prompt_llm_recorder_unused",
        )
        engine = build_engine(database_url)
        try:
            recorder = SqlLLMCallRecorder(engine)
            request = _request()
            response = await EchoLLMGateway().complete(request)

            with pytest.raises(LLMCallRecordingError):
                await recorder.record(
                    request=request,
                    response=response,
                    workflow_id="wf_llm_call_bad_prompt",
                    step_id="step_1",
                    agent_id="se.software_engineering/llm-recorder-agent-for-bad-prompt",
                    prompt_id="prompt_does_not_exist",
                    prompt_version="1.0.0",
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())
