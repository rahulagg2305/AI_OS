"""Real, end-to-end proof that a human approval genuinely notifies
somebody (``P02-S07-M17-T05``) — against a real Postgres container
(ADR-0015 — no mocking the database).

Until this step a workflow could pause at a `human_approval` step,
durably, waiting on a *person*, and nothing anywhere told that person.
`NotificationService` has classified `approval.`-prefixed events since it
was built (`_APPROVAL_EVENT_TYPE_PREFIX`), but nothing in production ever
published one — the gap `notification_service.md`, `event_bus.md` §4 and
`P02-S07-M17-T04`'s own ticket each named explicitly.

What this file proves is the whole documented chain for both halves of an
approval's life: `governance.approvals` row → a `platform.event_outbox`
row written *in the same transaction* →
:class:`~ai_os_kernel.event_bus.outbox_relay.OutboxRelay` →
:class:`~ai_os_kernel.event_bus.bus.InProcessEventBus` →
:class:`~ai_os_kernel.notification.service.NotificationService` → a real
delivery plus a durable ``notification.notification_deliveries`` row.

**Which mechanism is not a choice this file made.** `event_bus.md` §5's
decision table lists "approvals" under **Transactional outbox**, on the
same row as workflow lifecycle, so a direct `InProcessEventBus.publish`
would contradict the design document.

The delivery channel is the one deliberately-fake seam (ADR-0004), the
identical arrangement `test_workflow_completion_outbox.py` already uses:
`WebhookChannel` has its own end-to-end proof against a real local HTTP
server, and proving *this* chain needs no second HTTP receiver.
Everything else — database, approval row, outbox row, relay, bus,
service, delivery recorder — is the real production class.
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
from ai_os_kernel.workflow_engine.advance_runner import WorkflowAdvanceRunner, WorkflowRunOutcome
from ai_os_kernel.workflow_engine.definition_catalog import SqlWorkflowDefinitionCatalog
from ai_os_kernel.workflow_engine.errors import ApprovalNotPendingError
from ai_os_kernel.workflow_engine.human_approval import (
    HumanApprovalStepExecutor,
    SqlApprovalRepository,
)
from ai_os_kernel.workflow_engine.lease import SqlWorkflowLeaseRepository, WorkflowLeaseService
from ai_os_kernel.workflow_engine.models import WorkflowDefinition, WorkflowStep
from ai_os_kernel.workflow_engine.repository import SqlWorkflowInstanceRepository
from ai_os_kernel.workflow_engine.service import WorkflowInstanceService
from ai_os_kernel.workflow_engine.step_executor import DispatchingStepExecutor, NoOpStepExecutor
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

# Its own definition id, deliberately not shared with
# `tests/integration/workflow_engine/test_human_approval_execution.py`:
# `register()` is an upsert keyed on `(definition_id, version)` with
# `ON CONFLICT DO NOTHING`, so two files declaring different content
# under one id/version would silently resolve to whichever registered
# first.
_DEFINITION_ID = "se.approval_outbox_test"
_DEFINITION_VERSION = "1.0.0"
_PACK_ID = "se.software_engineering"
_STEP_ID = "approve-deployment"

_REQUESTED_EVENT_TYPE = "approval.requested"
_DECIDED_EVENT_TYPE = "approval.decided"

# Relay delivery is asynchronous through a real `InProcessEventBus`
# queue, so subscriber side effects are waited on as a real condition
# rather than slept for — the same `_wait_until` shape
# `test_outbox_relay.py` establishes, and the same reason R-015's own
# 4th occurrence was fixed by replacing a blind sleep.
_DELIVERY_TIMEOUT_SECONDS = 10.0
_POLL_SECONDS = 0.01


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
    """A real, structurally-typed ``DeliveryChannel`` that captures what
    it was asked to deliver and reports genuine success."""

    def __init__(self) -> None:
        self.delivered: list[Notification] = []

    @property
    def name(self) -> str:
        return "recording"

    async def deliver(self, notification: Notification) -> bool:
        self.delivered.append(notification)
        return True


class _EchoStepExecutor:
    """Stands in for the `finish` step so this file's scope stays the
    approval path, not a real tool invocation."""

    async def execute(
        self,
        step: WorkflowStep,
        *,
        workflow_id: str | None = None,
        principal_permissions: frozenset[str] | None = None,
        workflow_permissions: frozenset[str] | None = None,
    ) -> dict[str, Any]:
        return {"status": "ok"}


def _definition() -> WorkflowDefinition:
    return WorkflowDefinition.model_validate(
        {
            "id": _DEFINITION_ID,
            "name": "Approval Outbox Test",
            "description": "test fixture",
            "version": _DEFINITION_VERSION,
            "inputs": {"type": "object"},
            "outputs": {"type": "object"},
            "steps": [
                {"id": _STEP_ID, "type": "human_approval"},
                {"id": "finish", "type": "tool", "toolId": "se.noop"},
            ],
            "humanApprovalPoints": [
                {
                    "id": _STEP_ID,
                    "name": "Approve Deployment",
                    "description": "Approve the production deployment.",
                    "context": {"target": "prod"},
                    "options": ["approve", "reject"],
                }
            ],
            "failureHandling": {"onError": "halt"},
        }
    )


def _make_composition(
    engine: AsyncEngine,
) -> tuple[WorkflowAdvanceRunner, SqlApprovalRepository]:
    repository = SqlWorkflowInstanceRepository(engine)
    definition_catalog = SqlWorkflowDefinitionCatalog(engine)
    approval_repository = SqlApprovalRepository(engine)
    step_executor = DispatchingStepExecutor(
        agent_executor=NoOpStepExecutor(),
        tool_executor=_EchoStepExecutor(),
        default_executor=NoOpStepExecutor(),
        human_approval_executor=HumanApprovalStepExecutor(
            approval_repository=approval_repository,
            instance_repository=repository,
            definition_catalog=definition_catalog,
        ),
    )
    advance_runner = WorkflowAdvanceRunner(
        instance_service=WorkflowInstanceService(repository, step_executor, definition_catalog),
        lease_service=WorkflowLeaseService(SqlWorkflowLeaseRepository(engine)),
    )
    return advance_runner, approval_repository


async def _pause_at_approval(engine: AsyncEngine) -> tuple[str, SqlApprovalRepository]:
    """Drive a real instance until it genuinely pauses on the approval."""
    definition = _definition()
    await SqlWorkflowDefinitionCatalog(engine).register(definition=definition, pack_id=_PACK_ID)
    repository = SqlWorkflowInstanceRepository(engine)
    created = await repository.create(
        definition_id=_DEFINITION_ID,
        definition_version=_DEFINITION_VERSION,
        inputs={},
        principal_id="user-42",
    )
    await repository.transition_to_running(
        workflow_id=created.workflow_id, reason="worker picked it up"
    )
    advance_runner, approval_repository = _make_composition(engine)
    result = await advance_runner.run_to_completion(
        workflow_id=created.workflow_id,
        definition=definition,
        worker_id="worker-1",
        lease_duration_seconds=60,
        max_iterations=10,
    )
    assert result.outcome is WorkflowRunOutcome.WAITING_FOR_HUMAN
    return created.workflow_id, approval_repository


async def _outbox_rows(engine: AsyncEngine, *, workflow_id: str) -> list[dict[str, Any]]:
    """Outbox rows whose payload names ``workflow_id`` — the only way to
    select by workflow, since `platform.event_outbox` deliberately has no
    such column (`data_model.md` §10)."""
    async with engine.connect() as connection:
        result = await connection.execute(
            sa.select(event_outbox).order_by(event_outbox.c.created_at)
        )
        return [
            dict(row)
            for row in result.mappings().all()
            if row["payload"].get("workflow_id") == workflow_id
        ]


async def _wait_for(predicate: Any) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _DELIVERY_TIMEOUT_SECONDS
    while loop.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(_POLL_SECONDS)
    return False


def test_a_pending_approval_genuinely_notifies_somebody(database_url: str) -> None:
    """The headline proof: a paused workflow now reaches a real
    notification, so the human it is waiting on can actually be told."""

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
            workflow_id, _ = await _pause_at_approval(engine)

            # 1. The pause wrote a real, undispatched outbox row in the
            #    same transaction as the `pending` approvals row.
            rows = await _outbox_rows(engine, workflow_id=workflow_id)
            assert len(rows) == 1
            requested = rows[0]
            assert requested["event_type"] == _REQUESTED_EVENT_TYPE
            assert requested["dispatched_at"] is None
            assert requested["outbox_id"].startswith("obx_")
            assert requested["payload"]["step_id"] == _STEP_ID
            assert requested["payload"]["approval_class"] == _STEP_ID
            assert requested["payload"]["title"] == "Approve Deployment"
            assert requested["payload"]["approval_id"].startswith("appr_")
            # No `timeout` declared on this point, so no expiry.
            assert requested["payload"]["expires_at"] is None

            # 2. The real relay drains it into the real bus.
            result = await OutboxRelay(engine, bus).tick_once(limit=OUTBOX_RELAY_BATCH_LIMIT)
            assert requested["outbox_id"] in result.dispatched

            # 3. The real NotificationService classifies it as `approval`
            #    — the `approval.` prefix branch that had never once
            #    fired in production before this step — and delivers it.
            assert await _wait_for(lambda: len(channel.delivered) == 1), (
                "the pending approval never reached the NotificationService"
            )
            delivered = channel.delivered[0]
            assert delivered.notification_type == "approval"
            assert delivered.payload["workflow_id"] == workflow_id

            # 4. And the real recorder persisted the real, final outcome.
            recorded = await _recorded_approvals(engine, workflow_id)
            assert len(recorded) == 1
            assert recorded[0]["status"] == "sent"
            assert recorded[0]["channel"] == "recording"
        finally:
            service.close()
            await bus.aclose()
            await engine.dispose()

    asyncio.run(_run())


async def _recorded_approvals(engine: AsyncEngine, workflow_id: str) -> list[dict[str, Any]]:
    """Delivery rows for this workflow, polled — `_on_event` records
    *after* it delivers, so the channel having been called does not yet
    mean the row is committed."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _DELIVERY_TIMEOUT_SECONDS
    while True:
        async with engine.connect() as connection:
            found = await connection.execute(
                sa.select(notification_deliveries).where(
                    notification_deliveries.c.notification_type == "approval"
                )
            )
            rows = [
                dict(r)
                for r in found.mappings().all()
                if r["payload"].get("workflow_id") == workflow_id
            ]
        if rows or loop.time() >= deadline:
            return rows
        await asyncio.sleep(_POLL_SECONDS)


def test_a_real_decision_is_announced_with_its_decider(database_url: str) -> None:
    """The other half: whoever was told a decision was needed is told it
    was made, and by whom. R-001 makes attributable human approval a
    permanent hard rule, so the decider travels with the event."""

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            workflow_id, approval_repository = await _pause_at_approval(engine)
            approval = await approval_repository.get_by_step(
                workflow_id=workflow_id, step_id=_STEP_ID
            )
            assert approval is not None

            await approval_repository.decide(
                approval_id=approval.approval_id,
                principal_id="user-99",
                decision="approved",
                comment="Looks good to ship.",
            )

            rows = await _outbox_rows(engine, workflow_id=workflow_id)
            assert [r["event_type"] for r in rows] == [
                _REQUESTED_EVENT_TYPE,
                _DECIDED_EVENT_TYPE,
            ]
            decided = rows[1]
            assert decided["payload"]["decision"] == "approved"
            assert decided["payload"]["decided_by"] == "user-99"
            assert decided["payload"]["approval_id"] == approval.approval_id
            assert decided["dispatched_at"] is None
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_refused_double_decision_announces_nothing(database_url: str) -> None:
    """The governance property, proven rather than assumed: a decision
    that does not commit is never announced.

    `decide()` is guarded by ``WHERE status = 'pending'``, so a second
    attempt affects zero rows and raises. Because the outbox write lives
    inside that same transaction, no second `approval.decided` event can
    escape — an observer can never be told of a decision that was
    refused. This is exactly the failure mode ADR-0012's
    same-transaction rule exists to prevent, and it matters more here
    than anywhere else: an announced-but-uncommitted approval decision
    would be a governance defect, not a stale notification.
    """

    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            workflow_id, approval_repository = await _pause_at_approval(engine)
            approval = await approval_repository.get_by_step(
                workflow_id=workflow_id, step_id=_STEP_ID
            )
            assert approval is not None

            await approval_repository.decide(
                approval_id=approval.approval_id,
                principal_id="user-99",
                decision="approved",
                comment=None,
            )
            before = await _outbox_rows(engine, workflow_id=workflow_id)

            with pytest.raises(ApprovalNotPendingError):
                await approval_repository.decide(
                    approval_id=approval.approval_id,
                    principal_id="someone-else",
                    decision="rejected",
                    comment="second attempt",
                )

            after = await _outbox_rows(engine, workflow_id=workflow_id)
            assert [r["outbox_id"] for r in after] == [r["outbox_id"] for r in before]
            assert [r["event_type"] for r in after] == [
                _REQUESTED_EVENT_TYPE,
                _DECIDED_EVENT_TYPE,
            ]
            assert all(r["payload"].get("decided_by") != "someone-else" for r in after)
        finally:
            await engine.dispose()

    asyncio.run(_run())
