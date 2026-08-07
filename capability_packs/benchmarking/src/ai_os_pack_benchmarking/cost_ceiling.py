"""Cost ceiling enforcement (`P04-S03-M34-T03`, FR-076) —
`llm_gateway.md` §9's own "Experiment cost ceiling | Refuses to start
the run" row, the third of its 5 documented pre-call checks (2 of
which — per-alias, per-workflow — are already real,
`ai_os_kernel.llm_gateway.budget_enforcer.PerScopeBudgetEnforcer`).

**A real, distinct failure mode from the existing two ceilings, not a
reuse of `BudgetExceededError`.** §9's own table names it separately:
the per-alias/per-workflow ceilings check *already-accumulated real
spend* against a ceiling *before each individual call*
(`PerScopeBudgetEnforcer.is_within_budget`, checked "once per real
attempt"); this check instead refuses an entire experiment *before its
first call is ever made*, given an already-computed projection —
matching this ticket's own literal Input ("A projected cost") and
Output ("Refusal before dispatch").

**Computing a real, non-approximated projected cost is a real,
disclosed, separate concern, not this ticket's own scope.** A genuine,
non-estimated projection would need the real `count_tokens()` API
(`llm_gateway.md` §12: token counting must never be approximated) run
against every planned replicate's own real, rendered prompt, times
each one's own real, configured per-token pricing — real work this
pack cannot do alone (`count_tokens()` is real for exactly one
provider adapter today, `AnthropicAdapter`, reached only through the
Kernel this pack may never import) and which no caller has asked for
yet (`ExperimentSpec` names no rendering/pricing inputs at all). This
function takes the projection as a caller-supplied fact, exactly as
its own ticket names it as "Input," and enforces it — it does not
compute it.
"""

from __future__ import annotations

from decimal import Decimal


class CostCeilingExceededError(ValueError):
    """A projected cost exceeded its experiment's own declared
    ceiling — refused before any real call was made
    (`llm_gateway.md` §9: "Experiment cost ceiling | Refuses to start
    the run"), a real, distinct failure mode from
    `~ai_os_kernel.llm_gateway.errors.BudgetExceededError`, which
    instead refuses one already-in-progress call."""


def enforce_cost_ceiling(*, projected_cost_usd: Decimal, ceiling_usd: Decimal | None) -> None:
    """Refuses (raises `CostCeilingExceededError`) if `projected_cost_usd`
    exceeds `ceiling_usd`. `ceiling_usd=None` means no ceiling was
    declared for this experiment (`ExperimentDefinition.cost_ceiling_usd`'s
    own real default) — always passes, the identical "absent means
    unenforced" shape every other optional policy gate in this
    codebase already establishes."""
    if ceiling_usd is None:
        return
    if projected_cost_usd > ceiling_usd:
        raise CostCeilingExceededError(
            f"projected cost {projected_cost_usd} USD exceeds this experiment's own "
            f"declared ceiling of {ceiling_usd} USD — refused before any call was made"
        )
