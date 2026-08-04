"""The Context Assembler (context_manager.md §4) — combines every
configured :class:`~ai_os_kernel.context_manager.resolvers.
ContextSourceResolver`'s items into one :class:`~ai_os_kernel.
context_manager.models.AssembledContext`, ranks them by relevance (the
Context Filter / Ranker), then enforces a real token budget (the Size &
Token Budget Enforcer) — context_manager.md §4's three distinct boxes,
in that documented order, all real as of ``P02-S03-M08-T09``.

**The Filter/Ranker is now real (``P02-S03-M08-T09``).** Building it
was blocked until ``relevance_score`` had genuine cross-source variance
— true only since ``KnowledgeResolver`` (``P02-S03-M08-T05``) started
returning real fused RRF scores alongside ``WorkflowStateResolver``'s
fixed constant. :func:`_rank_by_relevance` is the real component:
:class:`~ai_os_kernel.context_manager.models.ContextItem`\\ s, sorted
descending by ``relevance_score``, ties broken by original
resolver-arrival order (a stable sort — ADR-0022's determinism
requirement).

**A deliberate, disclosed reversal of this module's own prior
decision.** Before this step, :func:`_apply_token_budget` used
``relevance_score`` only to decide *which* items survive truncation,
then deliberately returned survivors in their *original* resolver
order — a real, tested guarantee
(``test_surviving_items_are_returned_in_original_resolver_order_not_rank_order``,
now rewritten to assert the opposite). This ticket's own Goal — "rank
and trim candidates ... by relevance, not order" — and its Output — "a
ranked, trimmed set" — are explicit that the *final presented order*
must now be rank order too, matching context_manager.md §4's own
diagram sequencing (Filter/Ranker *before* the Budget Enforcer, not
folded into it). Confirmed as the intended reading via product-owner
sign-off before reversing the prior test's own guarantee, not decided
unilaterally.

**No budget is enforced unless one is real — the same "disabled means
``None``, zero behaviour change" shape every other Kernel policy limit
in this codebase already uses** (``budget_enforcer``/
``workflow_budget_enforcer`` on ``DispatchingLLMGateway``, ``circuit_
breaker``, ``backoff_policy``). A request with no ``token_budget`` and
an assembler with no ``default_token_budget`` still ranks every item
(this step's own new behaviour) but excludes none — every resolved item
included, ``items_excluded_count`` honestly ``0``.

**The Context Audit Logger is real too (``P02-S03-M08-T10``)**, the
identical optional-collaborator shape ``audit_logger``/
``budget_enforcer`` above already use: ``None`` (the default) means no
persistence and zero behaviour change for every existing caller; a real
:class:`~ai_os_kernel.context_manager.audit_logger.ContextAuditLogger`
means every ``assemble`` call is durably recorded (§9: "every context
assembly must record ...") before its result is returned.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from ai_os_kernel.context_manager.audit_logger import ContextAuditLogger
from ai_os_kernel.context_manager.ids import new_assembly_id
from ai_os_kernel.context_manager.models import (
    AssembledContext,
    ContextItem,
    ContextRequest,
    SourceType,
)
from ai_os_kernel.context_manager.resolvers import ContextSourceResolver


class ContextManager(Protocol):
    """The sole seam through which the Workflow Engine assembles context
    before invoking an Agent (agent_architecture.md's Invocation
    Lifecycle, step 1: "Workflow Engine assembles context via the
    Context Manager"). ``assemble`` is not a name context_manager.md
    specifies literally — that document shows no method signature, only
    a request/response shape — chosen to match this component's own
    documented name, "Context Assembler" (§4), and the verb-based
    Protocol method naming already established by
    :meth:`~ai_os_kernel.prompt_engine.renderer.PromptEngine.render`
    and :meth:`~ai_os_kernel.llm_gateway.gateway.LLMGateway.complete`.
    """

    async def assemble(self, request: ContextRequest) -> AssembledContext: ...


class DefaultContextManager:
    """Queries every configured resolver, in order, concatenates their
    items, then enforces a token budget if one applies.

    ``resolvers`` is a plain sequence, not a registry keyed by
    :class:`~ai_os_kernel.context_manager.models.SourceType` — nothing
    yet needs to look one up by type (no ``required_context_types`` on
    :class:`ContextRequest` to select against), so a registry would be
    an unused capability, not a real requirement.

    ``default_token_budget`` mirrors :class:`~ai_os_kernel.llm_gateway.
    budget_enforcer.PerScopeBudgetEnforcer`'s own shape: a ceiling the
    *assembler* is configured with, applied whenever a caller's own
    :class:`ContextRequest` doesn't specify a more specific one. This is
    a deliberate choice over requiring every caller to supply
    ``token_budget`` on every request: context_manager.md §5 documents
    ``token_budget`` as something a request *may* carry, not something
    every request must declare, and forcing every existing caller to
    start passing one would be exactly the kind of unnecessary,
    non-additive change this step avoids.
    """

    def __init__(
        self,
        resolvers: Sequence[ContextSourceResolver],
        *,
        default_token_budget: int | None = None,
        audit_logger: ContextAuditLogger | None = None,
    ) -> None:
        self._resolvers = resolvers
        self._default_token_budget = default_token_budget
        self._audit_logger = audit_logger

    async def assemble(self, request: ContextRequest) -> AssembledContext:
        sources_queried: list[SourceType] = []
        items: list[ContextItem] = []
        for resolver in self._resolvers:
            resolver_items = await resolver.resolve(request)
            sources_queried.append(resolver.source_type)
            items.extend(resolver_items)

        ranked_items = _rank_by_relevance(items)

        budget = (
            request.token_budget if request.token_budget is not None else self._default_token_budget
        )
        if budget is None:
            included, excluded_count = ranked_items, 0
        else:
            included, excluded_count = _apply_token_budget(ranked_items, budget)

        assembled = AssembledContext(
            items=included,
            total_tokens=sum(item.token_count for item in included),
            sources_queried=sources_queried,
            items_excluded_count=excluded_count,
            assembly_id=new_assembly_id(),
        )

        if self._audit_logger is not None:
            await self._audit_logger.record(request=request, assembled=assembled)

        return assembled


def _rank_by_relevance(items: Sequence[ContextItem]) -> list[ContextItem]:
    """The real Context Filter / Ranker (context_manager.md §4) —
    descending ``relevance_score``, ties broken by a stable sort that
    preserves original resolver-arrival order (ADR-0022: "context
    assembly ... is deterministic given the same inputs"). Runs before
    any budget is applied, so ranking always reflects every candidate,
    not only the survivors.
    """
    return sorted(items, key=lambda item: item.relevance_score, reverse=True)


def _apply_token_budget(items: Sequence[ContextItem], budget: int) -> tuple[list[ContextItem], int]:
    """The Size & Token Budget Enforcer — ``items`` is assumed already
    ranked (:func:`_rank_by_relevance`, called first in
    :meth:`DefaultContextManager.assemble`). Greedily admits each item,
    in that rank order, that still fits within the remaining budget,
    skipping (not stopping at) any that doesn't — so a smaller,
    lower-ranked item can still fill room a larger, higher-ranked one
    left unused.

    The returned list is in **rank order**, not original resolver
    order — this step's own reversal of a prior decision; see this
    module's own docstring for why.
    """
    included: list[ContextItem] = []
    remaining = budget
    for item in items:
        if item.token_count <= remaining:
            included.append(item)
            remaining -= item.token_count

    excluded_count = len(items) - len(included)
    return included, excluded_count
