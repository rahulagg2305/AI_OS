"""The ``ContextService`` Protocol (``platform_sdk.md`` §5.3,
``platform_sdk_v1_scope.md`` step 7).

**Declared, with no adapter built behind it — a deliberate, documented
scope boundary, not an oversight.** Unlike ``LLMGateway``/
``PromptRegistry``/``ToolInvoker`` (steps 4–6, each with a real
Kernel-side adapter built in step 6a), no agent calls ``.assemble()``
today — ``AgentStepExecutor`` already assembles context itself and hands
the result to an agent via ``AgentRequest.context``, so there is no real
caller this Protocol's own method needs to serve yet. See
:mod:`ai_os_sdk.models.context`'s own module docstring for the full
reasoning and the dated reconciliation decision behind its boundary
models.

**Structural compatibility with a real class is still verified below —
this differs from a genuine "nothing to check" situation.** Unlike
``PromptRegistry``/``ToolInvoker`` (from-scratch designs with no real
Kernel counterpart at all), a real, working
:class:`~ai_os_kernel.context_manager.manager.DefaultContextManager`
already implements exactly this signature
(``async def assemble(self, request: ContextRequest) -> AssembledContext``).
This module's own tests prove it satisfies this Protocol via
``isinstance`` — the identical "prove against a real class, not a mock"
discipline steps 3–4 already established for ``Agent``/``Tool``/
``LLMGateway`` — even though no Kernel-side *adapter* wraps it, since
building one has no real caller to justify it yet.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ai_os_sdk.models.context import AssembledContext, ContextRequest


@runtime_checkable
class ContextService(Protocol):
    """The sole seam through which context is assembled before invoking
    an agent (``platform_sdk.md`` §5.3). ``@runtime_checkable`` so a
    real, already-existing class can be checked against it by
    ``isinstance``, exactly as this module's own docstring describes."""

    async def assemble(self, request: ContextRequest) -> AssembledContext: ...
