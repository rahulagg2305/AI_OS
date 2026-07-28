"""Wires OpenTelemetry metrics into the same
:class:`~ai_os_kernel.observability.middleware.TraceIdMiddleware` seam
that :mod:`ai_os_kernel.observability.tracing` wires spans into
(ADR-0017) — the platform's second telemetry pillar, alongside traces.

Export is the OTel **console exporter** for now, for exactly the reason
:mod:`ai_os_kernel.observability.tracing` gives for spans: ADR-0017's
actual target is OTLP to a Collector, and none is deployed yet. The
console exporter is a real OpenTelemetry SDK exporter; swapping it for
an OTLP one later is a one-line change in :func:`configure_metrics` and
nowhere else.
"""

from __future__ import annotations

from opentelemetry import metrics
from opentelemetry.metrics import Counter, Meter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader
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


def configure_metrics() -> None:
    """Install the process-wide ``MeterProvider``. Call once, at process
    startup (see :func:`ai_os_kernel.bootstrap.build_app`).

    Safe to call more than once, for the same reason
    :func:`~ai_os_kernel.observability.tracing.configure_tracing` is:
    the OpenTelemetry API only allows the global provider to be set
    once per process and otherwise logs a warning.
    """
    if isinstance(metrics.get_meter_provider(), MeterProvider):
        return
    reader = PeriodicExportingMetricReader(ConsoleMetricExporter())
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
