"""The created -> running state transition against a real Postgres
container (ADR-0015 — no mocking the database). Proves: the happy path
appends a consistent state.transitioned event; an invalid transition is
rejected without side effects; and a failure in the event insert rolls
back a snapshot update that had already "succeeded" earlier in the same
transaction (ADR-0011's one-transaction guarantee, exercised from the
other direction than the instance-creation test).
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
from ai_os_kernel.workflow_engine.errors import (
    WorkflowInstanceCreationError,
    WorkflowInvalidTransitionError,
)
from ai_os_kernel.workflow_engine.instance import WorkflowInstanceStatus
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
                    "SELECT seq, event_type, payload FROM workflow.workflow_events "
                    "WHERE workflow_id = :workflow_id ORDER BY seq"
                ),
                {"workflow_id": workflow_id},
            )
            return [dict(row) for row in result.mappings().all()]
    finally:
        await engine.dispose()


def test_transition_to_running_succeeds_and_appends_the_event(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            repository = SqlWorkflowInstanceRepository(engine)
            created = await repository.create(
                definition_id="se.product_creation",
                definition_version="1.0.0",
                inputs={"specPath": "specs/product.md"},
                principal_id="user-42",
            )

            transitioned = await repository.transition_to_running(
                workflow_id=created.workflow_id, reason="worker picked it up"
            )

            assert transitioned.status == WorkflowInstanceStatus.RUNNING
            assert transitioned.last_event_seq == 2

            stored = await _fetch_instance(database_url, created.workflow_id)
            assert stored is not None
            assert stored["status"] == "running"
            assert stored["last_event_seq"] == 2

            events = await _fetch_events(database_url, created.workflow_id)
            assert [e["event_type"] for e in events] == ["workflow.started", "state.transitioned"]
            assert events[1]["seq"] == 2
            assert events[1]["payload"]["previousStatus"] == "created"
            assert events[1]["payload"]["newStatus"] == "running"
            assert events[1]["payload"]["reason"] == "worker picked it up"
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_transition_is_rejected_when_instance_is_not_in_created_status(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            repository = SqlWorkflowInstanceRepository(engine)
            created = await repository.create(
                definition_id="se.product_creation",
                definition_version="1.0.0",
                inputs={"specPath": "specs/product.md"},
                principal_id="user-42",
            )
            await repository.transition_to_running(
                workflow_id=created.workflow_id, reason="first transition"
            )

            with pytest.raises(WorkflowInvalidTransitionError, match="running"):
                await repository.transition_to_running(
                    workflow_id=created.workflow_id, reason="second transition"
                )

            # Rejected without side effects: still exactly two events.
            events = await _fetch_events(database_url, created.workflow_id)
            assert len(events) == 2
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_transition_is_rejected_when_instance_does_not_exist(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            repository = SqlWorkflowInstanceRepository(engine)

            with pytest.raises(WorkflowInvalidTransitionError, match="does not exist"):
                await repository.transition_to_running(
                    workflow_id="wf_does_not_exist", reason="irrelevant"
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_failed_event_append_rolls_back_the_snapshot_update(database_url: str) -> None:
    """The guarded UPDATE and the event INSERT are one transaction: if
    the second statement fails, the first's effect must not persist,
    even though it "succeeded" earlier in the same transaction."""

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            repository = SqlWorkflowInstanceRepository(engine)
            created = await repository.create(
                definition_id="se.product_creation",
                definition_version="1.0.0",
                inputs={"specPath": "specs/product.md"},
                principal_id="user-42",
            )

            # Pre-insert a seq=2 event for this workflow so the
            # repository's own seq=2 event insert collides with the
            # UNIQUE (workflow_id, seq) constraint — forcing the second
            # statement in transition_to_running's transaction to fail
            # after its guarded UPDATE already matched a row.
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO workflow.workflow_events "
                        "(event_id, workflow_id, seq, event_type, schema_version, "
                        " payload, occurred_at) "
                        "VALUES ('evt_preexisting', :workflow_id, 2, 'manual.duplicate', 1, "
                        " '{}'::jsonb, now())"
                    ),
                    {"workflow_id": created.workflow_id},
                )

            with pytest.raises(WorkflowInstanceCreationError):
                await repository.transition_to_running(
                    workflow_id=created.workflow_id, reason="will collide"
                )

            stored = await _fetch_instance(database_url, created.workflow_id)
            assert stored is not None
            assert stored["status"] == "created"
            assert stored["last_event_seq"] == 1
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_cancel_from_running_succeeds_and_appends_the_event(database_url: str) -> None:
    """Backs ``POST /api/v1/workflows/{id}/cancel`` (added 2026-08-10,
    `P06-S01-M36-T04`) — workflow_engine.md §7's own ``cancelled``
    state, genuinely reached for the first time."""

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            repository = SqlWorkflowInstanceRepository(engine)
            created = await repository.create(
                definition_id="se.product_creation",
                definition_version="1.0.0",
                inputs={"specPath": "specs/product.md"},
                principal_id="user-42",
            )
            await repository.transition_to_running(
                workflow_id=created.workflow_id, reason="worker picked it up"
            )

            cancelled = await repository.cancel(
                workflow_id=created.workflow_id, reason="operator requested cancellation"
            )

            assert cancelled.status == WorkflowInstanceStatus.CANCELLED
            assert cancelled.last_event_seq == 3

            stored = await _fetch_instance(database_url, created.workflow_id)
            assert stored is not None
            assert stored["status"] == "cancelled"

            events = await _fetch_events(database_url, created.workflow_id)
            assert [e["event_type"] for e in events] == [
                "workflow.started",
                "state.transitioned",
                "state.transitioned",
            ]
            assert events[2]["payload"]["previousStatus"] == "running"
            assert events[2]["payload"]["newStatus"] == "cancelled"
            assert events[2]["payload"]["reason"] == "operator requested cancellation"
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_cancel_from_created_succeeds_without_ever_having_run(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            repository = SqlWorkflowInstanceRepository(engine)
            created = await repository.create(
                definition_id="se.product_creation",
                definition_version="1.0.0",
                inputs={"specPath": "specs/product.md"},
                principal_id="user-42",
            )

            cancelled = await repository.cancel(
                workflow_id=created.workflow_id, reason="cancelled before it ever started"
            )

            assert cancelled.status == WorkflowInstanceStatus.CANCELLED
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_cancel_is_rejected_when_instance_does_not_exist(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            repository = SqlWorkflowInstanceRepository(engine)

            with pytest.raises(WorkflowInvalidTransitionError, match="does not exist"):
                await repository.cancel(workflow_id="wf_does_not_exist", reason="irrelevant")
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_cancel_is_rejected_when_the_instance_is_already_cancelled(database_url: str) -> None:
    """A real, disclosed, deliberate limit: cancellation is one-way —
    a second cancel against an already-cancelled instance is refused,
    the identical "guarded write affecting zero rows means refuse"
    shape :meth:`~ai_os_kernel.workflow_engine.human_approval.
    SqlApprovalRepository.decide` already establishes for its own
    one-way transition."""

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            repository = SqlWorkflowInstanceRepository(engine)
            created = await repository.create(
                definition_id="se.product_creation",
                definition_version="1.0.0",
                inputs={"specPath": "specs/product.md"},
                principal_id="user-42",
            )
            await repository.cancel(workflow_id=created.workflow_id, reason="first cancel")

            with pytest.raises(WorkflowInvalidTransitionError, match="cannot be cancelled"):
                await repository.cancel(workflow_id=created.workflow_id, reason="second cancel")
        finally:
            await engine.dispose()

    asyncio.run(_run())
