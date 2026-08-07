"""The Comparison Computer (`P04-S01-M12-T06`, FR-074) — this
package's second real code (after the Metrics Collector,
`P04-S01-M12-T04`).

**Reads what the Metrics Collector already wrote — no parallel
metric-computation mechanism.** Every metric value consumed here is
exactly what `SqlMetricsCollector.collect()` already wrote to real
`evaluation.metrics` rows, joined against real `evaluation.experiment_runs`
to know which replicates share a real `variant_key`, then aggregated —
reports mean and variance per (variant, metric), never a single run's
own point value (`docs/06_capability_packs/benchmarking/overview.md`
§7: "A comparison reports mean and variance over replicates, never a
single run").

**A cache-served run is excluded from aggregates**
(`overview.md` §7, ADR-0025) — `experiment_runs.served_from_cache=True`
rows are filtered out before computing mean/variance, never silently
averaged in. Only genuinely `status='completed'` runs are included —
an incomplete run has no real, final metric values worth reporting,
and `SqlMetricsCollector.collect()` has no real caller yet to guarantee
it is only ever invoked for one (nothing in that class's own code
checks completion status itself).

**Variance is `None`, not fabricated or a crash, when fewer than 2
real data points contribute.** `statistics.variance` (sample variance,
Bessel-corrected) genuinely requires at least 2 values; reporting a
fabricated `0` would misrepresent a single-point "variance" as a real
measurement of spread, and crashing would refuse an otherwise-valid
mean. Every input/output value stays `Decimal`, matching
`evaluation.metrics.metric_value`'s own real column type
(`NUMERIC(20,6)`) — never `float`, avoiding a real, silent precision
loss this codebase's own configured, exact cost/metric data does not
have today.

**No real production caller yet** — the same, disclosed limit every
real Benchmarking Pack/Evaluation Engine component built this session
carries: nothing in production creates a real `experiments`/
`experiment_runs` row today (Module 34 has no `manifest.yaml`, no
submission path). Proven end to end against a real Postgres with
real, hand-seeded fixtures — the identical "build real, wire later"
precedent already established for the Gate Registry, the Metrics
Collector, and every Benchmarking Pack module this session.
"""

from __future__ import annotations

import statistics
from decimal import Decimal
from typing import Protocol

import sqlalchemy as sa
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.persistence.evaluation_schema import experiment_runs, metrics

_COMPLETED_STATUS = "completed"


class MetricComparison(BaseModel):
    """One metric's own real mean/variance across a variant's own
    real, non-cache-served, completed replicates."""

    metric_name: str
    unit: str
    replicate_count: int
    mean: Decimal
    variance: Decimal | None


class VariantComparison(BaseModel):
    """One variant's own real comparison — every metric name observed
    across its own real replicates."""

    variant_key: str
    metrics: list[MetricComparison]


class ExperimentComparison(BaseModel):
    """The real, complete comparison for one experiment — this
    ticket's own "Output": per-variant, per-metric mean and variance,
    never a single run's own point value."""

    experiment_id: str
    variants: list[VariantComparison]


class ComparisonComputer(Protocol):
    """Computes one experiment's own real comparison — the seam a
    fake implementation substitutes in unit tests (ADR-0004:
    interface-driven, configuration over code), the identical shape
    `~ai_os_kernel.evaluation_engine.metrics_collector.MetricsCollector`
    already establishes."""

    async def compute(self, *, experiment_id: str) -> ExperimentComparison: ...


class SqlComparisonComputer:
    """The only implementation at this stage: SQLAlchemy 2.0 Core
    against Postgres (ADR-0011)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def compute(self, *, experiment_id: str) -> ExperimentComparison:
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        sa.select(
                            experiment_runs.c.variant_key,
                            metrics.c.metric_name,
                            metrics.c.metric_value,
                            metrics.c.unit,
                        )
                        .select_from(
                            experiment_runs.join(
                                metrics, metrics.c.run_id == experiment_runs.c.run_id
                            )
                        )
                        .where(
                            experiment_runs.c.experiment_id == experiment_id,
                            experiment_runs.c.served_from_cache.is_(False),
                            experiment_runs.c.status == _COMPLETED_STATUS,
                        )
                    )
                )
                .mappings()
                .all()
            )

        by_variant: dict[str, dict[str, list[tuple[Decimal, str]]]] = {}
        for row in rows:
            variant_metrics = by_variant.setdefault(row["variant_key"], {})
            values = variant_metrics.setdefault(row["metric_name"], [])
            values.append((row["metric_value"], row["unit"]))

        variant_comparisons: list[VariantComparison] = []
        for variant_key in sorted(by_variant):
            metric_comparisons: list[MetricComparison] = []
            for metric_name in sorted(by_variant[variant_key]):
                entries = by_variant[variant_key][metric_name]
                metric_values = [value for value, _ in entries]
                unit = entries[0][1]
                metric_comparisons.append(
                    MetricComparison(
                        metric_name=metric_name,
                        unit=unit,
                        replicate_count=len(metric_values),
                        mean=statistics.mean(metric_values),
                        variance=(
                            statistics.variance(metric_values) if len(metric_values) >= 2 else None
                        ),
                    )
                )
            variant_comparisons.append(
                VariantComparison(variant_key=variant_key, metrics=metric_comparisons)
            )

        return ExperimentComparison(experiment_id=experiment_id, variants=variant_comparisons)
