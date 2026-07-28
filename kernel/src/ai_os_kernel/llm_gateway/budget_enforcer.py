"""The Policy & Budget Enforcer (llm_gateway.md §3: "Policy & Budget
Enforcer — per-step, per-workflow, per-experiment"; §9: "Enforced
before the provider call").

**Two real, independent ceilings now exist: per-alias and
per-workflow.** Both are the *same* underlying mechanism —
:class:`PerScopeBudgetEnforcer` tracks cumulative
:class:`~ai_os_kernel.llm_gateway.models.LLMResponse` ``usage.cost_usd``
against a ceiling, keyed by an arbitrary caller-chosen ``scope`` string
— constructed twice in the real composition root
(``kernel/bootstrap.py``) under two different scope keys:

- **per-``model_alias``** (the first real slice, built when this
  module had only one ceiling and the class was still named
  ``PerAliasBudgetEnforcer``): ``model_alias`` is the one caller-facing
  correlation key that has always been on every ``LLMRequest``
  (ADR-0002: "callers never name a literal model id, only an alias"),
  so this needed no contract change at all. Different aliases already
  represent different cost/quality tiers (``fast-cheap`` vs
  ``reasoning``), so capping each independently is a genuine, useful
  budget control in its own right, not only an approximation of the
  workflow ceiling below.
- **per-``workflow_id``** (this step's own addition): now expressible
  because :class:`~ai_os_kernel.llm_gateway.models.LLMRequest` carries
  an optional :class:`~ai_os_kernel.llm_gateway.models.TraceContext`
  (``metadata``) with a ``workflow_id`` field — the exact, documented
  "Workflow cost ceiling" row in §9's table. See
  ``ai_os_kernel.llm_gateway.models``'s own docstring for exactly which
  slice of the full documented ``TraceContext`` this is and why.

**The class was renamed from ``PerAliasBudgetEnforcer`` to
``PerScopeBudgetEnforcer`` for this step**, and this is itself a
recorded architectural decision, not a cosmetic one: the
implementation was already scope-agnostic (its methods always took a
generic ``scope: str``, never anything alias-specific); only the class
*name* implied a single use. Instantiating something literally named
"PerAlias..." to track workflow spend would have been misleading to a
future reader — exactly the kind of confusion this step's own
documentation goals ("ensure another engineer can understand why this
design was chosen") exist to prevent. The rename changes no behaviour;
every existing method signature is unchanged.

**Reuses cost accounting the provider adapters already produce.**
Nothing here estimates or computes a cost — every real
:class:`~ai_os_kernel.llm_gateway.models.LLMResponse` already carries
an honest ``usage.cost_usd`` (computed from configured pricing;
llm_gateway.md's own "the Gateway is the only producer of cost data"
rule). This module only accumulates that already-real number per scope
and compares it against a configured ceiling — no token estimation, no
pre-flight cost guess (both would need a real tokenizer, which §12
forbids approximating).

**Checked once per real attempt, before the Circuit Breaker.** A
budget ceiling is a policy gate, not a resilience concern, so it is
checked first — a call already over budget for its alias or its
workflow spends no further tokens (or circuit-breaker bookkeeping)
finding that out. Neither ceiling is scoped by provider, so every
candidate in a fallback chain shares the identical verdict — see
:class:`~ai_os_kernel.llm_gateway.gateway.DispatchingLLMGateway`'s own
docstring for why a budget failure, unlike a provider-specific one,
never triggers a fallback attempt at all.

**One real cost can push cumulative spend past a ceiling before the
*next* call is refused** — there is no pre-flight cost estimate to
refuse a call speculatively (an honest characteristic of checking
already-recorded spend rather than guessing an upcoming one, not a
bug).

**A request with no ``metadata`` (no ``TraceContext``, or one with
``workflow_id=None``) simply cannot be checked against the per-workflow
ceiling** — there is nothing to key by. This is not a special case
requiring extra code: :class:`~ai_os_kernel.llm_gateway.gateway.
DispatchingLLMGateway` only ever calls the workflow enforcer when a
real ``workflow_id`` is present, so a caller that never supplies
``metadata`` (every caller before this step) is completely unaffected
— this step's own "preserve existing behaviour for callers that do not
use the new metadata" requirement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol


class BudgetEnforcer(Protocol):
    """Per-scope cumulative-spend gate the Policy & Budget Enforcer
    consults before attempting a real call, and reports real spend to
    after one — the seam a persisted or multi-ceiling (tokens/
    tool-calls, not only cost) implementation substitutes later
    (ADR-0004)."""

    def is_within_budget(self, scope: str) -> bool:
        """Whether a real call attributed to ``scope`` should be
        attempted right now. A scope never seen before is always within
        budget (nothing spent yet)."""
        ...

    def record_spend(self, scope: str, cost_usd: Decimal) -> None:
        """A real call attributed to ``scope`` just completed, honestly
        costing ``cost_usd`` — accumulates toward that scope's
        ceiling."""
        ...


@dataclass
class _ScopeSpend:
    total_cost_usd: Decimal = field(default_factory=lambda: Decimal("0"))


class PerScopeBudgetEnforcer:
    """The one real implementation: cumulative spend per caller-chosen
    ``scope`` string, held in a plain ``dict``, lost on process restart
    — the identical, deliberate scope limit
    :class:`~ai_os_kernel.llm_gateway.circuit_breaker.InMemoryCircuitBreaker`
    already documents for the identical reason (no second, real,
    persisted implementation is imminent yet).

    One instance's ``ceiling_usd`` applies independently to every scope
    key *that instance* sees — there is no shared, cross-scope total.
    Two independent ceilings (one per-alias, one per-workflow — see
    this module's own docstring) are therefore two independent
    instances, each with its own ceiling and its own scope space, never
    one instance keyed by a composite string — composing the keys would
    conflate two independent policies into one.
    """

    def __init__(self, *, ceiling_usd: Decimal) -> None:
        if ceiling_usd <= 0:
            raise ValueError("ceiling_usd must be positive")
        self._ceiling_usd = ceiling_usd
        self._spend: dict[str, _ScopeSpend] = {}

    def is_within_budget(self, scope: str) -> bool:
        spend = self._spend.get(scope)
        if spend is None:
            return True
        return spend.total_cost_usd < self._ceiling_usd

    def record_spend(self, scope: str, cost_usd: Decimal) -> None:
        spend = self._spend.setdefault(scope, _ScopeSpend())
        spend.total_cost_usd += cost_usd
