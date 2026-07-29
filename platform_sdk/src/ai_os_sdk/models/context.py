"""``ContextService`` boundary models (``platform_sdk.md`` §5.3,
``platform_sdk_v1_scope.md`` step 7).

**Landed as boundary models only — no agent calls ``.assemble()``
themselves.** ``AgentStepExecutor`` (Workflow Engine) already assembles
context and hands it to the agent via ``AgentRequest.context``
(``agent_architecture.md``'s Invocation Lifecycle, already real —
``step_executor.py``'s ``AgentStepExecutor._invocation_inputs``). Two
real pack agents (``agents/documentation.py``, ``agents/verification.py``)
only import the Kernel's own ``AssembledContext`` to type-annotate what
they receive from that lifecycle, never the assembly path itself —
``platform_sdk_v1_scope.md`` §2.2's own note on this. These models are
that import's future SDK-side target; :class:`~ai_os_sdk.contracts.
context_service.ContextService`'s own ``assemble()`` method has no real
implementation behind it anywhere, by design, matching v1.0.0's own
approved scope for this interface exactly.

**Every field checked against the real Kernel shape before writing this
— a genuine, dated reconciliation decision, the same discipline already
applied to every other real interface in this initiative
(``platform_sdk.md`` §4.2/§4.3/§5.1/§5.2/§5.6), even though no formal
decision block existed here before this step.**

> **🔵 v1.0.0 RECONCILIATION DECISION (2026-07-29): NARROW `ContextRequest`
> and `AssembledContext` to the real, already-documented reduced Kernel
> shape; KEEP `ContextItem` (already full parity); DESIGN `SourceRef`
> (the compact spec names no fields for it); NARROW `SourceType` to the
> one real resolver.**
>
> - **`ContextRequest`**: the documented shape carries `required_types:
>   ContextType[]`, `query: str | None`, and `filters: dict | None` in
>   addition to `workflow_id`/`step_id`/`agent_id`/`token_budget`. The
>   real `ai_os_kernel.context_manager.models.ContextRequest`
>   (verified by reading it, not assumed) carries only the latter four —
>   its own docstring already explains why the other three are absent as
>   *fields*, not present as always-`None` ones: `required_types` has no
>   declared source anywhere in this codebase (`workflow_architecture.md`'s
>   Step Contract names no field for which context types a step needs),
>   and no experiment/query mechanism exists to back `query`/`filters`
>   either. Populating them here with an unused default would be exactly
>   the "placeholder architecture" the Kernel's own model already refuses
>   to be — this reconciliation inherits that refusal rather than
>   re-introducing the gap one layer up.
> - **`AssembledContext`**: the documented shape adds `index_generation`
>   to the four fields kept below. The real Kernel model omits it for a
>   verified, real reason: `index_generation` exists to pin a retrieval
>   index generation for reproducibility (ADR-0022), and there is no
>   retrieval index anywhere in this codebase yet (no Knowledge Manager,
>   no Memory Manager). A fabricated value would misrepresent a
>   reproducibility guarantee this slice cannot provide — dropped here
>   for the identical reason, not merely copied without re-checking.
> - **`ContextItem`**: the real Kernel model already implements the full
>   documented shape (`content`/`provenance`/`relevance_score`/
>   `token_count`/`trust`) — its own docstring says so explicitly. Kept
>   verbatim; there is nothing to narrow.
> - **`SourceRef`**: the compact spec text names only that `ContextItem.
>   provenance` is a `SourceRef`, with no further field breakdown — there
>   is nothing to reconcile against, the same "design, not narrow or
>   extend" situation `ToolInvoker` was in (§5.6). The real Kernel shape
>   (`source_type`/`identifier`, no `version`) is kept as this model's
>   real design for the identical, verified reason its own docstring
>   gives: Workflow State has no versioning concept a future Knowledge/
>   Memory resolver's own documents might have, and an unused field for a
>   capability that does not exist yet would be a placeholder.
> - **`SourceType`**: the real Kernel enum has exactly one member,
>   `WORKFLOW_STATE` — context_manager.md §4 documents five source
>   resolvers, but only one is real. Narrowed to that one member; a
>   future Knowledge/Memory/AI-Context-Pack/Configuration resolver adds
>   its own member additively, the same precedent as every other reduced
>   enum in this codebase.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SourceType(StrEnum):
    """Which source resolver produced a given item
    (``context_manager.md`` §4's "Source Resolvers"). Only the first of
    five documented resolvers is real; see this module's own
    reconciliation decision block."""

    WORKFLOW_STATE = "workflow_state"


class SourceRef(BaseModel):
    """Where one :class:`ContextItem` came from. See this module's own
    reconciliation decision block for why ``version`` is absent."""

    model_config = ConfigDict(frozen=True)

    source_type: SourceType
    identifier: str


class ContextItem(BaseModel):
    """One unit of assembled context — the full documented §5.3 shape,
    kept verbatim (see this module's own reconciliation decision
    block)."""

    model_config = ConfigDict(frozen=True)

    content: str
    provenance: SourceRef
    relevance_score: float
    token_count: int
    trust: Literal["trusted", "untrusted"]


class ContextRequest(BaseModel):
    """See this module's own reconciliation decision block for which of
    §5.3's documented fields this narrowed shape carries, and why."""

    model_config = ConfigDict(frozen=True)

    workflow_id: str
    step_id: str
    agent_id: str | None = None
    token_budget: int | None = Field(default=None, gt=0)


class AssembledContext(BaseModel):
    """See this module's own reconciliation decision block for why
    ``index_generation`` is absent from this narrowed shape."""

    model_config = ConfigDict(frozen=True)

    items: list[ContextItem]
    total_tokens: int
    sources_queried: list[SourceType]
    items_excluded_count: int
    assembly_id: str
