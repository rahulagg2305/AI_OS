"""Unit tests for the OpenTelemetry metrics wiring (ADR-0017):
get_meter()/get_http_requests_counter() return real instruments, the
counter is created once and reused, and configure_metrics() is
idempotent. Counting behaviour itself (does an increment actually show
up in exported data) is proven end-to-end through the middleware in
test_middleware.py, with an isolated MeterProvider — this file covers
what's meaningfully testable without touching the process-global
provider these functions install.
"""

from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.metrics import Counter, Meter
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter

from ai_os_kernel.observability.metrics import (
    _build_metric_exporter,
    configure_metrics,
    get_http_requests_counter,
    get_meter,
)


def test_get_meter_returns_a_real_meter() -> None:
    meter = get_meter("ai_os_kernel.test")

    assert isinstance(meter, Meter)


def test_get_http_requests_counter_returns_a_real_counter() -> None:
    counter = get_http_requests_counter()

    assert isinstance(counter, Counter)


def test_get_http_requests_counter_is_created_once_and_reused() -> None:
    first = get_http_requests_counter()
    second = get_http_requests_counter()

    assert first is second


def test_configure_metrics_is_safe_to_call_more_than_once() -> None:
    configure_metrics()
    configure_metrics()  # must not raise


def test_build_metric_exporter_defaults_to_console_with_no_endpoint() -> None:
    exporter = _build_metric_exporter(None)

    assert isinstance(exporter, ConsoleMetricExporter)


def test_build_metric_exporter_uses_otlp_with_an_endpoint() -> None:
    exporter = _build_metric_exporter("http://localhost:4318")

    assert isinstance(exporter, OTLPMetricExporter)
    assert exporter._endpoint == "http://localhost:4318/v1/metrics"
