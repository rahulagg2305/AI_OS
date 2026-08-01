"""Wires OpenTelemetry metrics into the same
:class:`~ai_os_kernel.observability.middleware.TraceIdMiddleware` seam
that :mod:`ai_os_kernel.observability.tracing` wires spans into
(ADR-0017) — the platform's second telemetry pillar, alongside traces.

**Real OTLP/HTTP export to a Collector, as of ``P01-S05-M04-T03``,**
when ``otlp_endpoint`` is configured — the identical choice
:mod:`ai_os_kernel.observability.tracing` makes for spans, for the
identical reason. ``None`` (every environment with no Collector
deployed, including every test in this repo) keeps the console
exporter. :func:`_build_metric_exporter` is the one place this choice
is made.
"""

from __future__ import annotations

from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
    DEFAULT_METRICS_EXPORT_PATH,
    OTLPMetricExporter,
)
from opentelemetry.metrics import Counter, Meter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    ConsoleMetricExporter,
    MetricExporter,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import Resource

# Same Resource identity as configure_tracing() — both are the same
# process, and Resource attributes are how a backend groups every
# signal (traces, metrics, logs) back to the service that produced them.
_SERVICE_NAME = "ai-os-kernel"

# observability_stack.md §3.1: "aios.<subsystem>.<metric>, following
# OpenTelemetry semantic conventions where they exist." "requests" has
# no existing OTel semantic-convention name to follow, so this is the
# platform's own metric, named per that same convention.
_HTTP_REQUESTS_COUNTER_NAME = "aios.http.requests"

_http_requests_counter: Counter | None = None


def _build_metric_exporter(otlp_endpoint: str | None) -> MetricExporter:
    """The one place export target selection happens — a pure
    constructor, deliberately separate from :func:`configure_metrics`'s
    own process-wide-singleton concern, so it is directly unit-testable
    without fighting the OpenTelemetry API's "global provider set once
    per process" rule. Mirrors
    :func:`~ai_os_kernel.observability.tracing._build_span_exporter`
    exactly."""
    if otlp_endpoint is None:
        return ConsoleMetricExporter()
    return OTLPMetricExporter(endpoint=f"{otlp_endpoint}/{DEFAULT_METRICS_EXPORT_PATH}")


def configure_metrics(*, otlp_endpoint: str | None = None) -> None:
    """Install the process-wide ``MeterProvider``. Call once, at process
    startup (see :func:`ai_os_kernel.bootstrap.build_app`).

    Safe to call more than once, for the same reason
    :func:`~ai_os_kernel.observability.tracing.configure_tracing` is:
    the OpenTelemetry API only allows the global provider to be set
    once per process and otherwise logs a warning.
    """
    if isinstance(metrics.get_meter_provider(), MeterProvider):
        return
    reader = PeriodicExportingMetricReader(_build_metric_exporter(otlp_endpoint))
    provider = MeterProvider(
        resource=Resource.create({"service.name": _SERVICE_NAME}),
        metric_readers=[reader],
    )
    metrics.set_meter_provider(provider)


def get_meter(name: str) -> Meter:
    """The only supported way to obtain a meter in this codebase —
    mirrors :func:`ai_os_kernel.observability.tracing.get_tracer`."""
    return metrics.get_meter(name)


def get_http_requests_counter() -> Counter:
    """The ``aios.http.requests`` counter, incremented once per request
    by :class:`~ai_os_kernel.observability.middleware.TraceIdMiddleware`.

    Created once and cached: instruments are meant to be created a
    single time and reused, not re-created on every increment.
    Configures metrics first if nothing has, so this is safe to call
    regardless of whether :func:`configure_metrics` has already run.
    """
    global _http_requests_counter
    if _http_requests_counter is None:
        configure_metrics()
        _http_requests_counter = get_meter(__name__).create_counter(
            _HTTP_REQUESTS_COUNTER_NAME,
            unit="{request}",
            description="Number of HTTP requests handled by the Kernel API.",
        )
    return _http_requests_counter
