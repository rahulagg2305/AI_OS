"""SqlNotificationDeliveryRecorder against a real Postgres container
(ADR-0015 — no mocking the database). Proves a real ``record()`` call
genuinely inserts one row into ``notification.notification_deliveries``
with the values it was given, that repeated calls each insert their own
distinct row (no ``ON CONFLICT`` collapsing, since ``delivery_id`` is a
freshly-generated ULID every time), and that ``workflow_id``/``trace_id``
are genuinely nullable (no FK, per this schema's own deliberate no-
cross-schema-FK precedent).
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

from ai_os_kernel.notification.models import Notification
from ai_os_kernel.notification.recorder import SqlNotificationDeliveryRecorder
from ai_os_kernel.notification.schema import notification_deliveries
from ai_os_kernel.persistence.engine import build_engine
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


def test_record_writes_a_real_row_with_the_given_values(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            recorder = SqlNotificationDeliveryRecorder(engine)
            notification = Notification(
                notification_type="approval",
                channel="webhook",
                status="sent",
                workflow_id="wf_real_notification_1",
                trace_id="trace_real_1",
                payload={"approvalId": "appr-1"},
            )

            await recorder.record(notification)

            async with engine.connect() as connection:
                row = (
                    (
                        await connection.execute(
                            sa.select(notification_deliveries).where(
                                notification_deliveries.c.workflow_id == "wf_real_notification_1"
                            )
                        )
                    )
                    .mappings()
                    .one()
                )

            assert row["delivery_id"].startswith("ndel_")
            assert row["notification_type"] == "approval"
            assert row["channel"] == "webhook"
            assert row["status"] == "sent"
            assert row["trace_id"] == "trace_real_1"
            assert row["payload"] == {"approvalId": "appr-1"}
            assert row["recorded_at"] is not None
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_record_accepts_a_genuinely_null_workflow_and_trace_id(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            recorder = SqlNotificationDeliveryRecorder(engine)
            notification = Notification(
                notification_type="failure",
                channel="webhook",
                status="failed",
                workflow_id=None,
                trace_id=None,
                payload={},
            )

            await recorder.record(notification)

            async with engine.connect() as connection:
                row = (
                    (
                        await connection.execute(
                            sa.select(notification_deliveries).where(
                                notification_deliveries.c.notification_type == "failure",
                                notification_deliveries.c.workflow_id.is_(None),
                            )
                        )
                    )
                    .mappings()
                    .one()
                )

            assert row["status"] == "failed"
            assert row["workflow_id"] is None
            assert row["trace_id"] is None
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_repeated_calls_each_insert_their_own_distinct_row(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            recorder = SqlNotificationDeliveryRecorder(engine)
            notification = Notification(
                notification_type="completion",
                channel="webhook",
                status="sent",
                workflow_id="wf_real_notification_repeat",
                trace_id=None,
                payload={"n": 1},
            )

            await recorder.record(notification)
            await recorder.record(notification)

            async with engine.connect() as connection:
                count = (
                    await connection.execute(
                        sa.select(sa.func.count())
                        .select_from(notification_deliveries)
                        .where(
                            notification_deliveries.c.workflow_id == "wf_real_notification_repeat"
                        )
                    )
                ).scalar_one()

            assert count == 2
        finally:
            await engine.dispose()

    asyncio.run(_run())
