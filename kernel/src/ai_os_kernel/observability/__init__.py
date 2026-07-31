"""Observability & Audit — telemetry, correlation, and audit.

Structured logging with a per-request trace id, a real OpenTelemetry
``TracerProvider`` producing one span per request, and a real
``MeterProvider`` counting one ``aios.http.requests`` metric per
request too (:class:`TraceIdMiddleware`) — both exported via their OTel
console exporters (:func:`configure_tracing`, :func:`configure_metrics`)
— see :mod:`ai_os_kernel.observability.tracing` /
:mod:`ai_os_kernel.observability.metrics` for why console, not OTLP,
for now.

**The hash-chained audit log** (added 2026-07-31, ``P01-S05-M04-T05``)
is a genuinely separate concern from the telemetry above — tamper-
evident and never sampled (ADR-0017) — kept in its own module,
:mod:`ai_os_kernel.observability.audit`. :class:`SqlAuditLogWriter`
writes ``governance.audit_log`` rows whose ``row_hash`` chains to the
previous row's; :func:`~ai_os_kernel.observability.audit.verify_chain`
detects a row modified after it was written. The scheduled job that
runs verification on an interval and alerts is separate, later work.

See docs/03_architecture/kernel/observability.md, ADR-0017.
"""

from ai_os_kernel.observability.audit import (
    AuditLogRecord,
    AuditLogWriter,
    AuditOutcome,
    ChainVerificationResult,
    SqlAuditLogWriter,
    verify_chain,
)
from ai_os_kernel.observability.errors import AuditLogError
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
    "AuditLogError",
    "AuditLogRecord",
    "AuditLogWriter",
    "AuditOutcome",
    "ChainVerificationResult",
    "SqlAuditLogWriter",
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
    "verify_chain",
]
