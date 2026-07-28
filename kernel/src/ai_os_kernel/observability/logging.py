"""Structured logging configuration (ADR-0017).

Emits JSON logs with the active trace id automatically attached via
``structlog.contextvars``, and — while a span is active — the real
OpenTelemetry span's own ``trace_id``/``span_id`` too (see
:func:`ai_os_kernel.observability.tracing.bind_otel_span_context`).
Every logger is obtained through :func:`get_logger`, never
``logging.getLogger()`` directly — that is what guarantees every log
line is structured and trace-correlated.

OpenTelemetry OTLP export replaces the console span exporter configured
in :mod:`ai_os_kernel.observability.tracing` without changing any call
site (ADR-0017: "backend-swappable without touching application code").
"""

import logging
import sys

import structlog

from ai_os_kernel.observability.tracing import bind_otel_span_context


def configure_logging(log_level: str) -> None:
    """Configure stdlib logging and structlog together.

    Call once, at process startup (see
    :func:`ai_os_kernel.bootstrap.build_app`).
    """
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(stream=sys.stdout, level=level, format="%(message)s")

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            bind_otel_span_context,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """The only supported way to obtain a logger in this codebase."""
    logger: structlog.BoundLogger = structlog.get_logger(name)
    return logger
