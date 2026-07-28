"""ASGI middleware assigning a trace id to every request, wrapping it
in a real OpenTelemetry span, and counting it (ADR-0017).

Every log line emitted while handling a request automatically carries
this platform's own trace id (see
:mod:`ai_os_kernel.observability.logging`), and it is echoed back as
the ``X-Trace-Id`` response header so a caller can correlate its own
logs with ours. The request is also wrapped in a genuine OTel span —
distinct from ``X-Trace-Id``, which is an opaque, caller-supplied-or-
generated correlation token with no format requirement, unlike an OTel
trace id — so this middleware carries both without conflating them.
Finally, the request increments the ``aios.http.requests`` counter
(:mod:`ai_os_kernel.observability.metrics`) — the platform's second
telemetry pillar, alongside the span.
"""

from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from ai_os_kernel.observability.metrics import get_http_requests_counter
from ai_os_kernel.observability.trace import generate_trace_id
from ai_os_kernel.observability.tracing import get_tracer

_TRACE_ID_HEADER = "X-Trace-Id"


class TraceIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        trace_id = request.headers.get(_TRACE_ID_HEADER.lower()) or generate_trace_id()
        structlog.contextvars.bind_contextvars(trace_id=trace_id)
        try:
            with get_tracer(__name__).start_as_current_span(
                f"{request.method} {request.url.path}",
                attributes={
                    "aios.trace_id": trace_id,
                    "http.method": request.method,
                    "http.target": request.url.path,
                },
            ) as span:
                # Exceptions raised by call_next are recorded on the span
                # and re-raised by the context manager itself — no extra
                # handling needed here. The request is only counted once
                # a response actually exists (below), so an unhandled
                # exception here is not miscounted against some status.
                response = await call_next(request)
                span.set_attribute("http.status_code", response.status_code)
                get_http_requests_counter().add(
                    1,
                    attributes={
                        "http.method": request.method,
                        "http.status_code": response.status_code,
                    },
                )
        finally:
            structlog.contextvars.clear_contextvars()
        response.headers[_TRACE_ID_HEADER] = trace_id
        return response
