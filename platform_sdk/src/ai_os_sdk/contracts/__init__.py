"""Protocol definitions — the SDK's interfaces (``platform_sdk.md`` §4.2,
§4.3, §5, §7).

Empty in this step. Filled in, one file per interface, by
``platform_sdk_v1_scope.md``'s steps 3–7:

- ``agent.py``            — ``Agent`` Protocol (§4.2)                — step 3
- ``tool.py``              — ``Tool`` Protocol (§4.3)                 — step 3
- ``llm_gateway.py``       — ``LLMGateway`` Protocol (§5.1)           — step 4
- ``prompt_registry.py``   — ``PromptRegistry`` Protocol (§5.2)       — step 5
- ``secret_resolver.py``   — ``SecretResolver`` Protocol (§5.9)       — step 6
- ``tool_invoker.py``      — ``ToolInvoker`` Protocol (§5.6)          — step 6
- ``context_service.py``   — ``ContextService`` Protocol (§5.3) —
  declared but with no real caller yet; see the scope document §2.2
  for why only its boundary models, not this Protocol's ``assemble()``
  method, are exercised by any current agent               — step 7
- ``capability_pack.py``   — ``CapabilityPack`` Protocol (§7)         — step 7

The other 10 documented interfaces (``RetrievalService``,
``MemoryService``, ``EventBus``, ``ConfigService``, ``StorageService``,
``WorkspaceService``, ``Telemetry``, ``TraceabilityService``,
``QualityGateRegistry``, ``SpeechGateway``) are deliberately deferred —
none has any real usage today; see ``platform_sdk_v1_scope.md`` §7,
Non-goals.
"""

from __future__ import annotations
