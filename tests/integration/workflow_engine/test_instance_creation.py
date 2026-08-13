"""Workflow instance creation against a real Postgres container
(ADR-0015 — no mocking the database). Proves the event-log-plus-snapshot
pattern (ADR-0011): both rows land in one transaction, and a failure in
the second write leaves no trace of the first.
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
from ai_os_kernel.persistence.schema import workflow_instances
from ai_os_kernel.workflow_engine.definition_catalog import SqlWorkflowDefinitionCatalog
from ai_os_kernel.workflow_engine.instance import WorkflowInstanceStatus
from ai_os_kernel.workflow_engine.models import WorkflowDefinition
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from ai_os_kernel.workflow_engine.service import WorkflowInstanceService
from ai_os_kernel.workflow_engine.step_executor import NoOpStepExecutor
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


async def _fetch_instance(database_url: str, workflow_id: str) -> dict[str, Any] | None:
    engine = build_engine(database_url)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                sa.select(workflow_instances).where(workflow_instances.c.workflow_id == workflow_id)
            )
            row = result.mappings().one_or_none()
            return dict(row) if row is not None else None
    finally:
        await engine.dispose()


async def _fetch_events(database_url: str, workflow_id: str) -> list[dict[str, Any]]:
    engine = build_engine(database_url)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                sa.text(
                    "SELECT event_id, seq, event_type, schema_version, payload "
                    "FROM workflow.workflow_events WHERE workflow_id = :workflow_id "
                    "ORDER BY seq"
                ),
                {"workflow_id": workflow_id},
            )
            return [dict(row) for row in result.mappings().all()]
    finally:
        await engine.dispose()


def test_create_writes_the_instance_and_its_first_event(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            repository = SqlWorkflowInstanceRepository(engine)
            instance = await repository.create(
                definition_id="se.product_creation",
                definition_version="1.0.0",
                inputs={"specPath": "specs/product.md"},
                principal_id="user-42",
            )

            assert instance.status == WorkflowInstanceStatus.CREATED
            assert instance.last_event_seq == 1
            assert instance.inputs == {"specPath": "specs/product.md"}

            stored_instance = await _fetch_instance(database_url, instance.workflow_id)
            assert stored_instance is not None
            assert stored_instance["status"] == "created"
            assert stored_instance["last_event_seq"] == 1

            events = await _fetch_events(database_url, instance.workflow_id)
            assert len(events) == 1
            assert events[0]["seq"] == 1
            assert events[0]["event_type"] == "workflow.started"
            assert events[0]["payload"]["definitionId"] == "se.product_creation"
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_service_creates_a_real_instance_end_to_end(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            service = WorkflowInstanceService(
                SqlWorkflowInstanceRepository(engine),
                NoOpStepExecutor(),
                SqlWorkflowDefinitionCatalog(engine),
            )
            instance = await service.create_instance(
                definition=_minimal_definition(),
                inputs={"specPath": "specs/other.md"},
                principal_id="user-99",
                pack_id="se.software_engineering",
            )

            events = await _fetch_events(database_url, instance.workflow_id)
            assert len(events) == 1
            assert events[0]["event_type"] == "workflow.started"
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_transaction_rolls_back_both_writes_if_the_second_insert_fails(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            with pytest.raises(sa.exc.IntegrityError):
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.insert(workflow_instances).values(
                            workflow_id="wf_atomicity_check",
                            definition_id="se.product_creation",
                            definition_version="1.0.0",
                            status="created",
                            inputs={},
                            principal_id="user-42",
                            last_event_seq=1,
                        )
                    )
                    # occurred_at is NOT NULL with no server default
                    # (repository.py's deliberate choice) — omitting it
                    # forces this second statement to fail inside the
                    # same transaction as the first, valid insert.
                    await connection.execute(
                        sa.text(
                            "INSERT INTO workflow.workflow_events "
                            "(event_id, workflow_id, seq, event_type, schema_version, payload) "
                            "VALUES ('evt_atomicity_check', 'wf_atomicity_check', 1, "
                            " 'workflow.started', 1, '{}'::jsonb)"
                        )
                    )

            stored_instance = await _fetch_instance(database_url, "wf_atomicity_check")
            assert stored_instance is None
        finally:
            await engine.dispose()

    asyncio.run(_run())


def _minimal_definition() -> WorkflowDefinition:
    return WorkflowDefinition.model_validate(
        {
            "id": "se.product_creation",
            "name": "Full Product Creation",
            "description": "Turn a structured specification into working software.",
            "version": "1.0.0",
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
            "failureHandling": {"onError": "halt"},
        }
    )
