"""The Router (llm_gateway.md §3/§7): resolves a caller-supplied
``model_alias`` to a real provider and model id — "alias -> provider/
model, fallback chain." ADR-0002 requires this: callers never name a
literal model id, only an alias, so something in the platform must own
turning one into the other.

**Genuinely multi-provider, not one default provider for every
alias.** The previous step's own ``StaticRouter`` took a single
``default_provider`` and applied it to every configured alias — real,
but "beyond today's single-provider ... mapping" (this step's own
approved framing) was still true of it. Each alias now carries its own
:class:`RoutingDecision` (``provider`` + ``model_id``) directly, so two
aliases can genuinely resolve to two different providers — a real
routing decision, not an assumption baked into the constructor. Still
no provider health, no experiment pinning, no per-request
decision-making at all — see below for the one remaining piece
(a real chain) that *did* land, and see
:class:`~ai_os_kernel.llm_gateway.gateway.DispatchingLLMGateway` for
the seam that actually *acts* on a multi-provider decision.

**Now carries a real chain — the exact, backward-compatible extension
this module's own earlier docstring anticipated.** llm_gateway.md §7's
documented config shape (``aliases.<alias>.chain``, an ORDERED list of
provider/model candidates) exists for the Retry & Fallback Manager
(llm_gateway.md §3: "backoff, circuit breaker, chain traversal") to
walk on failure. This step builds the smallest real slice of that
subsystem: **chain traversal only** — no backoff, no circuit breaker,
no provider health, no experiment pinning (this step's own approved
exclusions). :class:`RoutingDecision` gained one new, optional field,
``fallback: RoutingDecision | None``, so a chain of any length is
simply a linked list of already-existing ``RoutingDecision`` objects —
the :class:`Router` Protocol's own ``resolve(alias) -> RoutingDecision``
shape needed no change at all, exactly as anticipated. The walking
itself lives in :class:`~ai_os_kernel.llm_gateway.gateway.
DispatchingLLMGateway`, not here — this module still only ever answers
"which provider and model (and which fallback, if any) for this alias,
right now," deterministically, from static configuration; *acting* on
a failure is the dispatcher's job, matching llm_gateway.md §3's own
Router/Retry-&-Fallback-Manager split.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from ai_os_kernel.llm_gateway.error_taxonomy import NO_ROUTE
from ai_os_kernel.llm_gateway.errors import LLMProviderError


class RoutingDecision(BaseModel):
    """One resolved routing choice: which provider, and which of that
    provider's real model ids, a caller's ``model_alias`` currently
    means, plus an optional ``fallback`` — the next candidate to try if
    this one fails, itself a full :class:`RoutingDecision` (so a chain
    of any length is just a linked list of these, primary first).
    ``fallback`` is ``None`` for every alias that configures no chain —
    the identical single-candidate shape this class always had,
    unchanged in that case."""

    model_config = ConfigDict(frozen=True)

    provider: str
    model_id: str
    fallback: RoutingDecision | None = None


def build_routing_chain(candidates: Sequence[tuple[str, str]]) -> RoutingDecision:
    """Builds one linked :class:`RoutingDecision` chain from an ordered,
    primary-first sequence of ``(provider, model_id)`` pairs — the
    Router-side half of "alias -> provider/model, fallback chain"
    (llm_gateway.md §3). ``candidates`` with exactly one entry produces
    a :class:`RoutingDecision` with ``fallback=None``, identical to
    constructing one directly; this function exists so a caller with a
    real, possibly-longer chain does not have to hand-write the nested
    construction itself.

    Raises :class:`ValueError` for an empty sequence — a chain needs at
    least one candidate (the primary) to mean anything.
    """

    if not candidates:
        raise ValueError("build_routing_chain requires at least one (provider, model_id) pair")

    last_provider, last_model_id = candidates[-1]
    decision = RoutingDecision(provider=last_provider, model_id=last_model_id)
    for provider, model_id in reversed(candidates[:-1]):
        decision = RoutingDecision(provider=provider, model_id=model_id, fallback=decision)
    return decision


class Router(Protocol):
    """Resolves a ``model_alias`` to a :class:`RoutingDecision` — the
    seam a provider-health-aware or experiment-pinning-aware
    implementation substitutes later (ADR-0004: interface-driven,
    configuration over code)."""

    def resolve(self, model_alias: str) -> RoutingDecision: ...


class StaticRouter:
    """The one deterministic implementation for this step: a fixed,
    configuration-driven ``alias -> RoutingDecision`` mapping, with no
    per-request decision-making at all — the "keep routing
    deterministic" requirement this step's own approved framing states.

    Each entry in ``routes`` names its own provider, so a caller
    building this mapping decides, per alias, which provider serves it
    — genuinely multi-provider when more than one provider name
    appears across the mapping's values, and identical to the previous
    step's single-provider behaviour when it does not. Nothing here
    checks that a named provider has a real, registered
    :class:`~ai_os_kernel.llm_gateway.gateway.LLMGateway` — that check
    belongs to whatever dispatches on the resolved decision (see
    :class:`~ai_os_kernel.llm_gateway.gateway.DispatchingLLMGateway`),
    not to the Router, which only ever answers "what did configuration
    say," never "is that usable right now."
    """

    def __init__(self, *, routes: Mapping[str, RoutingDecision]) -> None:
        self._routes = dict(routes)

    def resolve(self, model_alias: str) -> RoutingDecision:
        decision = self._routes.get(model_alias)
        if decision is None:
            raise LLMProviderError(
                f"model_alias {model_alias!r} has no configured route "
                "(ADR-0002: callers never name a literal model id, so an "
                "unconfigured alias cannot fall back to one)",
                category=NO_ROUTE.category,
                error_code=NO_ROUTE.error_code,
                retriable=NO_ROUTE.retriable,
            )
        return decision
