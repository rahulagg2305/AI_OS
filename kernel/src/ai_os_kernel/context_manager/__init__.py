"""Context Manager — request flow, one real resolver, and a real token
budget enforcer.

See docs/03_architecture/kernel/context_manager.md,
docs/03_architecture/agents/agent_architecture.md (Context Consumer /
Invocation Lifecycle), docs/03_architecture/workflow/workflow_architecture.md
(High-Level Architecture: "Context Manager -> assembled context"),
docs/19_roadmap/implementation_roadmap.md §3 (Stage B: "Context Manager
with deterministic assembly, budget enforcement, and trust tagging").

Implemented so far:

- :class:`~ai_os_kernel.context_manager.models.ContextRequest`/
  :class:`~ai_os_kernel.context_manager.models.AssembledContext`/
  :class:`~ai_os_kernel.context_manager.models.ContextItem`/
  :class:`~ai_os_kernel.context_manager.models.SourceRef`/
  :class:`~ai_os_kernel.context_manager.models.SourceType` — a
  deliberately reduced slice of context_manager.md §5/§6's documented
  request/response contract (see that module's own docstring for
  exactly which fields are present, absent, and why); ``ContextRequest``
  now also carries an optional ``token_budget``.
- :class:`~ai_os_kernel.context_manager.resolvers.ContextSourceResolver`
  (``Protocol``) / :class:`~ai_os_kernel.context_manager.resolvers.
  WorkflowStateResolver` — the one real resolver, reading a workflow
  instance's own declared ``inputs`` (see that module's own docstring
  for why this also stands in for context_manager.md §3's
  "User-provided inputs").
- :class:`~ai_os_kernel.context_manager.manager.ContextManager`
  (``Protocol``) / :class:`~ai_os_kernel.context_manager.manager.
  DefaultContextManager` — queries every configured resolver,
  concatenates their items, and now enforces a real token budget (a
  per-request override, or the assembler's own configured default):
  admits items by descending ``relevance_score`` (a stable sort, so
  ties preserve resolver order — ADR-0022), greedily including
  whatever still fits, and reports how many did not via
  ``items_excluded_count`` — the Size & Token Budget Enforcer
  context_manager.md §4/§6 documents. Still no filtering or ranking as
  first-class capabilities of their own (see that module's own
  docstring for why).

Not yet implemented: Knowledge Manager, Memory Manager, and AI Context
Pack resolvers (those Kernel components do not exist yet); a Runtime
Configuration resolver (the Configuration Manager is real but
deliberately deferred — one real resolver is enough to prove the flow);
a Context Filter/Ranker as its own component (distinct from budget
enforcement's reuse of ``relevance_score`` as a tie-break);
``required_context_types``/experiment or run identifiers on
``ContextRequest``; ``index_generation`` on ``AssembledContext`` (no
retrieval index exists to pin); and a Context Audit Logger persistence
writer (data_model.md defines no schema for a context assembly at all
— see the roadmap documentation for this finding, reported rather than
silently resolved).

**Documentation ambiguity, not silently resolved:** context_manager.md
§6 does not classify whether workflow/user-provided input is
``trusted`` or ``untrusted`` — only "repository content, ingested
documents, tool output, and web content" are given as ``untrusted``
examples. :class:`~ai_os_kernel.context_manager.resolvers.
WorkflowStateResolver` classifies it ``untrusted`` as a reasoned default
(see that module's own docstring); a future revision of
context_manager.md should state this explicitly.
"""

from ai_os_kernel.context_manager.manager import ContextManager, DefaultContextManager
from ai_os_kernel.context_manager.models import (
    AssembledContext,
    ContextItem,
    ContextRequest,
    SourceRef,
    SourceType,
)
from ai_os_kernel.context_manager.resolvers import ContextSourceResolver, WorkflowStateResolver

__all__ = [
    "AssembledContext",
    "ContextItem",
    "ContextManager",
    "ContextRequest",
    "ContextSourceResolver",
    "DefaultContextManager",
    "SourceRef",
    "SourceType",
    "WorkflowStateResolver",
]
