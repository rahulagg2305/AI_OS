"""The Retry & Fallback Manager's backoff policy (llm_gateway.md §3:
"backoff, circuit breaker, chain traversal"; §10: "exponential backoff
with jitter, bounded attempts and total time, honouring `retry_after`
when provided") — the third and final named piece of that subsystem to
get a real implementation, after chain traversal and the circuit
breaker.

**Provider-level retry only** (§10's own closing line: "The Gateway
owns provider-level retry; the Workflow Engine owns step-level retry —
a single boundary, so retries cannot multiply"): a :class:`BackoffPolicy`
governs how many times, and with what delay, the *same* provider
candidate is retried before :class:`~ai_os_kernel.llm_gateway.gateway.
DispatchingLLMGateway` gives up on it and moves to the next candidate in
the resolved :class:`~ai_os_kernel.llm_gateway.router.RoutingDecision`
chain (or fails, if there is none) — never a whole-chain retry loop,
and never a second retry layer stacked on top of the Workflow Engine's
own step-level retry policy (``docs/03_architecture/workflow/error_handling_retry.md``),
which is exactly what "retries cannot multiply" rules out.

**Full-jitter exponential backoff**: ``base_delay_seconds * 2 **
(n - 1)``, capped at ``max_delay_seconds``, then a uniform random draw
between zero and that cap — the same "full jitter" strategy already in
wide production use specifically because it spreads retries out evenly
rather than every failed caller retrying at the identical instant.
``max_total_seconds`` bounds the *cumulative* delay across every retry
of one candidate, so a large ``base_delay_seconds``/``max_attempts``
combination cannot make a single candidate's retries run indefinitely.

**``retry_after`` is not honoured.** §10 documents providers that
return a ``Retry-After`` value on a 429; no adapter
(:class:`~ai_os_kernel.llm_gateway.adapters.anthropic_adapter.AnthropicAdapter`,
:class:`~ai_os_kernel.llm_gateway.adapters.local_adapter.LocalAdapter`)
extracts that value from a real response today — the full §10 Error
Taxonomy (categorising provider errors and surfacing their headers)
does not exist in code yet (see :mod:`~ai_os_kernel.llm_gateway.gateway`'s
own docstring) — so there is nothing for this policy to honour yet. A
real, honest gap, not invented around.
"""

from __future__ import annotations

import random

from pydantic import BaseModel, ConfigDict, field_validator


class BackoffPolicy(BaseModel):
    """Bounds one provider candidate's retry behaviour: ``max_attempts``
    (the total number of real calls to that candidate, including the
    first — not additional retries on top of one), how the delay
    between attempts grows, and the ceiling on both a single delay and
    the cumulative delay across every retry of that one candidate.
    """

    model_config = ConfigDict(frozen=True)

    max_attempts: int
    base_delay_seconds: float
    max_delay_seconds: float
    max_total_seconds: float

    @field_validator("max_attempts")
    @classmethod
    def _max_attempts_is_at_least_one(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_attempts must be at least 1")
        return value

    @field_validator("base_delay_seconds", "max_delay_seconds", "max_total_seconds")
    @classmethod
    def _durations_are_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError(
                "base_delay_seconds, max_delay_seconds, and max_total_seconds must be positive"
            )
        return value

    def delay_seconds(self, retry_number: int) -> float:
        """The full-jitter delay before retry number ``retry_number``
        (1-indexed: the delay before the *second* overall attempt is
        ``delay_seconds(1)``, before the third is ``delay_seconds(2)``,
        and so on) — a uniform random draw between zero and
        ``base_delay_seconds * 2 ** (retry_number - 1)``, capped at
        ``max_delay_seconds``.
        """

        cap = min(self.max_delay_seconds, self.base_delay_seconds * (2 ** (retry_number - 1)))
        return random.uniform(0, cap)  # noqa: S311 — jitter timing, not a cryptographic use
