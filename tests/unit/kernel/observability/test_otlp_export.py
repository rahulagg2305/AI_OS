"""Real, end-to-end proof of OTLP/HTTP export (ADR-0017,
``P01-S05-M04-T03``): a real ``OTLPSpanExporter``/``OTLPMetricExporter``
(the exact objects :func:`~ai_os_kernel.observability.tracing._build_span_exporter`/
:func:`~ai_os_kernel.observability.metrics._build_metric_exporter`
construct) genuinely send real, parseable OTLP protobuf over real HTTP
to a real receiver — not an assertion that configuration merely exists.

Uses a real, in-process HTTP server (``http.server``, a real socket, a
real background thread) as the receiver, not a mock of ``requests`` or
of the exporter itself — the only thing standing in for a real
Collector is which *backend* receives the data, exactly the part
ADR-0017 says application code should never need to know about.

Deliberately never touches ``trace.set_tracer_provider()``/
``metrics.set_meter_provider()`` (the process-wide singletons
``configure_tracing()``/``configure_metrics()`` install) — the
OpenTelemetry API only allows those to be set once per process, and
many other tests in this suite already set one. Each test here builds
its own, fully isolated ``TracerProvider``/``MeterProvider`` bound
directly to the real exporter under test instead, the same isolation
``test_tracing.py``'s own ``_isolated_tracer`` already establishes.
"""

from __future__ import annotations

import threading
from collections.abc import Generator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,
    ExportMetricsServiceResponse,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from ai_os_kernel.observability.metrics import _build_metric_exporter
from ai_os_kernel.observability.tracing import _build_span_exporter


class _RecordingOtlpServer(ThreadingHTTPServer):
    """Holds the real, raw protobuf bodies this test's own receiver
    genuinely received — populated by ``_RecordingOtlpHandler``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.trace_request_bodies: list[bytes] = []
        self.metric_request_bodies: list[bytes] = []


class _RecordingOtlpHandler(BaseHTTPRequestHandler):
    server: _RecordingOtlpServer  # narrows the inherited Any-typed attribute

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        if self.path == "/v1/traces":
            self.server.trace_request_bodies.append(body)
            response_body = ExportTraceServiceResponse().SerializeToString()
        elif self.path == "/v1/metrics":
            self.server.metric_request_bodies.append(body)
            response_body = ExportMetricsServiceResponse().SerializeToString()
        else:
            self.send_response(404)
            self.end_headers()
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/x-protobuf")
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - stdlib signature
        pass  # silence default per-request stderr noise


@pytest.fixture
def otlp_receiver() -> Generator[_RecordingOtlpServer, None, None]:
    """A real HTTP server on an OS-assigned loopback port — a real
    socket and a real background thread, not a mock."""
    server = _RecordingOtlpServer(("127.0.0.1", 0), _RecordingOtlpHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_a_real_span_genuinely_reaches_a_real_otlp_receiver(
    otlp_receiver: _RecordingOtlpServer,
) -> None:
    endpoint = f"http://127.0.0.1:{otlp_receiver.server_port}"
    exporter = _build_span_exporter(endpoint)
    provider = TracerProvider(resource=Resource.create({"service.name": "test-service"}))
    provider.add_span_processor(BatchSpanProcessor(exporter))

    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("real-otlp-span"):
        pass
    assert provider.force_flush(timeout_millis=5000)

    assert len(otlp_receiver.trace_request_bodies) == 1
    request = ExportTraceServiceRequest()
    request.ParseFromString(otlp_receiver.trace_request_bodies[0])

    span_names = [
        span.name
        for resource_spans in request.resource_spans
        for scope_spans in resource_spans.scope_spans
        for span in scope_spans.spans
    ]
    assert span_names == ["real-otlp-span"]

    service_names = [
        attr.value.string_value
        for resource_spans in request.resource_spans
        for attr in resource_spans.resource.attributes
        if attr.key == "service.name"
    ]
    assert service_names == ["test-service"]

    provider.shutdown()


def test_a_real_metric_genuinely_reaches_a_real_otlp_receiver(
    otlp_receiver: _RecordingOtlpServer,
) -> None:
    endpoint = f"http://127.0.0.1:{otlp_receiver.server_port}"
    exporter = _build_metric_exporter(endpoint)
    # A long export_interval_millis -- this test drives the export
    # itself via force_flush(), never waiting on the real periodic
    # schedule, the identical "deterministic, no real sleep" reasoning
    # this codebase already applies to every other interval-driven loop.
    reader = PeriodicExportingMetricReader(exporter, export_interval_millis=3_600_000)
    provider = MeterProvider(
        resource=Resource.create({"service.name": "test-service"}), metric_readers=[reader]
    )

    counter = provider.get_meter("test").create_counter("test.otlp.counter")
    counter.add(1)
    assert provider.force_flush(timeout_millis=5000)

    assert len(otlp_receiver.metric_request_bodies) == 1
    request = ExportMetricsServiceRequest()
    request.ParseFromString(otlp_receiver.metric_request_bodies[0])

    metric_names = [
        metric.name
        for resource_metrics in request.resource_metrics
        for scope_metrics in resource_metrics.scope_metrics
        for metric in scope_metrics.metrics
    ]
    assert metric_names == ["test.otlp.counter"]

    data_points = [
        point
        for resource_metrics in request.resource_metrics
        for scope_metrics in resource_metrics.scope_metrics
        for metric in scope_metrics.metrics
        for point in metric.sum.data_points
    ]
    assert len(data_points) == 1
    assert data_points[0].as_int == 1

    provider.shutdown()


def test_no_receiver_at_the_endpoint_fails_the_export_without_raising(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A real, distinguishing negative case: nothing is listening on
    this port, so the real HTTP call genuinely fails -- logged by the
    exporter's own real retry/error handling rather than raising out of
    force_flush() (whose own return value reports only whether the
    flush attempt completed within the timeout, not whether the
    underlying export succeeded)."""
    exporter = _build_span_exporter("http://127.0.0.1:1")  # port 1: nothing ever listens here
    provider = TracerProvider(resource=Resource.create({"service.name": "test-service"}))
    provider.add_span_processor(BatchSpanProcessor(exporter))

    with provider.get_tracer("test").start_as_current_span("unreachable"):
        pass

    with caplog.at_level("ERROR"):
        provider.force_flush(timeout_millis=5000)  # must not raise

    assert "Failed to export span batch" in caplog.text

    provider.shutdown()
