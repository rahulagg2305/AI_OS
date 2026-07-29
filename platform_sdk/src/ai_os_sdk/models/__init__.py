"""Pydantic v2 boundary models — every value that crosses the pack/
platform boundary (``platform_sdk.md`` §4).

Real as of ``platform_sdk_v1_scope.md`` step 5: the four shared models
in :mod:`ai_os_sdk.models.common` (step 2), the ``LLMGateway`` models in
:mod:`ai_os_sdk.models.llm` (step 4), and ``RenderedPrompt`` in
:mod:`ai_os_sdk.models.prompt` (step 5) all exist and are re-exported
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
  consumer under. ``ToolResult`` is not dropped — it moves to step 6
  where its consumer, ``ToolInvoker``, lives.
- ``secret.py``/``SecretValue`` — §2.3: the pack's manifest declares no
  secret permission, so granting it one would violate §6.
- ``PromptDefinition`` (§5.2) — the return type of the deferred
  ``get()`` method; no implementation of stored-prompt lookup exists at
  any layer.

The ``AiOsError`` → ``StructuredError`` hierarchy (§4.4) lives in
:mod:`ai_os_sdk.errors`, not here, since it is raised rather than merely
carried across the boundary as data. That module imports *this* one;
never the reverse.
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
    "TraceContext",
    "UsageRecord",
    "is_artifact_id",
]
