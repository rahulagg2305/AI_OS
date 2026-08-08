"""Real write path for ``notification.notification_deliveries``
(`P06-S05-M22-T02`) — mirrors
:class:`~ai_os_kernel.workflow_engine.gate_result_recorder.SqlGateResultRecorder`'s
own exact shape: a real, insert-only recorder, one row per real
delivery attempt.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.notification.errors import NotificationDeliveryRecordingError
from ai_os_kernel.notification.ids import new_notification_delivery_id
from ai_os_kernel.notification.models import Notification
from ai_os_kernel.notification.schema import notification_deliveries


class NotificationDeliveryRecorder(Protocol):
    """Persistence boundary for recording one real delivery attempt's
    real, final outcome — the seam a fake implementation substitutes in
    unit tests (ADR-0004: interface-driven, configuration over code)."""

    async def record(self, notification: Notification) -> None: ...


class SqlNotificationDeliveryRecorder:
    """The only implementation of :class:`NotificationDeliveryRecorder`
    at this stage: SQLAlchemy 2.0 Core against Postgres (ADR-0011)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def record(self, notification: Notification) -> None:
        try:
            async with self._engine.begin() as connection:
                await connection.execute(
                    sa.insert(notification_deliveries).values(
                        delivery_id=new_notification_delivery_id(),
                        notification_type=notification.notification_type,
                        channel=notification.channel,
                        status=notification.status,
                        workflow_id=notification.workflow_id,
                        trace_id=notification.trace_id,
                        payload=notification.payload,
                        recorded_at=datetime.now(UTC),
                    )
                )
        except sa.exc.SQLAlchemyError as exc:
            raise NotificationDeliveryRecordingError(
                f"failed to record delivery for notification type "
                f"'{notification.notification_type}' on channel '{notification.channel}': {exc}"
            ) from exc
