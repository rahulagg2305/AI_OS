"""Real proof of :class:`OutboxRelay` against a real Postgres container
(ADR-0015 — no mocking the database): a real ``platform.event_outbox``
row is genuinely relayed through a real
:class:`~ai_os_kernel.event_bus.bus.InProcessEventBus` and delivered to
a real subscriber; an already-dispatched row is never redispatched; and
a genuine dispatch failure leaves the row a real candidate for retry on
the next pass rather than silently losing it.

No writer exists for ``platform.event_outbox`` yet (``P02-S07-M17-T01``
built the schema only), so rows are inserted directly here — the same
"seed the row a future writer would produce" shape
``tests/integration/workflow_engine/test_scheduler.py`` already
establishes for ``workflow_instances.scheduled_at``.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.event_bus.bus import EventHandler, InProcessEventBus, Subscription
from ai_os_kernel.event_bus.ids import new_outbox_id
from ai_os_kernel.event_bus.models import Event
from ai_os_kernel.event_bus.outbox_relay import OutboxRelay
from ai_os_kernel.persistence.engine import build_engine
from ai_os_kernel.persistence.platform_schema import event_outbox
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


class _FailingEventBus:
    """A real, structurally-typed :class:`EventBus` whose ``publish``
    always raises — isolates the relay's own retry behavior from
    :class:`InProcessEventBus`'s own, separately-tested delivery logic.
    """

    async def publish(self, event: Event) -> None:
        raise RuntimeError("simulated dispatch failure")

    def subscribe(
        self, event_type: str | None, handler: EventHandler
    ) -> Subscription:  # pragma: no cover
        raise NotImplementedError

    def unsubscribe(self, subscription: Subscription) -> None:  # pragma: no cover
        raise NotImplementedError

    async def aclose(self) -> None:  # pragma: no cover
        return None


async def _insert_outbox_row(
    engine: AsyncEngine,
    *,
    event_type: str = "workflow.completed",
    trace_id: str | None = "trace-abc",
    payload: dict[str, object] | None = None,
    created_at: datetime | None = None,
) -> str:
    outbox_id = new_outbox_id()
    async with engine.begin() as connection:
        await connection.execute(
            sa.insert(event_outbox).values(
                outbox_id=outbox_id,
                event_type=event_type,
                schema_version=1,
                payload=payload or {"detail": "real payload"},
                trace_id=trace_id,
                created_at=created_at or datetime.now(UTC),
            )
        )
    return outbox_id


async def _wait_until(predicate: object, *, timeout_seconds: float = 2.0) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    while loop.time() < deadline:
        if predicate():  # type: ignore[operator]
            return True
        await asyncio.sleep(0.01)
    return False


async def _fetch_dispatch_state(engine: AsyncEngine, *, outbox_id: str) -> sa.RowMapping:
    async with engine.connect() as connection:
        result = await connection.execute(
            sa.select(event_outbox.c.dispatched_at, event_outbox.c.attempts).where(
                event_outbox.c.outbox_id == outbox_id
            )
        )
        return result.mappings().one()


def test_tick_once_relays_a_real_outboxed_event_to_a_real_subscriber(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        bus = InProcessEventBus()
        try:
            received: list[Event] = []

            async def handler(event: Event) -> None:
                received.append(event)

            bus.subscribe("workflow.completed", handler)
            outbox_id = await _insert_outbox_row(engine, trace_id="trace-real")

            result = await OutboxRelay(engine, bus).tick_once(limit=100)

            assert outbox_id in result.dispatched
            assert await _wait_until(lambda: len(received) == 1)
            assert received[0].event_id == outbox_id
            assert received[0].trace_id == "trace-real"
            assert received[0].payload == {"detail": "real payload"}

            row = await _fetch_dispatch_state(engine, outbox_id=outbox_id)
            assert row["dispatched_at"] is not None
            assert row["attempts"] == 1
        finally:
            await bus.aclose()
            await engine.dispose()

    asyncio.run(_run())


def test_tick_once_never_redispatches_an_already_dispatched_row(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        bus = InProcessEventBus()
        try:
            received: list[Event] = []

            async def handler(event: Event) -> None:
                received.append(event)

            bus.subscribe("workflow.completed", handler)
            await _insert_outbox_row(engine)

            first = await OutboxRelay(engine, bus).tick_once(limit=100)
            second = await OutboxRelay(engine, bus).tick_once(limit=100)

            assert first.count == 1
            assert second.count == 0
            assert await _wait_until(lambda: len(received) == 1)
        finally:
            await bus.aclose()
            await engine.dispose()

    asyncio.run(_run())


def test_a_failed_dispatch_leaves_the_row_a_real_candidate_for_retry(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        failing_bus = _FailingEventBus()
        real_bus = InProcessEventBus()
        try:
            outbox_id = await _insert_outbox_row(engine)

            failed_result = await OutboxRelay(engine, failing_bus).tick_once(limit=100)
            assert failed_result.count == 0

            row = await _fetch_dispatch_state(engine, outbox_id=outbox_id)
            assert row["dispatched_at"] is None
            assert row["attempts"] == 1

            received: list[Event] = []

            async def handler(event: Event) -> None:
                received.append(event)

            real_bus.subscribe("workflow.completed", handler)
            retried_result = await OutboxRelay(engine, real_bus).tick_once(limit=100)

            assert outbox_id in retried_result.dispatched
            assert await _wait_until(lambda: len(received) == 1)

            row = await _fetch_dispatch_state(engine, outbox_id=outbox_id)
            assert row["dispatched_at"] is not None
            assert row["attempts"] == 2
        finally:
            await real_bus.aclose()
            await engine.dispose()

    asyncio.run(_run())


def test_tick_once_returns_empty_when_the_outbox_has_no_pending_rows(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        bus = InProcessEventBus()
        try:
            result = await OutboxRelay(engine, bus).tick_once(limit=100)
            assert result.count == 0
            assert result.dispatched == ()
        finally:
            await bus.aclose()
            await engine.dispose()

    asyncio.run(_run())
