"""The Retry & Fallback Manager's Circuit Breaker (llm_gateway.md §3:
"backoff, circuit breaker, chain traversal"; §10: "A circuit breaker
opens per provider after a configured consecutive-failure count and
half-opens on a timer") — the second of that subsystem's three named
pieces to get a real implementation, after chain traversal.

**Per-provider, in-process, three-state.** :class:`InMemoryCircuitBreaker`
tracks one :class:`CircuitState` per provider name — ``CLOSED`` (normal:
calls proceed), ``OPEN`` (skip: recent consecutive failures crossed the
configured threshold, so calls are refused without even attempting a
real network call), ``HALF_OPEN`` (one trial call is allowed after the
configured timer elapses, to test whether the provider has recovered).
This is exactly §10's own description, no more: no adaptive scoring, no
weighted health signal, no persistence across process restarts (a real,
plausible second implementation — e.g. Redis-backed, shared across
Kernel instances — is deferred; ADR-0004 does not yet have a second,
real implementation to justify building one now).

**The timer transition is lazy, not scheduled.** ``is_available()``
itself checks whether ``OPEN``'s configured ``reset_timeout_seconds``
has elapsed and transitions to ``HALF_OPEN`` as a side effect when it
has — there is no background timer, thread, or scheduler (a "no worker
scheduler" exclusion this codebase already applies elsewhere). This is
correct and sufficient because the breaker is only ever consulted
immediately before a real call would be made
(:class:`~ai_os_kernel.llm_gateway.gateway.DispatchingLLMGateway`), so
"the timer elapsed" only ever needs to be known at exactly the moment
it matters.

**Deliberately not concurrency-hardened.** Two concurrent requests
arriving during the same ``HALF_OPEN`` window may both be let through
as trials rather than exactly one — a known, accepted imprecision most
circuit breaker implementations share, not a correctness bug for this
step's scope ("no adaptive routing ... unless the architecture
explicitly requires one of them for this minimal step" — it does not
require strict single-trial gating).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol


class CircuitState(StrEnum):
    """One provider's current circuit state — §10's own three-state
    description, no more."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker(Protocol):
    """Per-provider failure memory the Retry & Fallback Manager consults
    before attempting a real call, and reports the outcome of after
    one — the seam a persisted/shared implementation substitutes later
    (ADR-0004)."""

    def is_available(self, provider: str) -> bool:
        """Whether a real call to ``provider`` should be attempted right
        now. A provider never seen before is always available (§10's
        own default: nothing is broken until proven otherwise)."""
        ...

    def record_success(self, provider: str) -> None:
        """A real call to ``provider`` just succeeded — resets it to
        ``CLOSED`` with no failure memory, whatever state it was in."""
        ...

    def record_failure(self, provider: str) -> None:
        """A real call to ``provider`` just raised
        :class:`~ai_os_kernel.llm_gateway.errors.LLMProviderError` —
        counts toward opening the circuit (or reopens it immediately,
        if this was itself the ``HALF_OPEN`` trial call)."""
        ...


@dataclass
class _ProviderCircuit:
    state: CircuitState = CircuitState.CLOSED
    consecutive_failures: int = 0
    # Only meaningful while `state is CircuitState.OPEN` — always set in
    # the same assignment that sets that state, so this default is never
    # read as a real timestamp.
    opened_at: float = field(default=0.0)


class InMemoryCircuitBreaker:
    """The one real implementation for this step: per-provider state
    held in a plain ``dict``, lost on process restart — see this
    module's own docstring for why that is an honest, deliberate scope
    limit, not an oversight.

    ``failure_threshold`` is the number of *consecutive* failures (not a
    rate or a window) that opens the circuit — §10's own "a configured
    consecutive-failure count." ``reset_timeout_seconds`` is how long an
    ``OPEN`` circuit stays closed to calls before allowing one
    ``HALF_OPEN`` trial — §10's own "half-opens on a timer."
    """

    def __init__(self, *, failure_threshold: int, reset_timeout_seconds: float) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be at least 1")
        if reset_timeout_seconds <= 0:
            raise ValueError("reset_timeout_seconds must be positive")
        self._failure_threshold = failure_threshold
        self._reset_timeout_seconds = reset_timeout_seconds
        self._circuits: dict[str, _ProviderCircuit] = {}

    def is_available(self, provider: str) -> bool:
        circuit = self._circuits.get(provider)
        if circuit is None or circuit.state is not CircuitState.OPEN:
            return True
        if time.monotonic() - circuit.opened_at < self._reset_timeout_seconds:
            return False
        circuit.state = CircuitState.HALF_OPEN
        return True

    def record_success(self, provider: str) -> None:
        self._circuits[provider] = _ProviderCircuit()

    def record_failure(self, provider: str) -> None:
        circuit = self._circuits.setdefault(provider, _ProviderCircuit())
        if circuit.state is CircuitState.HALF_OPEN:
            # The trial call itself failed: reopen immediately, without
            # waiting for a fresh run of consecutive closed-state
            # failures — the provider is still unhealthy.
            circuit.state = CircuitState.OPEN
            circuit.opened_at = time.monotonic()
            return
        circuit.consecutive_failures += 1
        if circuit.consecutive_failures >= self._failure_threshold:
            circuit.state = CircuitState.OPEN
            circuit.opened_at = time.monotonic()
