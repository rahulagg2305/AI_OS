"""Observability & Audit — telemetry and correlation.

Structured logging with a per-request trace id, a real OpenTelemetry
``TracerProvider`` producing one span per request, and now a real
``MeterProvider`` counting one ``aios.http.requests`` metric per
request too (:class:`TraceIdMiddleware`) — both exported via their OTel
console exporters (:func:`configure_tracing`, :func:`configure_metrics`)
— see :mod:`ai_os_kernel.observability.tracing` /
:mod:`ai_os_kernel.observability.metrics` for why console, not OTLP,
for now. The separate hash-chained audit log is a later Stage A/C step
(ADR-0017). Telemetry and audit are deliberately different concerns —
this package is telemetry only.

See docs/03_architecture/kernel/observability.md, ADR-0017.
"""

from ai_os_kernel.observability.logging import configure_logging, get_logger
from ai_os_kernel.observability.metrics import (
    configure_metrics,
    get_http_requests_counter,
    get_meter,
)
from ai_os_kernel.observability.middleware import TraceIdMiddleware
from ai_os_kernel.observability.trace import TraceContext, generate_trace_id, get_trace_id
from ai_os_kernel.observability.tracing import configure_tracing, get_tracer

__all__ = [
    "TraceContext",
    "TraceIdMiddleware",
    "configure_logging",
    "configure_metrics",
    "configure_tracing",
    "generate_trace_id",
    "get_http_requests_counter",
    "get_logger",
    "get_meter",
    "get_trace_id",
    "get_tracer",
]
