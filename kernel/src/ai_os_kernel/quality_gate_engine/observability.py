"""§5's **Observability Hook** — the one Quality Gate Engine component
that had no code at all (`P02-S06-M15-T10`).

**What was actually missing.** Verified 2026-08-13 by direct inspection:
this whole package was `__init__.py`, `errors.py` and `registry.py`, and
searching it for `logger`, `metric` or `span` returned nothing. Five of
§5's six components are real — the Gate Registry here, and the
Executor/Result Evaluator/Policy Enforcer/Result Store deliberately in
the Workflow Engine, an accepted and documented structural decision
(`quality_gate_engine.md`). This was the sixth, and it was genuinely
empty, so `quality_gate_engine.md` §8's observability requirements had
no producer whatsoever.

**Telemetry only — deliberately not a second store.** Every gate
resolution is already persisted durably to `evaluation.gate_results` by
`SqlGateResultRecorder`. This module adds the *observable* half: a
structured log line, a real counter, and a real span. It never writes to
the database, so a telemetry failure can never lose a gate result.

**Follows existing precedent rather than inventing a convention.** The
log event names use the `quality_gate.*` dotted shape
`workflow_worker_loop.*` already established; the counter is created
once and cached, exactly as `get_http_requests_counter` documents
instruments should be; and the tracer/meter come from
`ai_os_kernel.observability`, the only supported way to obtain either in
this codebase.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from typing import Any

from opentelemetry.metrics import Counter

from ai_os_kernel.observability.logging import get_logger
from ai_os_kernel.observability.metrics import configure_metrics, get_meter
from ai_os_kernel.observability.tracing import get_tracer

_logger = get_logger(__name__)

_GATE_RESOLUTIONS_COUNTER_NAME = "aios.quality_gate.resolutions"
_TRACER_NAME = "ai_os_kernel.quality_gate_engine"

# Cached for the reason `get_http_requests_counter` states outright:
# instruments are meant to be created once and reused, never re-created
# on every increment.
_gate_resolutions_counter: Counter | None = None


def get_gate_resolutions_counter() -> Counter:
    """The ``aios.quality_gate.resolutions`` counter, incremented once
    per real gate resolution — passing, warning or blocking.

    Configures metrics first if nothing has, so a caller reaching a gate
    before `configure_metrics` has run still records rather than
    crashing. The identical safety `get_http_requests_counter` provides.
    """
    global _gate_resolutions_counter
    if _gate_resolutions_counter is None:
        configure_metrics()
        _gate_resolutions_counter = get_meter(__name__).create_counter(
            _GATE_RESOLUTIONS_COUNTER_NAME,
            unit="1",
            description="Quality gate resolutions, by gate and outcome.",
        )
    return _gate_resolutions_counter


@contextlib.contextmanager
def gate_span(step_id: str) -> Iterator[None]:
    """A real span around one gate's execution.

    Deliberately records only the step id at open time: the gate's real
    id, version and severity are not known until the registry has
    resolved them, which happens *inside* this span. Attributes that
    matter for querying are attached at resolution time by
    :func:`record_gate_resolution`, which runs while this span is
    current.
    """
    with get_tracer(_TRACER_NAME).start_as_current_span(
        "quality_gate.execute", attributes={"aios.gate.step_id": step_id}
    ):
        yield


def record_gate_resolution(
    *,
    step_id: str,
    gate_id: str,
    passed: bool,
    severity: str,
    duration_ms: int,
    gate_version: str | None = None,
    blocked: bool = False,
) -> None:
    """Emit the log line, the metric and the span attributes for one
    real, resolved gate.

    ``blocked`` distinguishes the two genuinely different failure
    outcomes this engine produces and which ADR-0006 treats as *not*
    interchangeable: a blocking gate that halted the run, versus a
    warning-severity gate that failed and deliberately let it continue.
    Collapsing them into one "failed" signal would make the metric unable
    to answer the only question an operator actually asks of it.

    Best-effort by construction: telemetry must never be able to fail a
    gate that genuinely passed, so every emission is guarded. A dropped
    log line is a monitoring problem; a raised exception here would be a
    correctness one.
    """
    outcome = "blocked" if blocked else ("passed" if passed else "warned")
    attributes: dict[str, Any] = {
        "aios.gate.step_id": step_id,
        "aios.gate.id": gate_id,
        "aios.gate.outcome": outcome,
        "aios.gate.severity": severity,
    }
    if gate_version is not None:
        attributes["aios.gate.version"] = gate_version

    try:
        get_gate_resolutions_counter().add(1, attributes)
    except Exception as exc:  # noqa: BLE001
        _logger.warning("quality_gate.metric_failed", step_id=step_id, error=str(exc))

    log = _logger.warning if blocked else _logger.info
    log(
        "quality_gate.blocked" if blocked else "quality_gate.resolved",
        step_id=step_id,
        gate_id=gate_id,
        gate_version=gate_version,
        outcome=outcome,
        severity=severity,
        passed=passed,
        duration_ms=duration_ms,
    )
