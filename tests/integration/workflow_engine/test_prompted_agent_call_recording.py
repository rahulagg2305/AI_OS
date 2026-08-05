"""Real proof for the ``AgentStepExecutor``/``stepId`` fix
(``P04-S01-M12-T09``): a genuine agent invocation, driven through the
real, unmodified production composition function
(:func:`~ai_os_kernel.bootstrap._build_workflow_trigger`), now produces
a real, populated ``evaluation.llm_calls`` row — where before this fix
it would have been silently absent, since
:class:`~ai_os_kernel.workflow_engine.step_executor.AgentStepExecutor`
never supplied ``stepId``/``agentId``/``workflowId`` for
:meth:`~ai_os_kernel.prompted_completion.PromptedCompletionService.
complete_from_prompt`'s own call-recording guard to fire.

Only the agent's own LLM Gateway is swapped for
:class:`~ai_os_kernel.llm_gateway.gateway.EchoLLMGateway` (no live
Anthropic credential needed, ADR-0015's own "real database, no live
network for non-live tests" convention) — everything else is the real
production path: the real ``_build_workflow_trigger`` composition, a
real ``SqlLLMCallRecorder``/``SqlPromptCatalog``, and the real
:func:`~ai_os_kernel.bootstrap._seed_prompted_agent_catalog_rows`
seeding function this same fix adds, proving the foreign-key gap it
closes (``catalog.agents``/``catalog.prompts`` rows for the demo
composition) is real too, not merely asserted.

Also proves this closes the Run Manifest Recorder's own disclosed gap
(``P04-S01-M12-T05``) for this one composition: ``resolved_provider``/
``resolved_model_id`` on the recorded manifest's step entry are now
genuinely populated (``"echo"``/``"echo-1"``), not honestly ``None``.
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

from ai_os_kernel.bootstrap import (
    _DEMO_WORKFLOW_PROMPT_ID,
    _DEMO_WORKFLOW_PROMPT_VERSION,
    _DEMO_WORKFLOW_STEP_ID,
    _PROMPTED_AGENT_ID,
    _build_workflow_trigger,
    _seed_prompted_agent_catalog_rows,
)
from ai_os_kernel.context_manager.manager import DefaultContextManager
from ai_os_kernel.context_manager.resolvers import WorkflowStateResolver
from ai_os_kernel.llm_gateway.call_recorder import SqlLLMCallRecorder
from ai_os_kernel.llm_gateway.gateway import EchoLLMGateway
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.evaluation_schema import llm_calls, run_manifests
from ai_os_kernel.persistence.schema import workflow_instances
from ai_os_kernel.prompt_engine.catalog import SqlPromptCatalog
from ai_os_kernel.prompted_completion import PromptedCompletionService
from ai_os_kernel.workflow_engine.advance_runner import WorkflowRunOutcome
from ai_os_kernel.workflow_engine.prompted_agent import PromptedAgent
from ai_os_kernel.workflow_engine.registry import InMemoryAgentRegistry
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
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


def _real_call_recording_agent_registry(engine: AsyncEngine) -> InMemoryAgentRegistry:
    # The one real difference from bootstrap._build_prompted_agent_registry:
    # EchoLLMGateway instead of a live AnthropicAdapter. SqlPromptCatalog
    # and SqlLLMCallRecorder are both real, against this test's own real
    # Postgres -- exactly what the production composition wires.
    service = PromptedCompletionService(
        prompt_engine=SqlPromptCatalog(engine),
        llm_gateway=EchoLLMGateway(),
        call_recorder=SqlLLMCallRecorder(engine),
    )
    agent = PromptedAgent(service=service, max_output_tokens=1024)
    return InMemoryAgentRegistry({_PROMPTED_AGENT_ID: agent})


def _context_manager(engine: AsyncEngine) -> DefaultContextManager:
    return DefaultContextManager(
        resolvers=[WorkflowStateResolver(SqlWorkflowInstanceRepository(engine))]
    )


def test_a_real_agent_invocation_now_populates_evaluation_llm_calls(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            await _seed_prompted_agent_catalog_rows(engine)
            trigger = _build_workflow_trigger(
                engine, _real_call_recording_agent_registry(engine), _context_manager(engine)
            )

            result = await trigger({}, "test-principal")

            assert result.outcome is WorkflowRunOutcome.COMPLETED
            assert result.last_instance is not None
            workflow_id = result.workflow_id

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

            # Before this fix, AgentStepExecutor never supplied stepId/
            # workflowId, so complete_from_prompt's own call-recording
            # guard never fired and this row would not exist at all.
            assert call_row["step_id"] == _DEMO_WORKFLOW_STEP_ID
            assert call_row["agent_id"] == _PROMPTED_AGENT_ID
            assert call_row["prompt_id"] == _DEMO_WORKFLOW_PROMPT_ID
            assert call_row["prompt_version"] == _DEMO_WORKFLOW_PROMPT_VERSION
            assert call_row["provider"] == "echo"
            assert call_row["model_id"] == "echo-1"
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_the_run_manifest_recorders_own_disclosed_gap_now_closes_for_this_composition(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            await _seed_prompted_agent_catalog_rows(engine)
            trigger = _build_workflow_trigger(
                engine, _real_call_recording_agent_registry(engine), _context_manager(engine)
            )

            result = await trigger({}, "test-principal")

            assert result.outcome is WorkflowRunOutcome.COMPLETED
            workflow_id = result.workflow_id

            async with engine.connect() as connection:
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
                manifest_row = (
                    (
                        await connection.execute(
                            sa.select(run_manifests.c.manifest).where(
                                run_manifests.c.run_manifest_id == instance_row["run_manifest_id"]
                            )
                        )
                    )
                    .mappings()
                    .one()
                )

            steps_by_id = {entry["step_id"]: entry for entry in manifest_row["manifest"]["steps"]}
            step_entry = steps_by_id[_DEMO_WORKFLOW_STEP_ID]
            # Previously disclosed as honestly None for every real run
            # (run_manifest_recorder.py's own module docstring, gap 2) --
            # now genuinely populated for this composition.
            assert step_entry["resolved_provider"] == "echo"
            assert step_entry["resolved_model_id"] == "echo-1"
        finally:
            await engine.dispose()

    asyncio.run(_run())
