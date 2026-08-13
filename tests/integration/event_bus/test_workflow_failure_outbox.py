"""Real, end-to-end proof that a terminal workflow *failure* travels the
transactional-outbox chain, against a real Postgres container (ADR-0015 —
no mocking the database).

The exact mirror of ``test_workflow_completion_outbox.py``, for the other
terminal state. ``P02-S01-M05-T17`` (R-016) gave ``workflow_instances``
its first real ``failed`` writer, but that transition wrote only the
engine's own ``state.transitioned`` event-sourcing row — read by
``list_events``/``GET /workflows/{id}/events`` and subscribed to by
nothing. So the durable state change existed while the *domain event* did
not, and :class:`~ai_os_kernel.notification.service.NotificationService`'s
``workflow.failed`` category (``_FAILURE_EVENT_TYPE``, subscribed since
that service was built) still had no producer anywhere in the codebase.

What this file proves that nothing previously could: a genuinely
committed failure travels the whole documented ADR-0012 chain —
``workflow_instances.status = 'failed'`` → a ``platform.event_outbox``
row written *in the same transaction* →
:class:`~ai_os_kernel.event_bus.outbox_relay.OutboxRelay` →
:class:`~ai_os_kernel.event_bus.bus.InProcessEventBus` →
:class:`~ai_os_kernel.notification.service.NotificationService` → a real
``failure`` delivery and a real, durable
``notification.notification_deliveries`` row.

The last test drives the **real worker loop** to real retry exhaustion,
so the chain is proven from the production path that actually produces
failures — not only from a direct repository call.

The channel here is a recording fake — the one seam that is *not* real,
for the reason ADR-0004 establishes and the completion counterpart
already relies on; :class:`~ai_os_kernel.notification.webhook.
WebhookChannel` has its own proof against a real local HTTP server.
Everything else — the database, the outbox row, the relay, the bus, the
service, the delivery recorder, the worker loop — is the real production
class.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.event_bus.bus import InProcessEventBus
from ai_os_kernel.event_bus.outbox_relay import OUTBOX_RELAY_BATCH_LIMIT, OutboxRelay
from ai_os_kernel.notification.models import Notification
from ai_os_kernel.notification.recorder import SqlNotificationDeliveryRecorder
from ai_os_kernel.notification.schema import notification_deliveries
from ai_os_kernel.notification.service import NotificationService
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.platform_schema import event_outbox
from ai_os_kernel.workflow_engine.advance_runner import WorkflowAdvanceRunner
from ai_os_kernel.workflow_engine.definition_catalog import SqlWorkflowDefinitionCatalog
from ai_os_kernel.workflow_engine.errors import WorkflowInvalidTransitionError
from ai_os_kernel.workflow_engine.instance import WorkflowInstanceStatus
from ai_os_kernel.workflow_engine.lease import SqlWorkflowLeaseRepository, WorkflowLeaseService
from ai_os_kernel.workflow_engine.models import WorkflowDefinition, WorkflowStep
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from ai_os_kernel.workflow_engine.service import WorkflowInstanceService
from ai_os_kernel.workflow_engine.step_executor import DispatchingStepExecutor, NoOpStepExecutor
from ai_os_kernel.workflow_engine.worker_loop import WorkflowWorkerLoop
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

_DEFINITION_ID = "se.failure_outbox_test"
_PACK_ID = "se.software_engineering"
_AGENT_ID = "se.software_engineering/analyst"
_STEP_ID = "always_fails"
_FAILURE_EVENT_TYPE = "workflow.failed"

# The relay's delivery is asynchronous through a real `InProcessEventBus`
# queue, so a subscriber's side effect is observed by polling rather than
# by an arbitrary sleep — the `_wait_until` shape the completion
# counterpart and `test_outbox_relay.py` both already establish.
_DELIVERY_TIMEOUT_SECONDS = 5.0


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


class _RecordingChannel:
    """A real, structurally-typed
    :class:`~ai_os_kernel.notification.service.DeliveryChannel` that
    captures what it was asked to deliver and reports real success."""

    def __init__(self) -> None:
        self.delivered: list[Notification] = []

    @property
    def name(self) -> str:
        return "recording"

    async def deliver(self, notification: Notification) -> bool:
        self.delivered.append(notification)
        return True


class _AlwaysFailingStepExecutor:
    """A real ``StepExecutor`` whose step genuinely raises every time —
    the permanently-broken step that drives the worker loop to real
    retry exhaustion, and therefore to a real terminal failure."""

    def __init__(self) -> None:
        self.call_count = 0

    async def execute(
        self,
        step: WorkflowStep,
        *,
        workflow_id: str | None = None,
        principal_permissions: frozenset[str] | None = None,
        workflow_permissions: frozenset[str] | None = None,
    ) -> dict[str, Any]:
        self.call_count += 1
        raise RuntimeError("this step is permanently broken")


def _definition(*, version: str) -> WorkflowDefinition:
    return WorkflowDefinition.model_validate(
        {
            "id": _DEFINITION_ID,
            "name": "Failure Outbox Test",
            "description": "test fixture",
            "version": version,
            "inputs": {"type": "object"},
            "outputs": {"type": "object"},
            "steps": [{"id": _STEP_ID, "type": "agent", "agentId": _AGENT_ID}],
            "failureHandling": {"onError": "halt"},
        }
    )


async def _create_running_instance(engine: AsyncEngine, definition: WorkflowDefinition) -> str:
    """``workflow_instances`` carries a real foreign key onto
    ``catalog.workflow_definitions``, so the definition has to exist
    before any instance of it can. Registration upserts idempotently."""
    await SqlWorkflowDefinitionCatalog(engine).register(definition=definition, pack_id=_PACK_ID)
    repository = SqlWorkflowInstanceRepository(engine)
    created = await repository.create(
        definition_id=definition.id,
        definition_version=definition.version,
        inputs={},
        principal_id="user-42",
    )
    await repository.transition_to_running(
        workflow_id=created.workflow_id, reason="worker picked it up"
    )
    return created.workflow_id


async def _fetch_outbox_rows(engine: AsyncEngine, *, workflow_id: str) -> list[dict[str, Any]]:
    """Every outbox row whose payload names ``workflow_id`` — the only
    way to select by workflow, since ``platform.event_outbox``
    deliberately has no such column (``data_model.md`` §10)."""
    async with engine.connect() as connection:
        result = await connection.execute(
            sa.select(event_outbox).order_by(event_outbox.c.created_at)
        )
        return [
            dict(row)
            for row in result.mappings().all()
            if row["payload"].get("workflow_id") == workflow_id
        ]


async def _wait_until(predicate: Any, *, timeout_seconds: float) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    while loop.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return False


def test_a_committed_failure_reaches_a_real_failure_notification(database_url: str) -> None:
    """The headline proof: the whole ADR-0012 chain for the failure
    branch, all real classes. Before this step step 1 wrote nothing at
    all, so nothing downstream could ever fire."""

    async def _run() -> None:
        engine = build_engine(database_url)
        bus = InProcessEventBus()
        channel = _RecordingChannel()
        service = NotificationService(
            event_bus=bus,
            channel=channel,
            recorder=SqlNotificationDeliveryRecorder(engine),
        )
        try:
            repository = SqlWorkflowInstanceRepository(engine)
            workflow_id = await _create_running_instance(engine, _definition(version="1.0.0"))

            failed = await repository.mark_failed(
                workflow_id=workflow_id, reason="the step exhausted its retry budget"
            )
            assert failed.status is WorkflowInstanceStatus.FAILED

            # 1. The terminal transaction wrote a real, undispatched
            #    outbox row carrying the workflow id and the real reason.
            rows = await _fetch_outbox_rows(engine, workflow_id=workflow_id)
            assert len(rows) == 1
            assert rows[0]["event_type"] == _FAILURE_EVENT_TYPE
            assert rows[0]["payload"] == {
                "workflow_id": workflow_id,
                "reason": "the step exhausted its retry budget",
            }
            assert rows[0]["dispatched_at"] is None
            assert rows[0]["outbox_id"].startswith("obx_")

            # 2. The real relay drains it into the real bus.
            result = await OutboxRelay(engine, bus).tick_once(limit=OUTBOX_RELAY_BATCH_LIMIT)
            assert rows[0]["outbox_id"] in result.dispatched

            # 3. The real NotificationService classifies it as `failure`
            #    — the category that had a subscriber and no producer.
            assert await _wait_until(
                lambda: len(channel.delivered) == 1, timeout_seconds=_DELIVERY_TIMEOUT_SECONDS
            ), "the failure event never reached the NotificationService"
            delivered = channel.delivered[0]
            assert delivered.notification_type == "failure"
            assert delivered.payload["workflow_id"] == workflow_id

            # 4. And the real recorder persisted the real, final outcome.
            #    Polled, not read once: `_on_event` records *after* it
            #    delivers, so the channel having been called does not yet
            #    mean the row is committed.
            async def _recorded() -> list[dict[str, Any]]:
                async with engine.connect() as connection:
                    found = await connection.execute(
                        sa.select(notification_deliveries).where(
                            notification_deliveries.c.notification_type == "failure"
                        )
                    )
                    return [
                        dict(row)
                        for row in found.mappings().all()
                        if row["payload"].get("workflow_id") == workflow_id
                    ]

            recorded: list[dict[str, Any]] = []
            deadline = asyncio.get_running_loop().time() + _DELIVERY_TIMEOUT_SECONDS
            while asyncio.get_running_loop().time() < deadline:
                recorded = await _recorded()
                if recorded:
                    break
                await asyncio.sleep(0.01)
            assert len(recorded) == 1
            assert recorded[0]["status"] == "sent"
            assert recorded[0]["channel"] == "recording"

            # 5. The relay never redispatches an already-dispatched row.
            second = await OutboxRelay(engine, bus).tick_once(limit=OUTBOX_RELAY_BATCH_LIMIT)
            assert rows[0]["outbox_id"] not in second.dispatched
        finally:
            service.close()
            await bus.aclose()
            await engine.dispose()

    asyncio.run(_run())


def test_a_refused_transition_writes_no_outbox_row(database_url: str) -> None:
    """ADR-0012's guarantee on this writer specifically: the outbox row
    joins ``mark_failed``'s own transaction, so a transition the guarded
    CAS *refuses* emits no event at all. Without this, a rejected second
    failure could still tell the rest of the platform the workflow
    failed twice."""

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            repository = SqlWorkflowInstanceRepository(engine)
            workflow_id = await _create_running_instance(engine, _definition(version="1.0.1"))

            await repository.mark_failed(workflow_id=workflow_id, reason="first, legitimate")
            assert len(await _fetch_outbox_rows(engine, workflow_id=workflow_id)) == 1

            # Already terminal: the CAS matches zero rows and refuses.
            with pytest.raises(WorkflowInvalidTransitionError):
                await repository.mark_failed(workflow_id=workflow_id, reason="second, refused")

            # Still exactly one — the refused call added nothing.
            rows = await _fetch_outbox_rows(engine, workflow_id=workflow_id)
            assert len(rows) == 1
            assert rows[0]["payload"]["reason"] == "first, legitimate"
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_the_real_worker_loop_emits_the_failure_event_on_retry_exhaustion(
    database_url: str,
) -> None:
    """The production path, end to end: a permanently-failing step drives
    the real :class:`WorkflowWorkerLoop` to real retry exhaustion, and the
    resulting terminal failure genuinely produces the outbox event.

    This is the test that makes the chain real rather than merely
    reachable — nothing in production calls ``mark_failed`` directly."""

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            definition = _definition(version="1.0.2")
            workflow_id = await _create_running_instance(engine, definition)

            executor = _AlwaysFailingStepExecutor()
            step_executor = DispatchingStepExecutor(
                agent_executor=executor,
                tool_executor=NoOpStepExecutor(),
                default_executor=NoOpStepExecutor(),
            )
            repository = SqlWorkflowInstanceRepository(engine)
            catalog = SqlWorkflowDefinitionCatalog(engine)
            worker = WorkflowWorkerLoop(
                repository=repository,
                advance_runner=WorkflowAdvanceRunner(
                    WorkflowInstanceService(repository, step_executor, catalog),
                    WorkflowLeaseService(SqlWorkflowLeaseRepository(engine)),
                ),
                definition_catalog=catalog,
                worker_id="worker-1",
            )

            for _ in range(10):
                await worker.tick_once(limit=100, lease_duration_seconds=60)
                instance = await repository.get_instance(workflow_id)
                assert instance is not None
                if instance.status is not WorkflowInstanceStatus.RUNNING:
                    break

            instance = await repository.get_instance(workflow_id)
            assert instance is not None
            assert instance.status is WorkflowInstanceStatus.FAILED

            rows = await _fetch_outbox_rows(engine, workflow_id=workflow_id)
            assert len(rows) == 1
            assert rows[0]["event_type"] == _FAILURE_EVENT_TYPE
            assert "exhausted its retry budget" in rows[0]["payload"]["reason"]
        finally:
            await engine.dispose()

    asyncio.run(_run())
