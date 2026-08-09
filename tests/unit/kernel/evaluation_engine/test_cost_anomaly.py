"""Unit tests for the Cost Anomaly Alerting loop
(``P07-S03-M42-T02``). The real SQL detection logic
(:class:`~ai_os_kernel.evaluation_engine.cost_anomaly.SqlCostAnomalyDetector`)
already has its own real-Postgres integration tests
(``tests/integration/evaluation_engine/test_cost_anomaly.py``) — these
tests prove only the loop's own new behaviour: it runs on a real
interval, and it publishes a real `Event` the instant — and only the
instant — a check comes back anomalous.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import structlog.testing

from ai_os_kernel.evaluation_engine.cost_anomaly import (
    CostAnomalyCheckResult,
    run_cost_anomaly_check_once,
    run_periodic_cost_anomaly_check,
)
from ai_os_kernel.event_bus.bus import EventHandler, Subscription
from ai_os_kernel.event_bus.models import Event

_WHEN = datetime(2026, 7, 31, 12, 0, 0, tzinfo=UTC)


def _normal_result() -> CostAnomalyCheckResult:
    return CostAnomalyCheckResult(
        checked_at=_WHEN,
        current_hour_spend_usd=Decimal("2.000000"),
        trailing_mean_hourly_spend_usd=Decimal("1.000000"),
        is_anomalous=False,
    )


def _anomalous_result() -> CostAnomalyCheckResult:
    return CostAnomalyCheckResult(
        checked_at=_WHEN,
        current_hour_spend_usd=Decimal("10.000000"),
        trailing_mean_hourly_spend_usd=Decimal("1.000000"),
        is_anomalous=True,
    )


class _FakeCostAnomalyDetector:
    """The one real seam this loop depends on — a
    :class:`~ai_os_kernel.evaluation_engine.cost_anomaly.CostAnomalyDetector`,
    satisfied structurally, no mocking framework (ADR-0004). Mirrors
    ``test_audit_verification_job.py``'s own ``_ScheduledReader``: sets
    ``stop_event`` once it has been called ``stop_after`` times, so the
    loop's own real scheduling drives the stop condition, not a sleep
    loop in the test."""

    def __init__(
        self,
        results: list[CostAnomalyCheckResult],
        *,
        stop_event: asyncio.Event | None = None,
        stop_after: int | None = None,
    ) -> None:
        self._results = list(results)
        self._stop_event = stop_event
        self._stop_after = stop_after
        self.call_count = 0

    async def check_once(self, *, now: datetime | None = None) -> CostAnomalyCheckResult:
        result = self._results[min(self.call_count, len(self._results) - 1)]
        self.call_count += 1
        if self._stop_event is not None and self.call_count >= (self._stop_after or 0):
            self._stop_event.set()
        return result


class _FakeEventBus:
    """Records every published `Event` — this loop only ever calls
    `publish`; the other three `EventBus` methods are unused here."""

    def __init__(self) -> None:
        self.published: list[Event] = []

    async def publish(self, event: Event) -> None:
        self.published.append(event)

    def subscribe(self, event_type: str | None, handler: EventHandler) -> Subscription:
        raise NotImplementedError

    def unsubscribe(self, subscription: Subscription) -> None:
        raise NotImplementedError

    async def aclose(self) -> None:
        pass


async def test_a_normal_check_publishes_nothing_and_logs_no_alert() -> None:
    bus = _FakeEventBus()
    with structlog.testing.capture_logs() as logs:
        result = await run_cost_anomaly_check_once(
            _FakeCostAnomalyDetector([_normal_result()]), bus
        )

    assert result.is_anomalous is False
    assert bus.published == []
    events = [entry["event"] for entry in logs]
    assert "cost_anomaly.checked" in events
    assert "cost_anomaly.detected" not in events


async def test_an_anomalous_check_publishes_a_real_event_and_alerts() -> None:
    bus = _FakeEventBus()
    with structlog.testing.capture_logs() as logs:
        result = await run_cost_anomaly_check_once(
            _FakeCostAnomalyDetector([_anomalous_result()]), bus
        )

    assert result.is_anomalous is True
    assert len(bus.published) == 1
    published = bus.published[0]
    assert published.event_type == "cost.anomaly"
    assert published.payload["current_hour_spend_usd"] == "10.000000"

    alerts = [entry for entry in logs if entry["event"] == "cost_anomaly.detected"]
    assert len(alerts) == 1
    assert alerts[0]["log_level"] == "error"


async def test_the_loop_genuinely_iterates_on_a_real_schedule_and_stops_cleanly() -> None:
    """Proves the *scheduling*, not just one pass: a real ``asyncio``
    interval loop runs the check more than once before the caller
    stops it, and only the one genuinely anomalous pass publishes."""
    stop_event = asyncio.Event()
    detector = _FakeCostAnomalyDetector(
        [_normal_result(), _normal_result(), _anomalous_result()],
        stop_event=stop_event,
        stop_after=3,
    )
    bus = _FakeEventBus()

    await run_periodic_cost_anomaly_check(
        detector, bus, interval_seconds=0.01, stop_event=stop_event
    )

    assert detector.call_count >= 3
    assert len(bus.published) == 1
    assert bus.published[0].event_type == "cost.anomaly"


async def test_a_genuine_per_pass_failure_is_logged_and_never_kills_the_loop() -> None:
    class _FailingThenNormalDetector:
        def __init__(self, *, stop_event: asyncio.Event, stop_after: int) -> None:
            self._stop_event = stop_event
            self._stop_after = stop_after
            self.call_count = 0

        async def check_once(self, *, now: datetime | None = None) -> CostAnomalyCheckResult:
            self.call_count += 1
            if self.call_count >= self._stop_after:
                self._stop_event.set()
            if self.call_count == 1:
                raise RuntimeError("a genuine transient database error")
            return _normal_result()

    stop_event = asyncio.Event()
    detector = _FailingThenNormalDetector(stop_event=stop_event, stop_after=2)
    bus = _FakeEventBus()

    with structlog.testing.capture_logs() as logs:
        await run_periodic_cost_anomaly_check(
            detector, bus, interval_seconds=0.01, stop_event=stop_event
        )

    assert detector.call_count >= 2
    failures = [e for e in logs if e["event"] == "cost_anomaly.pass_failed"]
    assert len(failures) == 1
