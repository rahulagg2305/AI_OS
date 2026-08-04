"""The Context Assembler (context_manager.md §4) — combines every
configured :class:`~ai_os_kernel.context_manager.resolvers.
ContextSourceResolver`'s items into one :class:`~ai_os_kernel.
context_manager.models.AssembledContext`, then enforces a real token
budget (the Size & Token Budget Enforcer, context_manager.md §4/§6).

**Budget enforcement, not yet filtering or ranking — this step's own
approved scope.** context_manager.md §4 names a "Context Filter /
Ranker" and a "Size & Token Budget Enforcer" as two *distinct* internal
components. This step builds only the second. At the time this module
was first built, there was exactly one real resolver with a constant
``relevance_score`` (no ranking model existed yet), so there was
nothing for a real Filter/Ranker to rank *by*. **Updated
``P02-S03-M08-T05``:** ``KnowledgeResolver`` (``resolvers.py``) now
gives ``relevance_score`` genuine variance (a real fused RRF score, not
a constant) — the precondition this docstring named is now real, but
building the Filter/Ranker component itself remains out of scope for
that step too, deliberately left for its own dedicated one. The budget
enforcer below still reuses ``relevance_score`` only as a stable
tie-break for *which* items survive when there isn't room for all of
them — that is truncation, the behaviour context_manager.md §6
documents ("assembly truncates by rank and reports
``items_excluded_count``"), not ranking as a first-class capability of
its own.

**No budget is enforced unless one is real — the same "disabled means
``None``, zero behaviour change" shape every other Kernel policy limit
in this codebase already uses** (``budget_enforcer``/
``workflow_budget_enforcer`` on ``DispatchingLLMGateway``, ``circuit_
breaker``, ``backoff_policy``). A request with no ``token_budget`` and
an assembler with no ``default_token_budget`` behaves exactly as before
this step: every resolved item included, ``items_excluded_count``
honestly ``0``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

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
    ) -> None:
        self._resolvers = resolvers
        self._default_token_budget = default_token_budget

    async def assemble(self, request: ContextRequest) -> AssembledContext:
        sources_queried: list[SourceType] = []
        items: list[ContextItem] = []
        for resolver in self._resolvers:
            resolver_items = await resolver.resolve(request)
            sources_queried.append(resolver.source_type)
            items.extend(resolver_items)

        budget = (
            request.token_budget if request.token_budget is not None else self._default_token_budget
        )
        if budget is None:
            included, excluded_count = items, 0
        else:
            included, excluded_count = _apply_token_budget(items, budget)

        return AssembledContext(
            items=included,
            total_tokens=sum(item.token_count for item in included),
            sources_queried=sources_queried,
            items_excluded_count=excluded_count,
            assembly_id=new_assembly_id(),
        )


def _apply_token_budget(items: Sequence[ContextItem], budget: int) -> tuple[list[ContextItem], int]:
    """Admits items in descending ``relevance_score`` order — a stable
    sort, so items tied on score keep their original resolver order
    (ADR-0022: "context assembly ... is deterministic given the same
    inputs") — greedily including each one that still fits within the
    remaining budget and skipping (not stopping at) any that doesn't,
    so a smaller, lower-ranked item can still fill room a larger,
    higher-ranked one left unused.

    The returned list preserves the *original* resolver order among
    whichever items survive — truncation decides only which items are
    dropped, never reorders the ones that remain (this step's own
    "preserve stable ordering" requirement) — context_manager.md §6's
    "truncates by rank" governs admission, not final presentation
    order.
    """
    ranked_indices = sorted(
        range(len(items)), key=lambda index: items[index].relevance_score, reverse=True
    )
    admitted = [False] * len(items)
    remaining = budget
    for index in ranked_indices:
        token_count = items[index].token_count
        if token_count <= remaining:
            admitted[index] = True
            remaining -= token_count

    included = [item for index, item in enumerate(items) if admitted[index]]
    excluded_count = len(items) - len(included)
    return included, excluded_count
