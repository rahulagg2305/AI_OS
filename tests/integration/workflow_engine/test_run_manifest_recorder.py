"""``SqlRunManifestRecorder``, end to end, against real Postgres
(ADR-0015 — no mocking the database). Proves the real, multi-table
join this component exists for: given a real, completed workflow run
whose steps reference real, catalog-registered agents/tools/packs/
prompts, and a real ``evaluation.llm_calls`` row, the recorded manifest
genuinely reflects that real, joined data — not fabricated, not a
literal.

The complementary, end-to-end proof — the real production wiring
(`WorkflowInstanceService`/`delivery_pipeline.py`) genuinely recording
a manifest at real completion — lives in
``tests/integration/workflow_engine/test_delivery_pipeline_git_push.py``,
whose own registry is a deterministic ``InMemoryAgentRegistry`` never
registered into the real catalog, so this file is the one place the
*non-``None``* catalog-join case is proven.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Generator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.persistence.catalog_schema import agents, packs, prompts, tools
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.evaluation_schema import llm_calls, run_manifests
from ai_os_kernel.persistence.schema import workflow_instances, workflow_steps
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from ai_os_kernel.workflow_engine.run_manifest_recorder import SqlRunManifestRecorder
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


async def _seed_workflow_definition(
    engine: AsyncEngine, *, definition_id: str, version: str
) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                "INSERT INTO catalog.workflow_definitions "
                "(definition_id, version, pack_id, graph, inputs_schema, "
                " outputs_schema, declared_permissions, validated_at) "
                "VALUES (:definition_id, :version, 'test-pack', '{}'::jsonb, "
                " '{}'::jsonb, '{}'::jsonb, '[]'::jsonb, now()) "
                "ON CONFLICT (definition_id, version) DO NOTHING"
            ),
            {"definition_id": definition_id, "version": version},
        )


async def _seed_catalog(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            sa.insert(packs).values(
                pack_id="test-pack",
                version="2.0.0",
                state="activated",
                manifest={},
                sdk_version="0.1.0",
                min_kernel_version="0.1.0",
            )
        )
        await connection.execute(
            sa.insert(agents).values(
                agent_id="test-pack/analyst",
                pack_id="test-pack",
                version="1.5.0",
                entrypoint="test_pack.agents:AnalystAgent",
                input_schema={},
                output_schema={},
                required_permissions=[],
                required_tools=[],
            )
        )
        await connection.execute(
            sa.insert(tools).values(
                tool_id="test-pack/formatter",
                pack_id="test-pack",
                version="1.2.0",
                entrypoint="test_pack.tools:FormatterTool",
                trust_tier="tier2_trusted",
                input_schema={},
                output_schema={},
                required_permissions=[],
            )
        )
        await connection.execute(
            sa.insert(prompts).values(
                prompt_id="analyst.analyze",
                version="0.1.0",
                pack_id="test-pack",
                content="analyze this",
                input_schema={},
                content_hash="sha256:test",
            )
        )


def _step_row(
    *,
    step_id: str,
    workflow_id: str,
    step_name: str,
    agent_id: str | None,
    tool_id: str | None,
    prompt_id: str | None,
    prompt_version: str | None,
    model_alias: str | None,
) -> dict[str, object]:
    return {
        "step_id": step_id,
        "workflow_id": workflow_id,
        "step_name": step_name,
        "step_type": "agent" if agent_id else "tool",
        "status": "completed",
        "attempt": 1,
        "agent_id": agent_id,
        "tool_id": tool_id,
        "prompt_id": prompt_id,
        "prompt_version": prompt_version,
        "model_alias": model_alias,
        "inputs": {},
        "outputs": {"content": "real output"},
        "error": None,
        "idempotency_key": f"idem_{step_id}",
        "usage": {},
        "started_at": sa.func.now(),
        "completed_at": sa.func.now(),
    }


def test_a_real_run_manifest_reflects_real_catalog_joined_data(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            await _seed_workflow_definition(
                engine, definition_id="test.run-manifest-workflow", version="1.0.0"
            )
            await _seed_catalog(engine)

            instance = await SqlWorkflowInstanceRepository(engine).create(
                definition_id="test.run-manifest-workflow",
                definition_version="1.0.0",
                inputs={},
                principal_id="test-principal",
            )
            workflow_id = instance.workflow_id

            async with engine.begin() as connection:
                await connection.execute(
                    sa.insert(workflow_steps).values(
                        _step_row(
                            step_id="stp_analyze",
                            workflow_id=workflow_id,
                            step_name="analyze",
                            agent_id="test-pack/analyst",
                            tool_id=None,
                            prompt_id="analyst.analyze",
                            prompt_version="0.1.0",
                            model_alias="coding-strong",
                        )
                    )
                )
                await connection.execute(
                    sa.insert(workflow_steps).values(
                        _step_row(
                            step_id="stp_format",
                            workflow_id=workflow_id,
                            step_name="format",
                            agent_id=None,
                            tool_id="test-pack/formatter",
                            prompt_id=None,
                            prompt_version=None,
                            model_alias=None,
                        )
                    )
                )
                # A real evaluation.llm_calls row for the analyze step --
                # the one real caller that would exist once the
                # separate, pre-existing stepId-threading gap
                # (run_manifest_recorder.py's own docstring) is closed.
                await connection.execute(
                    sa.insert(llm_calls).values(
                        call_id="call_analyze_1",
                        workflow_id=workflow_id,
                        step_id="analyze",
                        agent_id="test-pack/analyst",
                        prompt_id="analyst.analyze",
                        prompt_version="0.1.0",
                        model_alias="coding-strong",
                        provider="anthropic",
                        model_id="claude-opus-5",
                        input_tokens=10,
                        output_tokens=20,
                        cache_read_tokens=0,
                        cache_write_tokens=0,
                        cost_usd=0,
                        latency_ms=100,
                        stop_reason="end_turn",
                        retries=0,
                        fallback_used=False,
                        degradations=[],
                    )
                )

            recorder = SqlRunManifestRecorder(engine)
            run_manifest_id = await recorder.record(
                workflow_id=workflow_id,
                definition_id="test.run-manifest-workflow",
                definition_version="1.0.0",
            )

            async with engine.connect() as connection:
                manifest_row = (
                    (
                        await connection.execute(
                            sa.select(run_manifests).where(
                                run_manifests.c.run_manifest_id == run_manifest_id
                            )
                        )
                    )
                    .mappings()
                    .one()
                )
                instance_row = (
                    (
                        await connection.execute(
                            sa.select(workflow_instances.c.run_manifest_id).where(
                                workflow_instances.c.workflow_id == workflow_id
                            )
                        )
                    )
                    .mappings()
                    .one()
                )

            assert manifest_row["workflow_id"] == workflow_id
            assert manifest_row["manifest_hash"].startswith("sha256:")
            assert instance_row["run_manifest_id"] == run_manifest_id

            manifest = manifest_row["manifest"]
            assert manifest["workflow_definition_id"] == "test.run-manifest-workflow"
            assert manifest["workflow_definition_version"] == "1.0.0"
            assert manifest["kernel_version"]

            steps_by_id = {entry["step_id"]: entry for entry in manifest["steps"]}
            assert set(steps_by_id) == {"analyze", "format"}

            analyze_entry = steps_by_id["analyze"]
            assert analyze_entry["agent_id"] == "test-pack/analyst"
            assert analyze_entry["agent_version"] == "1.5.0"
            assert analyze_entry["pack_id"] == "test-pack"
            assert analyze_entry["pack_version"] == "2.0.0"
            assert analyze_entry["prompt_id"] == "analyst.analyze"
            assert analyze_entry["prompt_version"] == "0.1.0"
            assert analyze_entry["model_alias"] == "coding-strong"
            assert analyze_entry["resolved_provider"] == "anthropic"
            assert analyze_entry["resolved_model_id"] == "claude-opus-5"

            format_entry = steps_by_id["format"]
            assert format_entry["tool_id"] == "test-pack/formatter"
            assert format_entry["tool_version"] == "1.2.0"
            assert format_entry["pack_id"] == "test-pack"
            assert format_entry["pack_version"] == "2.0.0"
            assert format_entry["agent_id"] is None
            # No real llm_calls row was seeded for this step -- honestly
            # None, not fabricated.
            assert format_entry["resolved_provider"] is None
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_the_latest_attempt_wins_when_a_step_genuinely_retried(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            await _seed_workflow_definition(
                engine, definition_id="test.run-manifest-retry-workflow", version="1.0.0"
            )
            instance = await SqlWorkflowInstanceRepository(engine).create(
                definition_id="test.run-manifest-retry-workflow",
                definition_version="1.0.0",
                inputs={},
                principal_id="test-principal",
            )
            workflow_id = instance.workflow_id

            async with engine.begin() as connection:
                await connection.execute(
                    sa.insert(workflow_steps).values(
                        {
                            **_step_row(
                                step_id="stp_build_1",
                                workflow_id=workflow_id,
                                step_name="build",
                                agent_id="test-pack/analyst",
                                tool_id=None,
                                prompt_id=None,
                                prompt_version=None,
                                model_alias="coding-balanced",
                            ),
                            "attempt": 1,
                            "status": "failed",
                        }
                    )
                )
                await connection.execute(
                    sa.insert(workflow_steps).values(
                        {
                            **_step_row(
                                step_id="stp_build_2",
                                workflow_id=workflow_id,
                                step_name="build",
                                agent_id="test-pack/analyst",
                                tool_id=None,
                                prompt_id=None,
                                prompt_version=None,
                                model_alias="coding-strong",
                            ),
                            "attempt": 2,
                        }
                    )
                )

            recorder = SqlRunManifestRecorder(engine)
            run_manifest_id = await recorder.record(
                workflow_id=workflow_id,
                definition_id="test.run-manifest-retry-workflow",
                definition_version="1.0.0",
            )

            async with engine.connect() as connection:
                manifest_row = (
                    (
                        await connection.execute(
                            sa.select(run_manifests.c.manifest).where(
                                run_manifests.c.run_manifest_id == run_manifest_id
                            )
                        )
                    )
                    .mappings()
                    .one()
                )

            steps = manifest_row["manifest"]["steps"]
            assert len(steps) == 1
            # The real, latest attempt's own declared configuration wins
            # -- not the failed first attempt's.
            assert steps[0]["model_alias"] == "coding-strong"
        finally:
            await engine.dispose()

    asyncio.run(_run())
