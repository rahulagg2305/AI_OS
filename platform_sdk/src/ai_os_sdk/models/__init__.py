"""Pydantic v2 boundary models — every value that crosses the pack/
platform boundary (``platform_sdk.md`` §4).

Empty in this step. Filled in, one file per concern, by
``platform_sdk_v1_scope.md``'s steps 2–7:

- ``common.py``   — ``ArtifactRef``, ``TraceContext``, ``SecurityContext``,
  ``StepBudget`` (§4.1)                                          — step 2
- ``agent.py``    — ``AgentRequest``, ``AgentResult`` (§4.2)      — step 3
- ``tool.py``     — ``ToolRequest``, ``ToolResult`` (§4.3)        — step 3
- ``llm.py``      — ``LLMRequest``, ``LLMResponse``, ``UsageRecord``,
  ``ProviderCapabilities``, and related shapes (§5.1)             — step 4
- ``prompt.py``   — ``RenderedPrompt``, ``PromptDefinition`` (§5.2) — step 5
- ``secret.py``   — ``SecretValue`` (§5.9)                        — step 6
- ``context.py``  — ``ContextRequest``, ``AssembledContext``,
  ``ContextItem``, ``SourceRef`` (§5.3)                           — step 7
- ``pack.py``     — ``PackContext``, ``PackRegistration``,
  ``HealthReport`` (§6, §7)                                       — step 7

The ``AiOsError`` → ``StructuredError`` exception hierarchy (§4.4) lives
in :mod:`ai_os_sdk.errors`, not here, since it is raised, not merely
carried across the boundary as data.
"""

from __future__ import annotations
