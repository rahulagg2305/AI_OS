"""The Policy & Budget Enforcer (llm_gateway.md §3: "Policy & Budget
Enforcer — per-step, per-workflow, per-experiment"; §9: "Enforced
before the provider call").

**Four real, independent ceilings now exist: per-alias, per-workflow,
per-step-tokens, and per-step-wall-time (`P02-S02-M06-T07`,
2026-08-10).** The per-step pair closes 2 of the 3 real gaps
`llm_gateway.md`'s own Implementation Status named ("2 of §9's 5
pre-call checks are real") — `StepBudget` (`ai_os_sdk.models.common`)
declares exactly four ceiling dimensions (`max_tokens`/`max_cost_usd`/
`max_tool_calls`/`max_wall_seconds`); with per-alias cost already
standing in for the step-cost dimension (this module's own prior
docstring), the two genuinely missing, *buildable* dimensions were
tokens and wall-time — both accumulate an already-real, already-honest
per-response number (`usage.input_tokens + usage.output_tokens`;
`usage.latency_ms`) the identical way cost already does, no new
estimation. **`max_tool_calls` remains genuinely unbuilt, disclosed,
not merely deferred**: `LLMRequest` has no `tools` field at all
(tool-calling is its own, separately deferred subsystem —
`models.py`'s own docstring lists `tools`/`tool_choice` among fields
"belonging to an explicitly deferred subsystem") — there is nothing for
a tool-call ceiling to count yet.

**Per-step ceilings are scoped by `(workflow_id, step_id)`, never bare
`step_id` — a real correctness requirement, not a style choice.** A
step id like `"build"` recurs across every separate real workflow
instance that declares a step of that name; keying by `step_id` alone
would let one instance's spend count against a completely different
instance's own ceiling. :func:`step_scope` builds the one, shared
composite key both new enforcers below use — the identical
`f"{workflow_id}:{step_name}:..."` composite-identity convention
`workflow_steps.idempotency_key` already establishes elsewhere in this
codebase, reused here rather than a second, ad hoc scheme.

**Two real, independent cost ceilings also exist: per-alias and
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


def step_scope(workflow_id: str, step_id: str) -> str:
    """The one, shared composite scope key every per-step ceiling below
    uses — see this module's own docstring for why bare ``step_id``
    would be wrong (it recurs across every separate real workflow
    instance that declares a step of that name)."""
    return f"{workflow_id}:{step_id}"


class CountBudgetEnforcer(Protocol):
    """The identical per-scope cumulative-ceiling shape
    :class:`BudgetEnforcer` already establishes, generalised to a plain
    ``int`` count rather than a :class:`~decimal.Decimal` cost — tokens
    and wall-time-in-milliseconds are both already-honest integers
    (:class:`~ai_os_kernel.llm_gateway.models.UsageRecord`), never
    money, so a separate, ``int``-native Protocol avoids forcing an
    artificial ``Decimal`` wrap at every call site for no real benefit.
    """

    def is_within_budget(self, scope: str) -> bool:
        """Whether a real call attributed to ``scope`` should be
        attempted right now. A scope never seen before is always within
        budget (nothing spent yet)."""
        ...

    def record_usage(self, scope: str, amount: int) -> None:
        """A real call attributed to ``scope`` just completed, honestly
        consuming ``amount`` of whatever this instance's own ceiling
        measures (tokens, or milliseconds) — accumulates toward that
        scope's ceiling."""
        ...


@dataclass
class _ScopeCount:
    total: int = 0


class PerScopeCountBudgetEnforcer:
    """The ``int``-native sibling of :class:`PerScopeBudgetEnforcer` —
    identical cumulative-per-scope-ceiling mechanism and identical
    deliberate scope limit (plain ``dict``, lost on process restart),
    just tracking a plain count instead of a cost. One instance per real
    ceiling (tokens, or wall-time-in-milliseconds) — see this module's
    own docstring for why per-step ceilings must be keyed by
    :func:`step_scope`'s own composite key, never bare ``step_id``.
    """

    def __init__(self, *, ceiling: int) -> None:
        if ceiling <= 0:
            raise ValueError("ceiling must be positive")
        self._ceiling = ceiling
        self._usage: dict[str, _ScopeCount] = {}

    def is_within_budget(self, scope: str) -> bool:
        usage = self._usage.get(scope)
        if usage is None:
            return True
        return usage.total < self._ceiling

    def record_usage(self, scope: str, amount: int) -> None:
        usage = self._usage.setdefault(scope, _ScopeCount())
        usage.total += amount
