"""Pydantic v2 boundary models — every value that crosses the pack/
platform boundary (``platform_sdk.md`` §4).

Partially real as of ``platform_sdk_v1_scope.md`` step 2: the four
shared models in :mod:`ai_os_sdk.models.common` exist and are
re-exported here. The rest arrive with the Protocol each belongs to:

- ``agent.py``    — ``AgentRequest``, ``AgentResult`` (§4.2)       — step 3
- ``tool.py``     — ``ToolRequest``, ``ToolResult`` (§4.3)         — step 3
- ``llm.py``      — ``LLMRequest``, ``LLMResponse``, ``UsageRecord``,
  ``ProviderCapabilities``, and related shapes (§5.1)              — step 4
- ``prompt.py``   — ``RenderedPrompt``, ``PromptDefinition`` (§5.2) — step 5
- ``context.py``  — ``ContextRequest``, ``AssembledContext``,
  ``ContextItem``, ``SourceRef`` (§5.3)                            — step 7
- ``pack.py``     — ``PackContext``, ``PackRegistration``,
  ``HealthReport`` (§6, §7)                                        — step 7

*(``secret.py``/``SecretValue`` was dropped from v1.0.0 —
``platform_sdk_v1_scope.md`` §2.3: the pack's manifest declares no
secret permission, so granting it one would violate §6.)*

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

__all__ = [
    "ARTIFACT_ID_PATTERN",
    "V1_TENANT_ID",
    "ArtifactRef",
    "SecurityContext",
    "StepBudget",
    "TraceContext",
    "is_artifact_id",
]
