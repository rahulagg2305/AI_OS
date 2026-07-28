"""WorkflowAdvanceRunner (acquire → advance once → release) against a
real Postgres container (ADR-0015 — no mocking the database). Proves:
a successful run claims, advances, and releases; the lease is still
released when advance() genuinely fails after a successful claim; and
a concurrent claim attempt is still rejected through this composition,
without ever reaching advance().
"""

import asyncio
import os
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.schema import workflow_leases
from ai_os_kernel.workflow_engine.advance_runner import (
    WorkflowAdvanceRunner,
    WorkflowRunOutcome,
)
from ai_os_kernel.workflow_engine.definition_catalog import SqlWorkflowDefinitionCatalog
from ai_os_kernel.workflow_engine.errors import (
    WorkflowInvalidTransitionError,
    WorkflowLeaseUnavailableError,
)
from ai_os_kernel.workflow_engine.instance import WorkflowInstanceStatus
from ai_os_kernel.workflow_engine.lease import SqlWorkflowLeaseRepository, WorkflowLeaseService
from ai_os_kernel.workflow_engine.models import WorkflowDefinition
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from ai_os_kernel.workflow_engine.service import WorkflowInstanceService
from ai_os_kernel.workflow_engine.step_executor import NoOpStepExecutor
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

_DEFINITION_ID = "se.product_creation"
_DEFINITION_VERSION = "1.0.0"


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


def _minimal_definition(definition_id: str = _DEFINITION_ID) -> WorkflowDefinition:
    return WorkflowDefinition.model_validate(
        {
            "id": definition_id,
            "name": "Full Product Creation",
            "description": "Turn a structured specification into working software.",
            "version": _DEFINITION_VERSION,
            "inputs": {
                "type": "object",
                "properties": {"specPath": {"type": "string"}},
                "required": ["specPath"],
            },
            "outputs": {"type": "object"},
            "steps": [
                {
                    "id": "analyze_requirements",
                    "type": "agent",
                    "agentId": "se.software_engineering/analyst",
                }
            ],
            "failureHandling": {"onError": "escalate"},
        }
    )


def _two_step_definition(definition_id: str = _DEFINITION_ID) -> WorkflowDefinition:
    return WorkflowDefinition.model_validate(
        {
            "id": definition_id,
            "name": "Full Product Creation",
            "description": "Turn a structured specification into working software.",
            "version": _DEFINITION_VERSION,
            "inputs": {
                "type": "object",
                "properties": {"specPath": {"type": "string"}},
                "required": ["specPath"],
            },
            "outputs": {"type": "object"},
            "steps": [
                {"id": "step_a", "type": "agent", "agentId": "se.software_engineering/analyst"},
                {"id": "step_b", "type": "agent", "agentId": "se.software_engineering/analyst"},
            ],
            "failureHandling": {"onError": "escalate"},
        }
    )


async def _create_running_instance(database_url: str) -> str:
    engine = build_engine(database_url)
    try:
        repository = SqlWorkflowInstanceRepository(engine)
        created = await repository.create(
            definition_id=_DEFINITION_ID,
            definition_version=_DEFINITION_VERSION,
            inputs={"specPath": "specs/product.md"},
            principal_id="user-42",
        )
        await repository.transition_to_running(
            workflow_id=created.workflow_id, reason="worker picked it up"
        )
        return created.workflow_id
    finally:
        await engine.dispose()


async def _lease_exists(database_url: str, workflow_id: str) -> bool:
    engine = build_engine(database_url)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                sa.select(workflow_leases).where(workflow_leases.c.workflow_id == workflow_id)
            )
            return result.mappings().one_or_none() is not None
    finally:
        await engine.dispose()


def _make_runner(engine: Any) -> WorkflowAdvanceRunner:
    return WorkflowAdvanceRunner(
        WorkflowInstanceService(
            SqlWorkflowInstanceRepository(engine),
            NoOpStepExecutor(),
            SqlWorkflowDefinitionCatalog(engine),
        ),
        WorkflowLeaseService(SqlWorkflowLeaseRepository(engine)),
    )


def test_run_once_claims_advances_and_releases(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            workflow_id = await _create_running_instance(database_url)
            runner = _make_runner(engine)

            result = await runner.run_once(
                workflow_id=workflow_id,
                definition=_minimal_definition(),
                worker_id="worker-1",
                lease_duration_seconds=60,
            )

            assert result.current_step_id == "analyze_requirements"
            assert await _lease_exists(database_url, workflow_id) is False
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_release_still_happens_when_advance_fails(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            workflow_id = await _create_running_instance(database_url)
            runner = _make_runner(engine)
            # A structurally valid definition, but with a different id
            # than the one the instance was actually created from —
            # advance() resolves a next step just fine, then its
            # persistence write is rejected by the definition-mismatch
            # guard (WorkflowInvalidTransitionError), *after* the lease
            # was already acquired successfully.
            mismatched_definition = _minimal_definition(definition_id="se.some_other_workflow")

            with pytest.raises(WorkflowInvalidTransitionError):
                await runner.run_once(
                    workflow_id=workflow_id,
                    definition=mismatched_definition,
                    worker_id="worker-1",
                    lease_duration_seconds=60,
                )

            assert await _lease_exists(database_url, workflow_id) is False
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_concurrent_claim_is_rejected_and_advance_never_runs(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            workflow_id = await _create_running_instance(database_url)
            lease_repository = SqlWorkflowLeaseRepository(engine)
            runner = _make_runner(engine)

            # worker-1 already holds the lease directly (simulating a
            # worker mid-step, before this composition even existed).
            await lease_repository.acquire(
                workflow_id=workflow_id, worker_id="worker-1", lease_duration_seconds=60
            )

            with pytest.raises(WorkflowLeaseUnavailableError, match="already leased"):
                await runner.run_once(
                    workflow_id=workflow_id,
                    definition=_minimal_definition(),
                    worker_id="worker-2",
                    lease_duration_seconds=60,
                )

            # advance() was never reached: current_step_id is still None.
            instance_repository = SqlWorkflowInstanceRepository(engine)
            instance = await instance_repository.get_instance(workflow_id)
            assert instance is not None
            assert instance.current_step_id is None

            # worker-1's own lease is untouched by worker-2's rejected attempt.
            assert await _lease_exists(database_url, workflow_id) is True
            await lease_repository.release(workflow_id=workflow_id, worker_id="worker-1")
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_run_once_succeeds_all_the_way_to_workflow_completion(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            workflow_id = await _create_running_instance(database_url)
            runner = _make_runner(engine)
            definition = _minimal_definition()  # exactly one step

            after_first = await runner.run_once(
                workflow_id=workflow_id,
                definition=definition,
                worker_id="worker-1",
                lease_duration_seconds=60,
            )
            assert after_first.current_step_id == "analyze_requirements"

            after_completion = await runner.run_once(
                workflow_id=workflow_id,
                definition=definition,
                worker_id="worker-1",
                lease_duration_seconds=60,
            )
            assert after_completion.status == WorkflowInstanceStatus.COMPLETED
            assert await _lease_exists(database_url, workflow_id) is False
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_run_to_completion_reaches_completed_for_a_multi_step_workflow(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            workflow_id = await _create_running_instance(database_url)
            runner = _make_runner(engine)

            result = await runner.run_to_completion(
                workflow_id=workflow_id,
                definition=_two_step_definition(),
                worker_id="worker-1",
                lease_duration_seconds=60,
                max_iterations=10,
            )

            assert result.outcome is WorkflowRunOutcome.COMPLETED
            # step_a, step_b, then the completing call: three advance() calls.
            assert result.iterations == 3
            assert result.last_instance is not None
            assert result.last_instance.status == WorkflowInstanceStatus.COMPLETED
            assert result.error is None
            assert await _lease_exists(database_url, workflow_id) is False
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_run_to_completion_stops_at_the_iteration_bound_before_completing(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            workflow_id = await _create_running_instance(database_url)
            runner = _make_runner(engine)

            result = await runner.run_to_completion(
                workflow_id=workflow_id,
                definition=_two_step_definition(),
                worker_id="worker-1",
                lease_duration_seconds=60,
                max_iterations=1,
            )

            assert result.outcome is WorkflowRunOutcome.MAX_ITERATIONS_REACHED
            assert result.iterations == 1
            assert result.last_instance is not None
            assert result.last_instance.status != WorkflowInstanceStatus.COMPLETED
            # Each run_once already released its own lease internally —
            # hitting the bound leaves nothing held.
            assert await _lease_exists(database_url, workflow_id) is False
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_run_to_completion_reports_a_terminal_error_without_raising(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            workflow_id = await _create_running_instance(database_url)
            runner = _make_runner(engine)
            # A structurally valid definition with the wrong id — every
            # advance() call will fail the definition-mismatch guard,
            # after successfully acquiring the lease each time.
            mismatched_definition = _two_step_definition(definition_id="se.some_other_workflow")

            result = await runner.run_to_completion(
                workflow_id=workflow_id,
                definition=mismatched_definition,
                worker_id="worker-1",
                lease_duration_seconds=60,
                max_iterations=10,
            )

            assert result.outcome is WorkflowRunOutcome.FAILED
            assert result.iterations == 1
            assert isinstance(result.error, WorkflowInvalidTransitionError)
            assert await _lease_exists(database_url, workflow_id) is False
        finally:
            await engine.dispose()

    asyncio.run(_run())
