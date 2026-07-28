"""Unit tests for TraceIdMiddleware's real OpenTelemetry span creation
and metric counting (ADR-0017) — proves the middleware genuinely
creates one span and records one ``aios.http.requests`` count per
request, both with the documented attributes.

Uses locally-created TracerProvider/MeterProvider instances (never the
process globals, substituted in via monkeypatch on the seam the
middleware itself calls through — the same "swap what the seam
returns" technique already used throughout this codebase's tests) so
this is fully isolated from configure_tracing()'s/configure_metrics()'s
once-per-process global state and needs no real exporter backend.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.metrics import Counter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader, NumberDataPoint
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Tracer

from ai_os_kernel.observability import middleware as middleware_module
from ai_os_kernel.observability.middleware import TraceIdMiddleware


def _app_with_isolated_telemetry(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[FastAPI, InMemorySpanExporter, InMemoryMetricReader]:
    span_exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    tracer: Tracer = tracer_provider.get_tracer("test")
    monkeypatch.setattr(middleware_module, "get_tracer", lambda name: tracer)

    metric_reader = InMemoryMetricReader()
    meter_provider = MeterProvider(metric_readers=[metric_reader])
    counter: Counter = meter_provider.get_meter("test").create_counter("aios.http.requests")
    monkeypatch.setattr(middleware_module, "get_http_requests_counter", lambda: counter)

    app = FastAPI()
    app.add_middleware(TraceIdMiddleware)

    @app.get("/ping")
    async def ping() -> dict[str, str]:
        return {"pong": "ok"}

    return app, span_exporter, metric_reader


def _counter_data_points(reader: InMemoryMetricReader) -> list[NumberDataPoint]:
    data = reader.get_metrics_data()
    assert data is not None
    points: list[NumberDataPoint] = []
    for resource_metrics in data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                for point in metric.data.data_points:
                    assert isinstance(point, NumberDataPoint)
                    points.append(point)
    return points


def test_a_request_produces_exactly_one_span_with_the_documented_attributes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, span_exporter, _ = _app_with_isolated_telemetry(monkeypatch)
    client = TestClient(app)

    response = client.get("/ping", headers={"X-Trace-Id": "my-trace"})

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "GET /ping"
    assert span.attributes is not None
    assert span.attributes["aios.trace_id"] == "my-trace"
    assert span.attributes["http.method"] == "GET"
    assert span.attributes["http.target"] == "/ping"
    assert span.attributes["http.status_code"] == 200
    assert response.headers["X-Trace-Id"] == "my-trace"


def test_a_generated_trace_id_is_recorded_on_the_span_when_no_header_is_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, span_exporter, _ = _app_with_isolated_telemetry(monkeypatch)
    client = TestClient(app)

    response = client.get("/ping")

    span = span_exporter.get_finished_spans()[0]
    assert span.attributes is not None
    assert span.attributes["aios.trace_id"] == response.headers["X-Trace-Id"]


def test_a_request_increments_the_http_requests_counter_with_method_and_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _, metric_reader = _app_with_isolated_telemetry(monkeypatch)
    client = TestClient(app)

    client.get("/ping")

    points = _counter_data_points(metric_reader)
    assert len(points) == 1
    point = points[0]
    assert point.attributes == {"http.method": "GET", "http.status_code": 200}
    assert point.value == 1


def test_two_requests_accumulate_on_the_same_counter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _, metric_reader = _app_with_isolated_telemetry(monkeypatch)
    client = TestClient(app)

    client.get("/ping")
    client.get("/ping")

    points = _counter_data_points(metric_reader)
    assert len(points) == 1
    assert points[0].value == 2
