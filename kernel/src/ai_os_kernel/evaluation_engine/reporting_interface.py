"""The Reporting Interface (`P04-S01-M12-T08`) — this package's third
real code (after the Metrics Collector, `P04-S01-M12-T04`, and the
Comparison Computer, `P04-S01-M12-T06`/`T07`).

**Exposes what the Comparison Computer already computed for real
consumption — no parallel mechanism.** This ticket's own literal
Input, "Computed comparisons," is exactly `ComparisonComputer.compute()`'s
own real `ExperimentComparison` — this module never recomputes a mean,
a variance, or an exclusion; it only makes an already-computed result
genuinely *queryable*, this ticket's own literal Output.

**`ComparisonReport` is a pure, synchronous wrapper — the comparison
it wraps must already be computed.** `EvaluationReportingInterface`
is the thin, async seam that actually calls the real
`ComparisonComputer` and wraps its result, matching the shape every
real caller will genuinely need (compute, then query) without forcing
every query call site to also own a database connection.

**`compare_by_metric` is the one genuinely new capability here, not
merely a lookup convenience.** `ExperimentComparison.variants` is
already queryable by variant (`get_variant`) and by
variant-then-metric (`get_metric`) with nothing more than a loop a
caller could write themselves — but `docs/06_capability_packs/benchmarking/overview.md`
§4's own "Comparison Report" definition is explicitly cross-variant
("shows how different models performed... across quality, cost,
performance, and process metrics"), which the raw, per-variant-first
`ExperimentComparison` shape does not directly support: answering "how
did every variant do on metric X" today means iterating every
variant and searching its own metrics list. `compare_by_metric` does
that pivot once, for real, so no future caller (a dashboard route, a
CLI, the Benchmarking Pack's own future reporting) has to reimplement
it.

**No real production caller yet** — the same, disclosed limit every
real Evaluation Engine/Benchmarking Pack component built this session
carries (Module 34 has no `manifest.yaml`, no submission path, so no
real `experiments`/`experiment_runs` row exists in production today).
Proven end to end against a real, computed `ExperimentComparison`.
"""

from __future__ import annotations

from typing import Protocol

from ai_os_kernel.evaluation_engine.comparison_computer import (
    ComparisonComputer,
    ExperimentComparison,
    MetricComparison,
    VariantComparison,
)


class ComparisonReport:
    """A real, queryable wrapper around one real, already-computed
    `ExperimentComparison` — this ticket's own "Output." Pure and
    synchronous: everything it exposes was already computed by the
    real `ComparisonComputer` before construction."""

    def __init__(self, comparison: ExperimentComparison) -> None:
        self._comparison = comparison

    @property
    def experiment_id(self) -> str:
        return self._comparison.experiment_id

    def variant_keys(self) -> list[str]:
        """Every real variant this report has data for, in the same
        order `ComparisonComputer.compute()` already produced (sorted
        `variant_key`)."""
        return [variant.variant_key for variant in self._comparison.variants]

    def get_variant(self, variant_key: str) -> VariantComparison | None:
        """One variant's own real comparison, or `None` if this
        report has no data for it — never a `KeyError` a caller must
        guard against separately."""
        return next((v for v in self._comparison.variants if v.variant_key == variant_key), None)

    def get_metric(self, *, variant_key: str, metric_name: str) -> MetricComparison | None:
        """One variant's own real comparison for one real metric, or
        `None` if either the variant or the metric has no data."""
        variant = self.get_variant(variant_key)
        if variant is None:
            return None
        return next((m for m in variant.metrics if m.metric_name == metric_name), None)

    def compare_by_metric(self, metric_name: str) -> dict[str, MetricComparison]:
        """Every real variant's own comparison for one real metric,
        keyed by `variant_key` — the real, cross-variant "how did
        every variant do on this metric" view this module's own
        docstring explains is genuinely new, not a lookup convenience.
        A variant that reports no data for this metric name is simply
        absent from the result, never a fabricated entry."""
        result: dict[str, MetricComparison] = {}
        for variant in self._comparison.variants:
            metric = next((m for m in variant.metrics if m.metric_name == metric_name), None)
            if metric is not None:
                result[variant.variant_key] = metric
        return result


class ReportingInterface(Protocol):
    """Exposes one experiment's own real, computed comparison as a
    real, queryable report — the seam a fake implementation
    substitutes in unit tests (ADR-0004: interface-driven,
    configuration over code)."""

    async def get_report(self, *, experiment_id: str) -> ComparisonReport: ...


class EvaluationReportingInterface:
    """The only implementation at this stage: composes the real,
    injected `ComparisonComputer` — never a second, parallel way to
    compute a mean or a variance."""

    def __init__(self, comparison_computer: ComparisonComputer) -> None:
        self._comparison_computer = comparison_computer

    async def get_report(self, *, experiment_id: str) -> ComparisonReport:
        comparison = await self._comparison_computer.compute(experiment_id=experiment_id)
        return ComparisonReport(comparison)
