"""``SqlCostAndQualityViews`` against a real Postgres container
(ADR-0015 — no mocking the database). Proves the real, general
aggregation this step adds (`P06-S03-M39-T03`): a cost breakdown by
model/workflow/agent/pack that genuinely reconciles with
``evaluation.llm_calls`` (FR-095's own acceptance criterion), and a
real gate-failure frequency summary (FR-094) — over real, seeded rows,
not fabricated numbers.
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

from ai_os_kernel.evaluation_engine.cost_and_quality_views import SqlCostAndQualityViews
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.evaluation_schema import gate_results, llm_calls
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


async def _seed_workflow_instance(
    engine: AsyncEngine, workflow_id: str, definition_id: str
) -> None:
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


async def _seed_agent(engine: AsyncEngine, *, agent_id: str, pack_id: str) -> None:
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
            {"agent_id": agent_id, "pack_id": pack_id},
        )
        await connection.execute(
            sa.text(
                "INSERT INTO catalog.prompts "
                "(prompt_id, pack_id, version, content, input_schema, content_hash) "
                "VALUES (:prompt_id, :pack_id, '1.0.0', 'p', '{}'::jsonb, 'sha256:x') "
                "ON CONFLICT (prompt_id, version) DO NOTHING"
            ),
            {"prompt_id": f"prompt_{agent_id.split('/')[-1]}", "pack_id": pack_id},
        )


def _llm_call_row(
    *,
    workflow_id: str,
    agent_id: str,
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: str,
) -> dict[str, object]:
    return {
        "call_id": f"call_{uuid.uuid4().hex}",
        "workflow_id": workflow_id,
        "step_id": "step_1",
        "agent_id": agent_id,
        "prompt_id": f"prompt_{agent_id.split('/')[-1]}",
        "prompt_version": "1.0.0",
        "model_alias": "fast-cheap",
        "provider": "anthropic",
        "model_id": model_id,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "cost_usd": Decimal(cost_usd),
        "latency_ms": 100,
        "stop_reason": "end_turn",
        "retries": 0,
        "fallback_used": False,
        "degradations": [],
    }


def _gate_result_row(*, workflow_id: str, gate_id: str, status: str) -> dict[str, object]:
    return {
        "result_id": f"gr_{uuid.uuid4().hex}",
        "workflow_id": workflow_id,
        "step_id": "step_1",
        "gate_id": gate_id,
        "gate_version": "1.0.0",
        "status": status,
        "severity": "blocking",
        "metrics": {},
        "messages": [],
        "duration_ms": 10,
    }


def test_a_real_cost_and_quality_report_reconciles_with_seeded_rows(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            workflow_a = f"wf_cq_{uuid.uuid4().hex}"
            workflow_b = f"wf_cq_{uuid.uuid4().hex}"
            await _seed_workflow_instance(engine, workflow_a, f"def_cq_a_{uuid.uuid4().hex}")
            await _seed_workflow_instance(engine, workflow_b, f"def_cq_b_{uuid.uuid4().hex}")
            await _seed_agent(engine, agent_id="pack-alpha/writer", pack_id="pack-alpha")
            await _seed_agent(engine, agent_id="pack-beta/writer", pack_id="pack-beta")

            async with engine.begin() as connection:
                await connection.execute(
                    sa.insert(llm_calls),
                    [
                        _llm_call_row(
                            workflow_id=workflow_a,
                            agent_id="pack-alpha/writer",
                            model_id="claude-opus-5",
                            input_tokens=100,
                            output_tokens=50,
                            cost_usd="1.500000",
                        ),
                        _llm_call_row(
                            workflow_id=workflow_a,
                            agent_id="pack-alpha/writer",
                            model_id="claude-opus-5",
                            input_tokens=200,
                            output_tokens=100,
                            cost_usd="2.500000",
                        ),
                        _llm_call_row(
                            workflow_id=workflow_b,
                            agent_id="pack-beta/writer",
                            model_id="claude-sonnet-5",
                            input_tokens=50,
                            output_tokens=25,
                            cost_usd="0.500000",
                        ),
                    ],
                )
                await connection.execute(
                    sa.insert(gate_results),
                    [
                        _gate_result_row(
                            workflow_id=workflow_a,
                            gate_id="quality-gate-lint-clean",
                            status="failed",
                        ),
                        _gate_result_row(
                            workflow_id=workflow_a,
                            gate_id="quality-gate-lint-clean",
                            status="failed",
                        ),
                        _gate_result_row(
                            workflow_id=workflow_b,
                            gate_id="quality-gate-lint-clean",
                            status="passed",
                        ),
                        _gate_result_row(
                            workflow_id=workflow_b,
                            gate_id="quality-gate-test-clean",
                            status="failed",
                        ),
                    ],
                )

            views = SqlCostAndQualityViews(engine)
            report = await views.get_report()

            by_model = {entry.dimension_value: entry for entry in report.by_model}
            assert by_model["claude-opus-5"].call_count == 2
            assert by_model["claude-opus-5"].total_input_tokens == 300
            assert by_model["claude-opus-5"].total_output_tokens == 150
            assert by_model["claude-opus-5"].total_cost_usd == Decimal("4.000000")
            assert by_model["claude-sonnet-5"].call_count == 1
            assert by_model["claude-sonnet-5"].total_cost_usd == Decimal("0.500000")

            by_workflow = {entry.dimension_value: entry for entry in report.by_workflow}
            assert by_workflow[workflow_a].call_count == 2
            assert by_workflow[workflow_b].call_count == 1

            by_agent = {entry.dimension_value: entry for entry in report.by_agent}
            assert by_agent["pack-alpha/writer"].total_cost_usd == Decimal("4.000000")
            assert by_agent["pack-beta/writer"].total_cost_usd == Decimal("0.500000")

            by_pack = {entry.dimension_value: entry for entry in report.by_pack}
            assert by_pack["pack-alpha"].call_count == 2
            assert by_pack["pack-beta"].call_count == 1

            failures = {
                (entry.gate_id, entry.status): entry.count for entry in report.gate_failures
            }
            assert failures[("quality-gate-lint-clean", "failed")] == 2
            assert failures[("quality-gate-lint-clean", "passed")] == 1
            assert failures[("quality-gate-test-clean", "failed")] == 1
            # Most frequent failure first.
            assert report.gate_failures[0].gate_id == "quality-gate-lint-clean"
            assert report.gate_failures[0].status == "failed"
            assert report.gate_failures[0].count == 2
        finally:
            await engine.dispose()

    asyncio.run(_run())
