"""``SqlCostAnomalyDetector`` against a real Postgres container
(ADR-0015 — no mocking the database). Proves NFR-045's own literal
arithmetic ("fires ... when hourly spend exceeds 3x the trailing 7-day
hourly mean") over real, explicitly-timestamped seeded rows, not
fabricated numbers — ``P07-S03-M42-T02``.

Each test uses its own, widely separated ``now`` anchor (30 days apart)
so all three share one Postgres container/table without their own
trailing windows ever overlapping — real isolation, no truncation
needed between tests.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.evaluation_engine.cost_anomaly import SqlCostAnomalyDetector
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.evaluation_schema import llm_calls
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

_ANOMALY_NOW = datetime(2026, 1, 1, tzinfo=UTC)
_NORMAL_NOW = _ANOMALY_NOW - timedelta(days=30)
_COLD_START_NOW = _ANOMALY_NOW - timedelta(days=60)


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


async def _seed_workflow_instance(engine: AsyncEngine, workflow_id: str) -> None:
    definition_id = f"def_ca_{uuid.uuid4().hex}"
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                "INSERT INTO catalog.workflow_definitions "
                "(definition_id, pack_id, version, graph, inputs_schema, "
                " outputs_schema, declared_permissions, validated_at) "
                "VALUES (:definition_id, 'test-pack', '1.0.0', "
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


async def _seed_agent(engine: AsyncEngine, *, agent_id: str) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                "INSERT INTO catalog.agents "
                "(agent_id, pack_id, version, entrypoint, input_schema, output_schema, "
                " required_permissions, required_tools) "
                "VALUES (:agent_id, 'test-pack', '1.0.0', 'pack.agents:Agent', "
                " '{}'::jsonb, '{}'::jsonb, '[]'::jsonb, '[]'::jsonb) "
                "ON CONFLICT (agent_id) DO NOTHING"
            ),
            {"agent_id": agent_id},
        )
        await connection.execute(
            sa.text(
                "INSERT INTO catalog.prompts "
                "(prompt_id, pack_id, version, content, input_schema, content_hash) "
                "VALUES (:prompt_id, 'test-pack', '1.0.0', 'p', '{}'::jsonb, 'sha256:x') "
                "ON CONFLICT (prompt_id, version) DO NOTHING"
            ),
            {"prompt_id": f"prompt_{agent_id}"},
        )


async def _seed_llm_call(
    engine: AsyncEngine, *, workflow_id: str, agent_id: str, cost_usd: str, created_at: datetime
) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            sa.insert(llm_calls).values(
                call_id=f"call_{uuid.uuid4().hex}",
                workflow_id=workflow_id,
                step_id="step_1",
                agent_id=agent_id,
                prompt_id=f"prompt_{agent_id}",
                prompt_version="1.0.0",
                model_alias="fast-cheap",
                provider="anthropic",
                model_id="claude-opus-5",
                input_tokens=1,
                output_tokens=1,
                cache_read_tokens=0,
                cache_write_tokens=0,
                cost_usd=Decimal(cost_usd),
                latency_ms=100,
                stop_reason="end_turn",
                retries=0,
                fallback_used=False,
                degradations=[],
                created_at=created_at,
            )
        )


def test_a_real_spike_against_a_real_trailing_mean_is_genuinely_flagged(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            workflow_id = f"wf_ca_{uuid.uuid4().hex}"
            agent_id = f"agent_ca_{uuid.uuid4().hex}"
            await _seed_workflow_instance(engine, workflow_id)
            await _seed_agent(engine, agent_id=agent_id)

            # Trailing window: one real row totalling $168 over 168
            # real hours -> a real hourly mean of exactly $1.00.
            await _seed_llm_call(
                engine,
                workflow_id=workflow_id,
                agent_id=agent_id,
                cost_usd="168.000000",
                created_at=_ANOMALY_NOW - timedelta(hours=100),
            )
            # Current window: $10 in the last real hour -> 10x the
            # real mean, genuinely over the 3x threshold.
            await _seed_llm_call(
                engine,
                workflow_id=workflow_id,
                agent_id=agent_id,
                cost_usd="10.000000",
                created_at=_ANOMALY_NOW - timedelta(minutes=30),
            )

            detector = SqlCostAnomalyDetector(engine)
            result = await detector.check_once(now=_ANOMALY_NOW)

            assert result.trailing_mean_hourly_spend_usd == Decimal("1.000000")
            assert result.current_hour_spend_usd == Decimal("10.000000")
            assert result.is_anomalous is True
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_real_spend_within_the_threshold_is_genuinely_not_flagged(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            workflow_id = f"wf_ca_{uuid.uuid4().hex}"
            agent_id = f"agent_ca_{uuid.uuid4().hex}"
            await _seed_workflow_instance(engine, workflow_id)
            await _seed_agent(engine, agent_id=agent_id)

            # Trailing mean: $1.00/hour, same as above.
            await _seed_llm_call(
                engine,
                workflow_id=workflow_id,
                agent_id=agent_id,
                cost_usd="168.000000",
                created_at=_NORMAL_NOW - timedelta(hours=100),
            )
            # Current window: $2 — above the mean but genuinely at
            # (not over) 2x, comfortably under the real 3x threshold.
            await _seed_llm_call(
                engine,
                workflow_id=workflow_id,
                agent_id=agent_id,
                cost_usd="2.000000",
                created_at=_NORMAL_NOW - timedelta(minutes=30),
            )

            detector = SqlCostAnomalyDetector(engine)
            result = await detector.check_once(now=_NORMAL_NOW)

            assert result.trailing_mean_hourly_spend_usd == Decimal("1.000000")
            assert result.current_hour_spend_usd == Decimal("2.000000")
            assert result.is_anomalous is False
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_no_real_trailing_history_is_honestly_never_flagged(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            workflow_id = f"wf_ca_{uuid.uuid4().hex}"
            agent_id = f"agent_ca_{uuid.uuid4().hex}"
            await _seed_workflow_instance(engine, workflow_id)
            await _seed_agent(engine, agent_id=agent_id)

            # Only current-window spend — genuinely zero real trailing
            # history (a cold-started deployment). A ratio against a
            # zero baseline is undefined, not "infinitely anomalous."
            await _seed_llm_call(
                engine,
                workflow_id=workflow_id,
                agent_id=agent_id,
                cost_usd="500.000000",
                created_at=_COLD_START_NOW - timedelta(minutes=30),
            )

            detector = SqlCostAnomalyDetector(engine)
            result = await detector.check_once(now=_COLD_START_NOW)

            assert result.trailing_mean_hourly_spend_usd is None
            assert result.current_hour_spend_usd == Decimal("500.000000")
            assert result.is_anomalous is False
        finally:
            await engine.dispose()

    asyncio.run(_run())
