"""Protocol definitions — the SDK's interfaces (``platform_sdk.md`` §4.2,
§4.3, §5, §7).

**Read the *v1.0.0 Reconciliation Decision* block in each corresponding
section of ``platform_sdk.md`` before treating its prose as the shape
built here.** Five interfaces carry one (recorded 2026-07-29,
``platform_sdk_v1_scope.md`` step 2a), and where a block and the prose
around it disagree, the block governs v1.0.0.

Partially real as of step 6: ``Agent``/``Tool`` (step 3), ``LLMGateway``
(step 4, narrowed to ``complete``/``capabilities`` — the two methods the
real ``DispatchingLLMGateway`` implements), ``PromptRegistry`` (step 5,
the documented keyword call style — the one interface where the
*specification* was kept over the Kernel's own request-object shape;
see its decision block), and now ``ToolInvoker`` (step 6, a from-scratch
design grounded in the platform-provided
:data:`~ai_os_sdk.contracts.tool_invoker.PLATFORM_SANDBOX_RUN_COMMAND`
tool — see its decision block). The rest arrive in order:

- ``context_service.py``   — ``ContextService`` (§5.3); its boundary
  models are what v1.0.0 actually needs, not its method            — step 7
- ``capability_pack.py``   — ``CapabilityPack`` (§7)                — step 7

**Deferred past v1.0.0, deliberately:** ``SecretResolver`` (§5.9 — the
one real pack declares no secret permission, and §6 grants a
``PackContext`` attribute only for a declared capability), plus the ten
interfaces whose underlying subsystem is 0%-built or a docstring-only
stub (``RetrievalService``, ``MemoryService``, ``EventBus``,
``ConfigService``, ``StorageService``, ``WorkspaceService``,
``Telemetry``, ``TraceabilityService``, ``QualityGateRegistry``,
``SpeechGateway``). See ``platform_sdk_v1_scope.md`` §2.3 and §7.
"""

from __future__ import annotations

from ai_os_sdk.contracts.agent import Agent
from ai_os_sdk.contracts.llm_gateway import LLMGateway
from ai_os_sdk.contracts.prompt_registry import PromptRegistry
from ai_os_sdk.contracts.tool import Tool, TrustTier
from ai_os_sdk.contracts.tool_invoker import (
    PLATFORM_SANDBOX_RUN_COMMAND,
    PLATFORM_SANDBOX_RUN_COMMAND_DESCRIPTOR,
    ToolInvoker,
)

__all__ = [
    "PLATFORM_SANDBOX_RUN_COMMAND",
    "PLATFORM_SANDBOX_RUN_COMMAND_DESCRIPTOR",
    "Agent",
    "LLMGateway",
    "PromptRegistry",
    "Tool",
    "ToolInvoker",
    "TrustTier",
]
