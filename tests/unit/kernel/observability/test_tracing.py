"""Unit tests for the OpenTelemetry wiring (ADR-0017): span creation,
the structlog processor that correlates log lines to the active span,
and configure_tracing()'s idempotency.

Uses a locally-created TracerProvider (never registered as the process
global) throughout — starting a span with it still makes that span
"current" via OpenTelemetry's context API, which is exactly what
bind_otel_span_context reads, so these tests need no real exporter and
never touch or depend on the shared, once-per-process global provider
configure_tracing() installs.
"""

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Tracer

from ai_os_kernel.observability.tracing import (
    _build_span_exporter,
    bind_otel_span_context,
    configure_tracing,
    get_tracer,
)


def _isolated_tracer() -> tuple[Tracer, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer("test"), exporter


def test_get_tracer_returns_a_real_tracer() -> None:
    tracer = get_tracer("ai_os_kernel.test")

    assert tracer is not None


def test_bind_otel_span_context_adds_hex_ids_while_a_span_is_active() -> None:
    tracer, _ = _isolated_tracer()

    with tracer.start_as_current_span("test-span"):
        event_dict = bind_otel_span_context(None, "info", {"event": "hello"})

    assert set(event_dict["otelTraceID"]) <= set("0123456789abcdef")
    assert len(event_dict["otelTraceID"]) == 32
    assert set(event_dict["otelSpanID"]) <= set("0123456789abcdef")
    assert len(event_dict["otelSpanID"]) == 16


def test_bind_otel_span_context_leaves_the_event_unchanged_with_no_active_span() -> None:
    event_dict = bind_otel_span_context(None, "info", {"event": "hello"})

    assert "otelTraceID" not in event_dict
    assert "otelSpanID" not in event_dict


def test_two_spans_from_the_same_trace_share_a_trace_id_but_not_a_span_id() -> None:
    tracer, _ = _isolated_tracer()

    with tracer.start_as_current_span("parent"):
        outer = bind_otel_span_context(None, "info", {})
        with tracer.start_as_current_span("child"):
            inner = bind_otel_span_context(None, "info", {})

    assert outer["otelTraceID"] == inner["otelTraceID"]
    assert outer["otelSpanID"] != inner["otelSpanID"]


def test_configure_tracing_is_safe_to_call_more_than_once() -> None:
    configure_tracing()
    configure_tracing()  # must not raise


def test_build_span_exporter_defaults_to_console_with_no_endpoint() -> None:
    exporter = _build_span_exporter(None)

    assert isinstance(exporter, ConsoleSpanExporter)


def test_build_span_exporter_uses_otlp_with_an_endpoint() -> None:
    exporter = _build_span_exporter("http://localhost:4318")

    assert isinstance(exporter, OTLPSpanExporter)
    assert exporter._endpoint == "http://localhost:4318/v1/traces"
