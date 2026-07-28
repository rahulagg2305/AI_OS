"""Correlation identifiers.

Only ``trace_id`` is populated at this stage — ``workflow_id``,
``step_id``, ``agent_id``, and ``experiment_id`` are added once the
Workflow Engine exists (Stage B) and become fields it binds through the
same ``structlog.contextvars`` mechanism used here for ``trace_id``.

This is the seam OpenTelemetry attaches to later (ADR-0017): replacing
:func:`generate_trace_id`'s random hex with the active OTel span's trace
id is the only change needed when OTel instrumentation lands — no
caller of :func:`get_trace_id` changes.
"""

import uuid

import structlog
from pydantic import BaseModel


class TraceContext(BaseModel):
    """Matches the correlation fields required by
    docs/16_observability/observability_stack.md §5."""

    trace_id: str
    workflow_id: str | None = None
    step_id: str | None = None
    agent_id: str | None = None
    experiment_id: str | None = None


def generate_trace_id() -> str:
    """A random hex id, unique enough for request correlation."""
    return uuid.uuid4().hex


def get_trace_id() -> str | None:
    """The trace id bound to the current request or task, if any."""
    value = structlog.contextvars.get_contextvars().get("trace_id")
    return value if isinstance(value, str) else None
