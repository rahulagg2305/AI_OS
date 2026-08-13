"""Real, end-to-end proof of the transactional-outbox *producer* path
(``P02-S07-M17-T04``) against a real Postgres container (ADR-0015 — no
mocking the database).

What this file proves that nothing previously could: a genuinely
committed workflow completion travels the whole documented ADR-0012
chain — ``workflow_instances.status = 'completed'`` → a
``platform.event_outbox`` row written *in the same transaction* →
:class:`~ai_os_kernel.event_bus.outbox_relay.OutboxRelay` →
:class:`~ai_os_kernel.event_bus.bus.InProcessEventBus` →
:class:`~ai_os_kernel.notification.service.NotificationService` → a real
delivery and a real, durable ``notification.notification_deliveries``
row.

Before this step every link existed and was tested in isolation, but the
chain was severed at the first one: ``platform.event_outbox`` had no
writer at all (``ai_os_kernel.event_bus``'s own package docstring said
so), so ``tests/integration/event_bus/test_outbox_relay.py`` had to seed
rows by hand, and ``NotificationService``'s ``workflow.completed``
category could never fire in a real process.

The channel here is a recording fake — the one seam that is *not* real,
for the reason ADR-0004 already establishes and
``tests/integration/notification/test_recorder.py`` already relies on:
proving this chain does not need a live HTTP receiver, and
:class:`~ai_os_kernel.notification.webhook.WebhookChannel` has its own
end-to-end proof against a real local HTTP server. Everything else in
the chain — the database, the outbox row, the relay, the bus, the
service, the delivery recorder — is the real production class.
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

from ai_os_kernel.event_bus.bus import InProcessEventBus
from ai_os_kernel.event_bus.outbox_relay import OUTBOX_RELAY_BATCH_LIMIT, OutboxRelay
from ai_os_kernel.event_bus.outbox_writer import write_outbox_event
from ai_os_kernel.notification.models import Notification
from ai_os_kernel.notification.recorder import SqlNotificationDeliveryRecorder
from ai_os_kernel.notification.schema import notification_deliveries
from ai_os_kernel.notification.service import NotificationService
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.platform_schema import event_outbox
from ai_os_kernel.workflow_engine.definition_catalog import SqlWorkflowDefinitionCatalog
from ai_os_kernel.workflow_engine.instance import WorkflowInstanceStatus
from ai_os_kernel.workflow_engine.models import WorkflowDefinition
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

_DEFINITION_ID = "se.product_creation"
_DEFINITION_VERSION = "1.0.0"
_COMPLETION_EVENT_TYPE = "workflow.completed"

# The relay's own delivery is asynchronous through a real
# `InProcessEventBus` queue, so a subscriber's side effect is observed by
# polling rather than by an arbitrary sleep — the identical `_wait_until`
# shape `test_outbox_relay.py` already establishes for the same reason.
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


def _two_step_definition() -> WorkflowDefinition:
    return WorkflowDefinition.model_validate(
        {
            "id": _DEFINITION_ID,
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
                },
                {"id": "implement", "type": "agent", "agentId": "se.software_engineering/analyst"},
            ],
            "failureHandling": {"onError": "halt"},
        }
    )


async def _register_definition(engine: Any, definition: WorkflowDefinition) -> None:
    """``workflow_instances`` carries a real foreign key onto
    ``catalog.workflow_definitions``, so the definition has to exist
    before any instance of it can. Registration upserts idempotently
    (``SqlWorkflowDefinitionCatalog.register``'s own ``ON CONFLICT``),
    so every test in this module may call it freely."""
    await SqlWorkflowDefinitionCatalog(engine).register(
        definition=definition, pack_id="se.software_engineering"
    )


async def _advance_to_completion(
    repository: SqlWorkflowInstanceRepository, definition: WorkflowDefinition
) -> str:
    """Drive one real instance from ``create`` to ``completed`` through
    the real repository, returning its ``workflow_id``."""
    created = await repository.create(
        definition_id=_DEFINITION_ID,
        definition_version=_DEFINITION_VERSION,
        inputs={"specPath": "specs/product.md"},
        principal_id="user-42",
    )
    await repository.transition_to_running(
        workflow_id=created.workflow_id, reason="worker picked it up"
    )
    await repository.advance_workflow(
        workflow_id=created.workflow_id,
        definition_id=_DEFINITION_ID,
        definition_version=_DEFINITION_VERSION,
        expected_current_step_id=None,
        next_step=definition.steps[0],
        outputs={},
    )
    await repository.advance_workflow(
        workflow_id=created.workflow_id,
        definition_id=_DEFINITION_ID,
        definition_version=_DEFINITION_VERSION,
        expected_current_step_id="analyze_requirements",
        next_step=definition.steps[1],
        outputs={},
    )
    completed = await repository.advance_workflow(
        workflow_id=created.workflow_id,
        definition_id=_DEFINITION_ID,
        definition_version=_DEFINITION_VERSION,
        expected_current_step_id="implement",
        next_step=None,
        outputs={},
    )
    assert completed.status is WorkflowInstanceStatus.COMPLETED
    return created.workflow_id


async def _fetch_outbox_rows(engine: Any, *, workflow_id: str) -> list[dict[str, Any]]:
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


def test_a_committed_completion_reaches_a_real_notification(database_url: str) -> None:
    """The headline proof: the whole ADR-0012 chain, all real classes."""

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
            definition = _two_step_definition()
            await _register_definition(engine, definition)
            workflow_id = await _advance_to_completion(repository, definition)

            # 1. The terminal transaction wrote a real, undispatched
            #    outbox row carrying the workflow id in its payload.
            rows = await _fetch_outbox_rows(engine, workflow_id=workflow_id)
            assert len(rows) == 1
            assert rows[0]["event_type"] == _COMPLETION_EVENT_TYPE
            assert rows[0]["payload"] == {"workflow_id": workflow_id}
            assert rows[0]["dispatched_at"] is None
            assert rows[0]["outbox_id"].startswith("obx_")

            # 2. The real relay drains it into the real bus.
            result = await OutboxRelay(engine, bus).tick_once(limit=OUTBOX_RELAY_BATCH_LIMIT)
            assert rows[0]["outbox_id"] in result.dispatched

            # 3. The real NotificationService delivers it.
            assert await _wait_until(
                lambda: len(channel.delivered) == 1, timeout_seconds=_DELIVERY_TIMEOUT_SECONDS
            ), "the completion event never reached the NotificationService"
            delivered = channel.delivered[0]
            assert delivered.notification_type == "completion"
            assert delivered.payload == {"workflow_id": workflow_id}

            # 4. And the real recorder persisted the real, final outcome.
            #    `workflow_id` is null on the row because the relay
            #    rebuilds `Event.workflow_id` as None — the outbox table
            #    has no such column (outbox_relay.py's own disclosed
            #    limitation); the payload above is what carries it.
            async def _recorded() -> list[dict[str, Any]]:
                async with engine.connect() as connection:
                    found = await connection.execute(
                        sa.select(notification_deliveries).where(
                            notification_deliveries.c.notification_type == "completion"
                        )
                    )
                    return [
                        dict(row)
                        for row in found.mappings().all()
                        if row["payload"].get("workflow_id") == workflow_id
                    ]

            # Polled, not read once: `_on_event` records *after* it
            # delivers, so the channel having been called does not yet
            # mean the row is committed. Reading it once raced and
            # genuinely failed here before this loop was added.
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
            assert recorded[0]["workflow_id"] is None

            # 5. The relay never redispatches an already-dispatched row,
            #    so a second pass delivers nothing further.
            second = await OutboxRelay(engine, bus).tick_once(limit=OUTBOX_RELAY_BATCH_LIMIT)
            assert rows[0]["outbox_id"] not in second.dispatched
        finally:
            service.close()
            await bus.aclose()
            await engine.dispose()

    asyncio.run(_run())


def test_a_rolled_back_transaction_leaves_no_outbox_row(database_url: str) -> None:
    """ADR-0012's actual guarantee, proven directly on the writer: the
    outbox row joins its caller's transaction, so a rollback takes the
    event with it. This is what makes "no event can ever describe a
    state change that did not commit" true rather than aspirational —
    and it is the reason
    :func:`~ai_os_kernel.event_bus.outbox_writer.write_outbox_event`
    takes an ``AsyncConnection`` instead of an ``AsyncEngine``.
    """

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            marker = "wf_rolled_back_sentinel"
            with pytest.raises(RuntimeError, match="deliberate"):
                async with engine.begin() as connection:
                    await write_outbox_event(
                        connection,
                        event_type=_COMPLETION_EVENT_TYPE,
                        payload={"workflow_id": marker},
                    )
                    raise RuntimeError("deliberate failure after the outbox write")

            assert await _fetch_outbox_rows(engine, workflow_id=marker) == []
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_non_terminal_advance_writes_no_outbox_row(database_url: str) -> None:
    """Only the terminal transition outboxes. Mid-run step progress is
    recorded in ``workflow.workflow_events`` — this engine's own
    event-sourcing log — and must not become a notification, or every
    multi-step workflow would notify once per step.
    """

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            repository = SqlWorkflowInstanceRepository(engine)
            definition = _two_step_definition()
            await _register_definition(engine, definition)
            created = await repository.create(
                definition_id=_DEFINITION_ID,
                definition_version=_DEFINITION_VERSION,
                inputs={"specPath": "specs/product.md"},
                principal_id="user-42",
            )
            await repository.transition_to_running(
                workflow_id=created.workflow_id, reason="worker picked it up"
            )
            advanced = await repository.advance_workflow(
                workflow_id=created.workflow_id,
                definition_id=_DEFINITION_ID,
                definition_version=_DEFINITION_VERSION,
                expected_current_step_id=None,
                next_step=definition.steps[0],
                outputs={},
            )
            assert advanced.status is WorkflowInstanceStatus.RUNNING
            assert await _fetch_outbox_rows(engine, workflow_id=created.workflow_id) == []
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_failed_completion_notifies_nobody(database_url: str) -> None:
    """The workflow-level counterpart to the rollback proof: when the
    terminal transaction genuinely fails, the instance is not completed
    *and* no outbox row survives, so no observer is ever told about a
    completion that did not happen.

    The failure is forced the same way
    ``tests/integration/workflow_engine/test_step_progression.py``
    already does it — pre-inserting the ``seq`` the completion event
    would claim, so that insert collides inside the transaction.
    """

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            repository = SqlWorkflowInstanceRepository(engine)
            definition = _two_step_definition()
            await _register_definition(engine, definition)
            created = await repository.create(
                definition_id=_DEFINITION_ID,
                definition_version=_DEFINITION_VERSION,
                inputs={"specPath": "specs/product.md"},
                principal_id="user-42",
            )
            await repository.transition_to_running(
                workflow_id=created.workflow_id, reason="worker picked it up"
            )
            await repository.advance_workflow(
                workflow_id=created.workflow_id,
                definition_id=_DEFINITION_ID,
                definition_version=_DEFINITION_VERSION,
                expected_current_step_id=None,
                next_step=definition.steps[0],
                outputs={},
            )
            await repository.advance_workflow(
                workflow_id=created.workflow_id,
                definition_id=_DEFINITION_ID,
                definition_version=_DEFINITION_VERSION,
                expected_current_step_id="analyze_requirements",
                next_step=definition.steps[1],
                outputs={},
            )
            # last_event_seq is 6; completing would append seq=7.
            async with engine.begin() as connection:
                await connection.execute(
                    sa.text(
                        "INSERT INTO workflow.workflow_events "
                        "(event_id, workflow_id, seq, event_type, schema_version, "
                        " payload, occurred_at) "
                        "VALUES ('evt_outbox_collision', :workflow_id, 7, "
                        " 'manual.duplicate', 1, '{}'::jsonb, now())"
                    ),
                    {"workflow_id": created.workflow_id},
                )

            with pytest.raises(Exception):  # noqa: B017 - the repository's own wrapped error
                await repository.advance_workflow(
                    workflow_id=created.workflow_id,
                    definition_id=_DEFINITION_ID,
                    definition_version=_DEFINITION_VERSION,
                    expected_current_step_id="implement",
                    next_step=None,
                    outputs={},
                )

            still_running = await repository.get_instance(created.workflow_id)
            assert still_running is not None
            assert still_running.status is not WorkflowInstanceStatus.COMPLETED
            assert await _fetch_outbox_rows(engine, workflow_id=created.workflow_id) == []
        finally:
            await engine.dispose()

    asyncio.run(_run())
