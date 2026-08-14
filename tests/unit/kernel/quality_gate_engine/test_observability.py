"""§5's Observability Hook (`P02-S06-M15-T10`) — the component that had
no code at all until this ticket.

These assert on the *real* emissions, captured from `structlog`'s own
real pipeline, rather than on a mock having been called: the point of
the ticket was that nothing was emitted, so "something real came out"
is the only assertion that would have failed before.
"""

from __future__ import annotations

import structlog

from ai_os_kernel.quality_gate_engine.observability import (
    gate_span,
    get_gate_resolutions_counter,
    record_gate_resolution,
)


def test_a_passing_gate_emits_a_real_structured_event() -> None:
    with structlog.testing.capture_logs() as logs:
        record_gate_resolution(
            step_id="quality-gate-tests-pass",
            gate_id="se.build_tests_pass",
            gate_version="1.0.0",
            passed=True,
            severity="blocking",
            duration_ms=137,
        )

    assert len(logs) == 1
    event = logs[0]
    assert event["event"] == "quality_gate.resolved"
    assert event["outcome"] == "passed"
    assert event["gate_id"] == "se.build_tests_pass"
    assert event["gate_version"] == "1.0.0"
    assert event["duration_ms"] == 137
    assert event["log_level"] == "info"


def test_a_blocked_gate_is_distinguishable_from_a_warning_failure() -> None:
    """ADR-0006 treats these as genuinely different outcomes, so the
    telemetry must too — collapsing both into "failed" would make the
    metric unable to answer the only question an operator asks of it."""
    with structlog.testing.capture_logs() as logs:
        record_gate_resolution(
            step_id="g",
            gate_id="se.build_lint_clean",
            passed=False,
            severity="blocking",
            duration_ms=5,
            blocked=True,
        )
        record_gate_resolution(
            step_id="g",
            gate_id="se.style_advisory",
            passed=False,
            severity="warning",
            duration_ms=5,
        )

    blocked, warned = logs
    assert blocked["event"] == "quality_gate.blocked"
    assert blocked["outcome"] == "blocked"
    assert blocked["log_level"] == "warning"
    assert warned["event"] == "quality_gate.resolved"
    assert warned["outcome"] == "warned"
    assert warned["log_level"] == "info"


def test_the_counter_is_created_once_and_reused() -> None:
    """Instruments are meant to be created a single time and reused —
    the same contract `get_http_requests_counter` documents."""
    assert get_gate_resolutions_counter() is get_gate_resolutions_counter()


def test_recording_never_raises_even_when_the_metric_backend_fails() -> None:
    """Telemetry must never be able to fail a gate that genuinely
    passed. A dropped metric is a monitoring problem; an exception here
    would be a correctness one."""
    import ai_os_kernel.quality_gate_engine.observability as obs

    class _ExplodingCounter:
        def add(self, amount: int, attributes: dict[str, object]) -> None:
            raise RuntimeError("metric backend is down")

    original = obs._gate_resolutions_counter
    obs._gate_resolutions_counter = _ExplodingCounter()  # type: ignore[assignment]
    try:
        with structlog.testing.capture_logs() as logs:
            record_gate_resolution(
                step_id="g", gate_id="se.x", passed=True, severity="blocking", duration_ms=1
            )
        events = [entry["event"] for entry in logs]
        assert "quality_gate.metric_failed" in events
        assert "quality_gate.resolved" in events
    finally:
        obs._gate_resolutions_counter = original


def test_the_gate_span_is_a_real_usable_context_manager() -> None:
    """The span must not swallow an exception the gate raises — a
    blocking gate's failure has to propagate out of it unchanged."""
    with gate_span("quality-gate-tests-pass"):
        pass

    try:
        with gate_span("quality-gate-tests-pass"):
            raise RuntimeError("gate blew up")
    except RuntimeError as exc:
        assert str(exc) == "gate blew up"
    else:  # pragma: no cover - the raise above always fires
        raise AssertionError("gate_span swallowed a real exception")
