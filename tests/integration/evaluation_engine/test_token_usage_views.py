"""``SqlTokenUsageViews`` against a real Postgres container (ADR-0015 —
no mocking the database). Proves api_architecture.md §6.4's own
``GET /api/v1/usage/tokens``, "Token usage incl. cache split".

**The cache split is the point, and it is why this file exists at all.**
``evaluation.llm_calls`` has recorded ``cache_read_tokens`` and
``cache_write_tokens`` on every real call since the table existed, and
nothing anywhere read them. The pre-existing
``test_cost_and_quality_views.py`` seeds both as literal ``0`` in every
row — accurately, because the report it tests has no cache columns to
assert on. Here they are seeded to genuinely different non-zero values
per model, so a query that ignored them, summed the wrong column, or
transposed read and write would fail rather than pass by coincidence.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Generator
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.evaluation_engine.token_usage_views import SqlTokenUsageViews, TokenUsageEntry
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.evaluation_schema import llm_calls
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

_PACK_ID = "se.software_engineering"
_AGENT_ID = "se.software_engineering/analyst"
_MODEL_A = "claude-model-a"
_MODEL_B = "claude-model-b"


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


async def _seed_workflow_instance(engine: AsyncEngine, *, workflow_id: str) -> None:
    definition_id = "se.token_usage_test"
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                "INSERT INTO catalog.workflow_definitions "
                "(definition_id, pack_id, version, graph, inputs_schema, "
                " outputs_schema, declared_permissions, validated_at) "
                "VALUES (:definition_id, 'se.software_engineering', '1.0.0', "
                " '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, '[]'::jsonb, now()) "
                "ON CONFLICT (definition_id, version) DO NOTHING"
            ),
            {"definition_id": definition_id},
        )
        await connection.execute(
            sa.text(
                "INSERT INTO workflow.workflow_instances "
                "(workflow_id, definition_id, definition_version, status, "
                " inputs, principal_id, last_event_seq) "
                "VALUES (:workflow_id, :definition_id, '1.0.0', 'created', "
                " '{}'::jsonb, 'user_test', 0)"
            ),
            {"workflow_id": workflow_id, "definition_id": definition_id},
        )


async def _seed_agent(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                "INSERT INTO catalog.agents "
                "(agent_id, pack_id, version, entrypoint, input_schema, output_schema, "
                " required_permissions, required_tools) "
                "VALUES (:agent_id, :pack_id, '1.0.0', 'pack.agents:Agent', "
                " '{}'::jsonb, '{}'::jsonb, '[]'::jsonb, '[]'::jsonb) "
                "ON CONFLICT (agent_id) DO NOTHING"
            ),
            {"agent_id": _AGENT_ID, "pack_id": _PACK_ID},
        )
        await connection.execute(
            sa.text(
                "INSERT INTO catalog.prompts "
                "(prompt_id, pack_id, version, content, input_schema, content_hash) "
                "VALUES ('prompt_analyst', :pack_id, '1.0.0', 'p', '{}'::jsonb, 'sha256:x') "
                "ON CONFLICT (prompt_id, version) DO NOTHING"
            ),
            {"pack_id": _PACK_ID},
        )


def _call(
    *,
    workflow_id: str,
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
    cache_write_tokens: int,
) -> dict[str, object]:
    return {
        "call_id": f"call_{uuid.uuid4().hex}",
        "workflow_id": workflow_id,
        "step_id": "step_1",
        "agent_id": _AGENT_ID,
        "prompt_id": "prompt_analyst",
        "prompt_version": "1.0.0",
        "model_alias": "fast-cheap",
        "provider": "anthropic",
        "model_id": model_id,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_tokens": cache_read_tokens,
        "cache_write_tokens": cache_write_tokens,
        "cost_usd": Decimal("0.010000"),
        "latency_ms": 100,
        "stop_reason": "end_turn",
        "retries": 0,
        "fallback_used": False,
        "degradations": [],
    }


def _by(entries: list[TokenUsageEntry], value: str) -> TokenUsageEntry:
    match = [e for e in entries if e.dimension_value == value]
    assert len(match) == 1, f"expected exactly one entry for {value!r}, got {len(match)}"
    return match[0]


def test_the_report_reconciles_with_seeded_rows_including_the_cache_split(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            workflow_id = f"wf_{uuid.uuid4().hex}"
            await _seed_workflow_instance(engine, workflow_id=workflow_id)
            await _seed_agent(engine)

            # Deliberately distinct, non-round, non-equal values so that
            # summing the wrong column, or transposing read and write,
            # cannot coincidentally produce the expected number.
            rows = [
                _call(
                    workflow_id=workflow_id,
                    model_id=_MODEL_A,
                    input_tokens=100,
                    output_tokens=10,
                    cache_read_tokens=700,
                    cache_write_tokens=30,
                ),
                _call(
                    workflow_id=workflow_id,
                    model_id=_MODEL_A,
                    input_tokens=200,
                    output_tokens=20,
                    cache_read_tokens=1300,
                    cache_write_tokens=5,
                ),
                _call(
                    workflow_id=workflow_id,
                    model_id=_MODEL_B,
                    input_tokens=50,
                    output_tokens=1,
                    cache_read_tokens=0,
                    cache_write_tokens=900,
                ),
            ]
            async with engine.begin() as connection:
                await connection.execute(sa.insert(llm_calls), rows)

            report = await SqlTokenUsageViews(engine).get_token_usage()

            model_a = _by(report.by_model, _MODEL_A)
            assert model_a.call_count == 2
            assert model_a.total_input_tokens == 300
            assert model_a.total_output_tokens == 30
            assert model_a.total_cache_read_tokens == 2000
            assert model_a.total_cache_write_tokens == 35

            # A model that only ever wrote cache and never read it — the
            # asymmetry proves the two columns are not conflated.
            model_b = _by(report.by_model, _MODEL_B)
            assert model_b.total_cache_read_tokens == 0
            assert model_b.total_cache_write_tokens == 900

            # Every dimension aggregates the same three calls.
            workflow = _by(report.by_workflow, workflow_id)
            assert workflow.call_count == 3
            assert workflow.total_cache_read_tokens == 2000
            assert workflow.total_cache_write_tokens == 935

            agent = _by(report.by_agent, _AGENT_ID)
            assert agent.call_count == 3
            assert agent.total_cache_read_tokens == 2000

            # `pack` comes from the real catalog.agents FK join, never a
            # string split on agent_id.
            pack = _by(report.by_pack, _PACK_ID)
            assert pack.call_count == 3
            assert pack.total_cache_write_tokens == 935
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_the_totals_reconcile_across_every_dimension(database_url: str) -> None:
    """FR-095's own acceptance shape, applied to tokens: the same calls
    summed along different axes must agree. A per-dimension query that
    double-counted through the pack join would break this."""

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            report = await SqlTokenUsageViews(engine).get_token_usage()

            def total(entries: list[TokenUsageEntry]) -> tuple[int, int, int]:
                return (
                    sum(e.call_count for e in entries),
                    sum(e.total_cache_read_tokens for e in entries),
                    sum(e.total_cache_write_tokens for e in entries),
                )

            assert total(report.by_model) == total(report.by_workflow)
            assert total(report.by_model) == total(report.by_agent)
            assert total(report.by_model) == total(report.by_pack)
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_an_empty_database_returns_a_real_empty_report(database_url: str) -> None:
    """An honest empty result, never a null or a crash — the same
    "existing-but-unrun is a valid 200" shape the experiment comparison
    read already establishes."""

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(sa.delete(llm_calls))

            report = await SqlTokenUsageViews(engine).get_token_usage()

            assert report.by_model == []
            assert report.by_workflow == []
            assert report.by_agent == []
            assert report.by_pack == []
        finally:
            await engine.dispose()

    asyncio.run(_run())
