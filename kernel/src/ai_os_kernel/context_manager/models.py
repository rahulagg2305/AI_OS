"""A deliberately minimal slice of context_manager.md §5/§6's documented
request/response contract — enough to prove the Context Manager's own
request flow end to end, not the full seven-source, ranked, budgeted
design that document describes.

**Reduced, not redesigned.** context_manager.md §5's full ``Context
Request`` names ``workflow_id``, ``step_id``, ``agent_id``,
``required_context_types``, ``token_budget or size limit``, and
``experiment / run identifiers``. :class:`ContextRequest` here now
carries the first three plus ``token_budget`` — the Size & Token Budget
Enforcer's own step adds exactly the one field it needs, nothing else —
plus ``knowledge_query`` (``P02-S03-M08-T05``), added the identical way
once :class:`~ai_os_kernel.context_manager.resolvers.KnowledgeResolver`
gave it a real, immediate need. ``required_context_types`` and the
experiment/run identifiers remain absent as *fields*, not present as
always-``None`` ones — the same "reduced slice" shape
:class:`~ai_os_kernel.llm_gateway.models.TraceContext` already
established: ``required_context_types`` still has no declared source
(workflow_architecture.md's Step Contract has no field naming which
context types a step needs — only
``agentId``/``toolId``/``promptId``/``promptVersion``/``modelAlias``),
and no experiment support exists anywhere in this codebase
(evaluation_engine.md §5.1: experiment definition lives in the
Benchmarking Pack, which does not exist). Populating either with an
unused default would be exactly the "placeholder architecture" this
step must avoid.

**``token_budget`` is optional and, when absent, changes nothing.**
:class:`~ai_os_kernel.context_manager.manager.DefaultContextManager`
falls back to its own constructor-supplied default when a request
carries none — see that module's own docstring. A request that
specifies neither (no caller does, before this step) is enforced
exactly as it was before this step: every resolved item included,
``items_excluded_count`` honestly ``0``.

**``AssembledContext`` is likewise a reduced slice of context_manager.md
§6.** ``items``, ``total_tokens``, ``sources_queried``, and
``items_excluded_count`` are all implemented and mean exactly what they
say: this call's real, possibly-truncated items, a real (approximate —
see below) token sum of exactly those surviving items, which resolvers
actually ran, and how many resolved items a real Size & Token Budget
Enforcer excluded. §6's ``index_generation`` field is omitted entirely:
it exists to pin a retrieval index generation for reproducibility
(ADR-0022), and there is no retrieval index — no Knowledge Manager, no
Memory Manager, nothing under kernel_architecture.md's "Retrieval"
heading is built yet. A fabricated value here would misrepresent a
reproducibility guarantee this slice cannot provide.

**Token counts here are an honest approximation, not a contradiction of
llm_gateway.md §12.** §12's "never approximate, provider endpoints
only" rule governs the LLM Gateway's own budget/cost accounting, where
an approximation would corrupt money and enforcement. Context assembly
happens *before* a model is even chosen (``ContextRequest`` carries no
``model_alias`` — context_manager.md's own §5 does not list one), so no
provider ``count_tokens()`` endpoint is reachable yet even in principle.
``ContextItem.token_count``/``AssembledContext.total_tokens`` are
therefore a simple, deterministic length heuristic
(:func:`~ai_os_kernel.context_manager.resolvers.estimate_tokens`), used
for bookkeeping only — nothing in this slice enforces a budget against
it.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SourceType(StrEnum):
    """Which :class:`~ai_os_kernel.context_manager.resolvers.
    ContextSourceResolver` produced a given item — context_manager.md
    §4's "Source Resolvers" list five; all five are real here.
    """

    WORKFLOW_STATE = "workflow_state"
    # Real as of P02-S03-M08-T05 -- see resolvers.py's own
    # KnowledgeResolver.
    KNOWLEDGE = "knowledge"
    # Real as of P02-S03-M08-T06 -- see resolvers.py's own
    # MemoryResolver.
    MEMORY = "memory"
    # Real as of P02-S03-M08-T08 -- see resolvers.py's own
    # RuntimeConfigResolver.
    CONFIGURATION = "configuration"
    # Real as of P02-S03-M08-T07 -- see resolvers.py's own
    # AIContextPackResolver.
    AI_CONTEXT_PACK = "ai_context_pack"


class SourceRef(BaseModel):
    """Where one :class:`ContextItem` came from. context_manager.md §6
    says only "where it came from, and at what version" — no fields are
    specified. ``version`` is deliberately omitted here rather than
    populated with a meaningless constant: Workflow State has no
    versioning concept the way a Knowledge Manager document might, and
    adding an unused field for a future source is exactly the
    placeholder architecture this step avoids. A future
    Knowledge/Memory resolver can add it additively.
    """

    model_config = ConfigDict(frozen=True)

    source_type: SourceType
    identifier: str


class ContextItem(BaseModel):
    """One unit of assembled context — context_manager.md §6's full
    shape, implemented completely (unlike the request/response wrapper
    around it): every field here is real and meaningful today, not a
    placeholder for a future capability.
    """

    model_config = ConfigDict(frozen=True)

    content: str
    provenance: SourceRef
    relevance_score: float
    token_count: int
    trust: Literal["trusted", "untrusted"]


class ContextRequest(BaseModel):
    """See this module's own docstring for which of context_manager.md
    §5's documented fields this reduced slice carries, and why."""

    model_config = ConfigDict(frozen=True)

    workflow_id: str
    step_id: str
    agent_id: str | None = None
    # None means "no per-request override" — the Size & Token Budget
    # Enforcer's own default applies instead (see manager.py). Rejects
    # <= 0 rather than silently admitting nothing, or nothing at all:
    # a nonsensical value is a caller error, not a degenerate context.
    token_budget: int | None = Field(default=None, gt=0)
    # Added at P02-S03-M08-T05: real, per-request query text for
    # KnowledgeResolver (resolvers.py). None means "no knowledge query
    # declared for this request" -- the identical "an unresolvable
    # source contributing nothing is not a failure" shape every other
    # resolver in this package already establishes, not an error.
    knowledge_query: str | None = None


class AssembledContext(BaseModel):
    """See this module's own docstring for which of context_manager.md
    §6's documented fields this reduced slice carries, and why
    ``index_generation`` is absent entirely."""

    model_config = ConfigDict(frozen=True)

    items: list[ContextItem]
    total_tokens: int
    sources_queried: list[SourceType]
    items_excluded_count: int
    assembly_id: str
