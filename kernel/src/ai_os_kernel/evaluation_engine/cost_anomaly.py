"""Cost Anomaly Alerting (`P07-S03-M42-T02`, NFR-045: "Fires within 5
minutes when hourly spend exceeds 3x the trailing 7-day hourly mean").

**Real cost telemetry, not a synthetic feed** — reads
`evaluation.llm_calls` directly, the same table
:mod:`ai_os_kernel.evaluation_engine.cost_and_quality_views` reads.
That module's own docstring disclosed this table carried no timestamp
column at all, so "hourly spend" could not be computed; this ticket's
own investigation confirmed that gap and added `created_at`
(`kernel/alembic/versions/0035_llm_calls_created_at.py`) — the real,
minimal, additive fix, not an approximation via
`workflow_instances.created_at` (which would be wrong whenever a
workflow's own calls span more than the alerting window).

**Trailing mean, not a rolling per-hour average.** NFR-045's own
wording — "3x the trailing 7-day hourly mean" — reads naturally as
"total spend over the trailing window, divided by the number of hours
in that window," not an average of only the hours that happened to
have activity (which would overstate the mean whenever real usage is
bursty, exactly the pattern an anomaly detector must not be blind to).
`COST_ANOMALY_TRAILING_WINDOW_HOURS` (168, real: 24 x 7) is the fixed
divisor.

**No real trailing history means no fire, honest, not a fabricated
certainty.** A ratio against a zero baseline is undefined, not
"infinitely anomalous" — the same "never fabricate; disclose the
empty case" precedent
:class:`~ai_os_kernel.evaluation_engine.comparison_computer.
SqlComparisonComputer` already establishes for `variance` under two
replicates.

**Alerts through the real, already-built Notification Service, not a
new delivery mechanism.** `run_periodic_cost_anomaly_check` publishes
a real `Event(event_type="cost.anomaly", ...)` to the real `EventBus`
(`ai_os_kernel.bootstrap`'s own `app.state.event_bus`, running since
before this step but never wired to any real producer — the
identical, already-disclosed gap `notification/service.py`'s own
docstring names). `NotificationService` classifies it into a new,
fourth real category (`cost_anomaly`) and delivers it through the real
`WebhookChannel`, wired into `_lifespan` for the first time by this
step alongside this loop.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Protocol

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.event_bus.bus import EventBus
from ai_os_kernel.event_bus.models import Event
from ai_os_kernel.observability.logging import get_logger
from ai_os_kernel.persistence.evaluation_schema import llm_calls

logger = get_logger(__name__)

# NFR-045's own literal numbers, not guessed.
COST_ANOMALY_THRESHOLD_MULTIPLIER = Decimal("3")
COST_ANOMALY_TRAILING_WINDOW_HOURS = 24 * 7

# Well under half of NFR-045's own 5-minute detection SLA, leaving a
# full check's worth of margin for one slow pass — the identical
# "frequent enough to meet the SLA, not scanning constantly" reasoning
# `AUDIT_CHAIN_VERIFICATION_INTERVAL_SECONDS`'s own comment already
# gives for its unrelated 300-second interval.
COST_ANOMALY_CHECK_INTERVAL_SECONDS = 120.0

# The real, published Event's own event_type — the identical
# `"<category>.<verb>"` convention `notification/service.py`'s own
# `_APPROVAL_EVENT_TYPE_PREFIX`/`_FAILURE_EVENT_TYPE` already establish.
COST_ANOMALY_EVENT_TYPE = "cost.anomaly"
COST_ANOMALY_EVENT_SOURCE = "evaluation_engine.cost_anomaly"


@dataclass(frozen=True)
class CostAnomalyCheckResult:
    """One real check's own real result — always returned, whether or
    not it was anomalous, the same "always report, not just on the
    interesting case" shape `ChainVerificationResult` already
    establishes for the Audit Chain Verification job."""

    checked_at: datetime
    current_hour_spend_usd: Decimal
    trailing_mean_hourly_spend_usd: Decimal | None
    is_anomalous: bool


class CostAnomalyDetector(Protocol):
    """The seam a fake implementation substitutes in unit tests
    (ADR-0004: interface-driven, configuration over code)."""

    async def check_once(self, *, now: datetime | None = None) -> CostAnomalyCheckResult: ...


class SqlCostAnomalyDetector:
    """The only implementation of :class:`CostAnomalyDetector` at this
    stage: SQLAlchemy 2.0 Core against Postgres (ADR-0011)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def check_once(self, *, now: datetime | None = None) -> CostAnomalyCheckResult:
        # `now` exists only so a test can assert against a real,
        # deterministic clock instead of racing `datetime.now(UTC)`
        # against however long a real Postgres round-trip takes — the
        # identical "test-only override, never a second policy
        # decision" shape `PlatformConfig`'s own interval-override
        # fields already establish. The real periodic loop below never
        # passes it.
        if now is None:
            now = datetime.now(UTC)
        # A sliding trailing-1-hour window ending now, not a calendar-hour
        # boundary — this loop checks every `COST_ANOMALY_CHECK_INTERVAL_SECONDS`,
        # so "hourly spend" must mean "spend over the last real hour," not
        # "spend since the top of the wall-clock hour" (which would make
        # the very first minutes after each hour boundary spuriously look
        # anomaly-free regardless of real spend).
        current_window_start = now - timedelta(hours=1)
        trailing_window_start = current_window_start - timedelta(
            hours=COST_ANOMALY_TRAILING_WINDOW_HOURS
        )

        async with self._engine.connect() as connection:
            current_hour_spend = (
                await connection.execute(
                    sa.select(sa.func.coalesce(sa.func.sum(llm_calls.c.cost_usd), 0)).where(
                        llm_calls.c.created_at >= current_window_start,
                        llm_calls.c.created_at < now,
                    )
                )
            ).scalar_one()
            trailing_window_spend = (
                await connection.execute(
                    sa.select(sa.func.coalesce(sa.func.sum(llm_calls.c.cost_usd), 0)).where(
                        llm_calls.c.created_at >= trailing_window_start,
                        llm_calls.c.created_at < current_window_start,
                    )
                )
            ).scalar_one()

        trailing_mean = trailing_window_spend / COST_ANOMALY_TRAILING_WINDOW_HOURS
        is_anomalous = (
            trailing_mean > 0
            and current_hour_spend > COST_ANOMALY_THRESHOLD_MULTIPLIER * trailing_mean
        )
        return CostAnomalyCheckResult(
            checked_at=now,
            current_hour_spend_usd=current_hour_spend,
            trailing_mean_hourly_spend_usd=trailing_mean if trailing_mean > 0 else None,
            is_anomalous=is_anomalous,
        )


async def run_cost_anomaly_check_once(
    detector: CostAnomalyDetector, event_bus: EventBus
) -> CostAnomalyCheckResult:
    """One real check, always logged; a real `Event` is published only
    when genuinely anomalous — the identical "always log, alert only on
    the real condition" shape
    `run_audit_chain_verification_once` already establishes."""
    result = await detector.check_once()
    if result.is_anomalous:
        logger.error(
            "cost_anomaly.detected",
            current_hour_spend_usd=str(result.current_hour_spend_usd),
            trailing_mean_hourly_spend_usd=str(result.trailing_mean_hourly_spend_usd),
            threshold_multiplier=str(COST_ANOMALY_THRESHOLD_MULTIPLIER),
        )
        await event_bus.publish(
            Event(
                event_type=COST_ANOMALY_EVENT_TYPE,
                source=COST_ANOMALY_EVENT_SOURCE,
                payload={
                    "current_hour_spend_usd": str(result.current_hour_spend_usd),
                    "trailing_mean_hourly_spend_usd": str(result.trailing_mean_hourly_spend_usd),
                    "threshold_multiplier": str(COST_ANOMALY_THRESHOLD_MULTIPLIER),
                },
            )
        )
    else:
        logger.info(
            "cost_anomaly.checked",
            current_hour_spend_usd=str(result.current_hour_spend_usd),
            trailing_mean_hourly_spend_usd=(
                str(result.trailing_mean_hourly_spend_usd)
                if result.trailing_mean_hourly_spend_usd is not None
                else None
            ),
        )
    return result


async def run_periodic_cost_anomaly_check(
    detector: CostAnomalyDetector,
    event_bus: EventBus,
    *,
    interval_seconds: float,
    stop_event: asyncio.Event,
) -> None:
    """Runs :func:`run_cost_anomaly_check_once` every `interval_seconds`
    until `stop_event` is set — the identical loop shape
    `run_periodic_audit_chain_verification` already establishes,
    including per-pass resilience: a genuine transient failure (a real
    database error) is logged and never kills this loop."""
    while not stop_event.is_set():
        try:
            await run_cost_anomaly_check_once(detector, event_bus)
        except Exception as exc:  # noqa: BLE001 -- a genuine per-pass failure must never kill the loop
            logger.error("cost_anomaly.pass_failed", error=str(exc))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
