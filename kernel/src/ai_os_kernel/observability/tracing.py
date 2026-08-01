"""Wires the OpenTelemetry SDK into the existing structlog +
:class:`~ai_os_kernel.observability.middleware.TraceIdMiddleware` seam
(ADR-0017), so every request produces a real span and every log line
emitted while one is active is genuinely correlated to it — not just
carrying this platform's own ``trace_id`` (see
:mod:`ai_os_kernel.observability.trace`).

**Real OTLP/HTTP export to a Collector, as of ``P01-S05-M04-T03``,**
when ``otlp_endpoint`` is configured (``PlatformConfig.otlp_endpoint``,
ADR-0017: "The Collector — not application code — decides the real
backend"). ``None`` (every environment with no Collector deployed,
including every test in this repo) keeps the console exporter — a real
OpenTelemetry SDK exporter, not a stand-in of our own, and exactly the
"backend-swappable without touching application code" guarantee
ADR-0017 makes: :func:`_build_span_exporter` is the one place this
choice is made.
"""

from __future__ import annotations

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    DEFAULT_TRACES_EXPORT_PATH,
    OTLPSpanExporter,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
    SpanExporter,
)
from opentelemetry.trace import Tracer
from structlog.typing import EventDict, WrappedLogger

# Identifies this process in every exported span's Resource attributes —
# the OpenTelemetry Semantic Conventions' own name for "which service
# produced this," not a platform-specific invention.
_SERVICE_NAME = "ai-os-kernel"


def _build_span_exporter(otlp_endpoint: str | None) -> SpanExporter:
    """The one place export target selection happens — a pure
    constructor, deliberately separate from :func:`configure_tracing`'s
    own process-wide-singleton concern, so it is directly unit-testable
    without fighting the OpenTelemetry API's "global provider set once
    per process" rule.

    ``otlp_endpoint`` is a *base* Collector URL (e.g.
    ``http://localhost:4318``); the real, standard ``v1/traces`` suffix
    (:data:`DEFAULT_TRACES_EXPORT_PATH`, the exporter's own constant,
    never re-typed here) is appended to it, the same base-plus-signal-path
    convention ``OTEL_EXPORTER_OTLP_ENDPOINT`` itself uses.
    """
    if otlp_endpoint is None:
        return ConsoleSpanExporter()
    return OTLPSpanExporter(endpoint=f"{otlp_endpoint}/{DEFAULT_TRACES_EXPORT_PATH}")


def configure_tracing(*, otlp_endpoint: str | None = None) -> None:
    """Install the process-wide ``TracerProvider``. Call once, at
    process startup (see :func:`ai_os_kernel.bootstrap.build_app`).

    Safe to call more than once: the OpenTelemetry API only allows the
    global provider to be set once per process and otherwise logs a
    warning, so this checks first — every test in this repo calls
    ``build_app()`` independently, which would otherwise emit a
    spurious warning on every call after the first.

    A real OTLP exporter batches spans (:class:`BatchSpanProcessor` —
    standard practice for network export, so a span never blocks on a
    real HTTP call) rather than exporting immediately
    (:class:`SimpleSpanProcessor`, unchanged for the console exporter,
    where immediate dev-visibility is the point).
    """
    if isinstance(trace.get_tracer_provider(), TracerProvider):
        return
    provider = TracerProvider(resource=Resource.create({"service.name": _SERVICE_NAME}))
    exporter = _build_span_exporter(otlp_endpoint)
    processor = (
        BatchSpanProcessor(exporter) if otlp_endpoint is not None else SimpleSpanProcessor(exporter)
    )
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)


def get_tracer(name: str) -> Tracer:
    """The only supported way to obtain a tracer in this codebase —
    mirrors :func:`ai_os_kernel.observability.logging.get_logger`."""
    return trace.get_tracer(name)


def bind_otel_span_context(
    logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """A structlog processor: adds the active span's own ``trace_id``/
    ``span_id`` (hex — the OTel-native identifiers, distinct from this
    platform's own ``trace_id`` field already bound by
    :class:`~ai_os_kernel.observability.middleware.TraceIdMiddleware`)
    to every log line emitted while a span is active. A log line
    emitted with no active span (for example, outside any request) is
    unchanged."""
    span_context = trace.get_current_span().get_span_context()
    if span_context.is_valid:
        event_dict["otelTraceID"] = format(span_context.trace_id, "032x")
        event_dict["otelSpanID"] = format(span_context.span_id, "016x")
    return event_dict
