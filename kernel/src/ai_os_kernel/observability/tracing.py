"""Wires the OpenTelemetry SDK into the existing structlog +
:class:`~ai_os_kernel.observability.middleware.TraceIdMiddleware` seam
(ADR-0017), so every request produces a real span and every log line
emitted while one is active is genuinely correlated to it — not just
carrying this platform's own ``trace_id`` (see
:mod:`ai_os_kernel.observability.trace`).

Export is the OTel **console exporter** for now. ADR-0017's actual
target is OTLP to a Collector, which is what decides the real backend —
but no Collector is deployed yet (no Compose observability profile
exists — docs/19_roadmap/implementation_status.md). The console
exporter is a real OpenTelemetry SDK exporter, not a stand-in of our
own; swapping it for an OTLP exporter later is a one-line change in
:func:`configure_tracing` and nowhere else, exactly the
"backend-swappable without touching application code" guarantee
ADR-0017 makes.
"""

from __future__ import annotations

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
from opentelemetry.trace import Tracer
from structlog.typing import EventDict, WrappedLogger

# Identifies this process in every exported span's Resource attributes —
# the OpenTelemetry Semantic Conventions' own name for "which service
# produced this," not a platform-specific invention.
_SERVICE_NAME = "ai-os-kernel"


def configure_tracing() -> None:
    """Install the process-wide ``TracerProvider``. Call once, at
    process startup (see :func:`ai_os_kernel.bootstrap.build_app`).

    Safe to call more than once: the OpenTelemetry API only allows the
    global provider to be set once per process and otherwise logs a
    warning, so this checks first — every test in this repo calls
    ``build_app()`` independently, which would otherwise emit a
    spurious warning on every call after the first.
    """
    if isinstance(trace.get_tracer_provider(), TracerProvider):
        return
    provider = TracerProvider(resource=Resource.create({"service.name": _SERVICE_NAME}))
    provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
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
