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
tool — see its decision block).

Also real as of step 6b: ``PackContextReceiver``
(``entrypoint_context.py``) — **not** §7's own ``CapabilityPack``/
``PackContext`` entry-point contract, but the narrower, distinct
injection mechanism a zero-argument-constructible entrypoint uses to
receive whichever real context it was granted, once, before first real
use — the generalized form of the lazy-build workaround every real
Software Engineering pack agent already uses today. See its own module
docstring for the full reasoning, including why it is typed ``context:
Any`` rather than ``context: PackContext``.

Real as of step 7: ``ContextService`` (``context_service.py``) — its
boundary models (:mod:`ai_os_sdk.models.context`) are what v1.0.0 needs,
not a real implementation behind its one method; structural
compatibility is still proven against the real, already-working
``DefaultContextManager`` — and ``CapabilityPack``/``PackContext``/
``PackRegistration``/``HealthReport`` (``capability_pack.py``, §6/§7) —
relocated here from ``ai_os_kernel.capability_manager.pack_contract``,
additively, per step 6b's own record. **Deliberately not split into
``ai_os_sdk.models`` the way every other boundary model was** — see
``capability_pack.py``'s own module docstring for the real layering
reason (these types reference other Protocols by nature, and ``models/``
must never import ``contracts/``).

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
from ai_os_sdk.contracts.capability_pack import (
    CapabilityPack,
    HealthReport,
    PackContext,
    PackRegistration,
)
from ai_os_sdk.contracts.context_service import ContextService
from ai_os_sdk.contracts.entrypoint_context import PackContextReceiver
from ai_os_sdk.contracts.llm_gateway import LLMGateway
from ai_os_sdk.contracts.prompt_registry import PromptRegistry
from ai_os_sdk.contracts.tool import Tool, TrustTier
from ai_os_sdk.contracts.tool_invoker import (
    PLATFORM_PYTHON_INTERPRETER,
    PLATFORM_SANDBOX_RUN_COMMAND,
    PLATFORM_SANDBOX_RUN_COMMAND_DESCRIPTOR,
    ToolInvoker,
)

__all__ = [
    "PLATFORM_PYTHON_INTERPRETER",
    "PLATFORM_SANDBOX_RUN_COMMAND",
    "PLATFORM_SANDBOX_RUN_COMMAND_DESCRIPTOR",
    "Agent",
    "CapabilityPack",
    "ContextService",
    "HealthReport",
    "LLMGateway",
    "PackContext",
    "PackContextReceiver",
    "PackRegistration",
    "PromptRegistry",
    "Tool",
    "ToolInvoker",
    "TrustTier",
]
