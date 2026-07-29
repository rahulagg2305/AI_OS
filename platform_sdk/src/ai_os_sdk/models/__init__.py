"""Pydantic v2 boundary models — every value that crosses the pack/
platform boundary (``platform_sdk.md`` §4).

Real as of ``platform_sdk_v1_scope.md`` step 6: the four shared models
in :mod:`ai_os_sdk.models.common` (step 2), the ``LLMGateway`` models in
:mod:`ai_os_sdk.models.llm` (step 4), ``RenderedPrompt`` in
:mod:`ai_os_sdk.models.prompt` (step 5), and the tool-invocation models
in :mod:`ai_os_sdk.models.tool` (``TrustTier``, ``ToolDescriptor``,
``ToolStatus``, ``ToolResult`` — step 6) all exist and are re-exported
here. The rest arrive with the Protocol each belongs to:

- ``context.py``  — ``ContextRequest``, ``AssembledContext``,
  ``ContextItem``, ``SourceRef`` (§5.3)                            — step 7
- ``pack.py``     — ``PackContext``, ``PackRegistration``,
  ``HealthReport`` (§6, §7)                                        — step 7

**Dropped from v1.0.0, not merely deferred:**

- ``AgentRequest``/``AgentResult`` (§4.2) and ``ToolRequest`` (§4.3) —
  ``platform_sdk_v1_scope.md`` step 2a narrowed ``Agent``/``Tool`` to
  the dict-based ``execute(inputs) -> outputs`` shape (see the decision
  blocks in ``platform_sdk.md`` §4.2/§4.3), which these models have no
  consumer under. ``ToolResult`` was not dropped with them — it is real
  as of this step, alongside its consumer, ``ToolInvoker``.
- ``secret.py``/``SecretValue`` — §2.3: the pack's manifest declares no
  secret permission, so granting it one would violate §6.
- ``PromptDefinition`` (§5.2) — the return type of the deferred
  ``get()`` method; no implementation of stored-prompt lookup exists at
  any layer.

The ``AiOsError`` exception hierarchy (§4.4) lives in
:mod:`ai_os_sdk.errors`, not here, since it is raised rather than merely
carried across the boundary as data. **One correction to this rule,
made in step 6:** ``ErrorCategory``/``StructuredError`` themselves are
data shapes, not raised exceptions, and now live in
:mod:`ai_os_sdk.models.error` — moved out of ``ai_os_sdk.errors``
specifically so that a *model* (:class:`~ai_os_sdk.models.tool.ToolResult`)
could depend on ``StructuredError`` without ``ai_os_sdk.models``
importing ``ai_os_sdk.errors``, which would cycle back through
``ai_os_sdk.errors``'s own dependency on
:class:`~ai_os_sdk.models.common.TraceContext`. ``ai_os_sdk.errors``
still re-exports both names unchanged; only the exception classes that
are actually *raised* (``AiOsError`` and its six subclasses) remain
defined there.
"""

from __future__ import annotations

from ai_os_sdk.models.common import (
    ARTIFACT_ID_PATTERN,
    V1_TENANT_ID,
    ArtifactRef,
    SecurityContext,
    StepBudget,
    TraceContext,
    is_artifact_id,
)
from ai_os_sdk.models.llm import (
    LLMRequest,
    LLMResponse,
    Message,
    MessageRole,
    ProviderCapabilities,
    StopReason,
    UsageRecord,
)
from ai_os_sdk.models.prompt import RenderedPrompt
from ai_os_sdk.models.tool import ToolDescriptor, ToolResult, ToolStatus, TrustTier

__all__ = [
    "ARTIFACT_ID_PATTERN",
    "V1_TENANT_ID",
    "ArtifactRef",
    "LLMRequest",
    "LLMResponse",
    "Message",
    "MessageRole",
    "ProviderCapabilities",
    "RenderedPrompt",
    "SecurityContext",
    "StepBudget",
    "StopReason",
    "ToolDescriptor",
    "ToolResult",
    "ToolStatus",
    "TraceContext",
    "TrustTier",
    "UsageRecord",
    "is_artifact_id",
]
