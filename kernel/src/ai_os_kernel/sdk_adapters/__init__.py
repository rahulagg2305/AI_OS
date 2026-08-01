"""The Kernel's own implementations of the Platform SDK's Protocols
(``docs/03_architecture/platform/platform_sdk.md``,
``platform_sdk_v1_scope.md`` step 6a).

**This is the boundary where "the Kernel implements the SDK" actually
happens.** ``platform_sdk.md`` §2 rule 1 makes ``ai-os-sdk`` the
dependency floor — it depends on nothing else, and everything else may
depend on it. The Kernel is exactly that "everything else": it now
declares a real dependency on ``ai-os-sdk`` (``kernel/pyproject.toml``)
and this package is where that dependency is spent. Nothing in
``ai_os_sdk`` imports anything from here, or could.

Three adapters, one per Protocol proven structurally compatible or
designed in steps 3–6:

- :mod:`llm_gateway_adapter` — wraps a real
  :class:`~ai_os_kernel.llm_gateway.gateway.DispatchingLLMGateway`
  to satisfy :class:`ai_os_sdk.contracts.LLMGateway`.
- :mod:`prompt_registry_adapter` — wraps a real
  :class:`~ai_os_kernel.prompt_engine.renderer.PromptEngine` to satisfy
  :class:`ai_os_sdk.contracts.PromptRegistry`, implementing the
  conversion step 5's tests proved lossless.
- :mod:`tool_invoker_adapter` — wraps a real
  :class:`~ai_os_kernel.sandbox.executor.SandboxExecutor` to satisfy
  :class:`ai_os_sdk.contracts.ToolInvoker`, exposing
  ``platform.sandbox.run_command`` — and, when constructed with a real
  :class:`~ai_os_kernel.workflow_engine.registry.ToolRegistry`
  (``P02-S05-M18-T03``), resolves and invokes any other manifest-declared
  ``tool_id`` through that registry's own real path, not an internal
  shim.

**As of step 6b, one more module assembles those three into a real,
permission-gated context:**

- :mod:`pack_context` — :func:`~ai_os_kernel.sdk_adapters.pack_context.build_pack_context`
  builds a real :class:`~ai_os_kernel.capability_manager.pack_contract.PackContext`
  from an entrypoint's own declared permissions, granting ``llm``/
  ``prompts``/``tools`` only when the matching permission was declared —
  never over-provisioned. Injecting the result into a zero-argument
  entrypoint uses the new :class:`ai_os_sdk.contracts.PackContextReceiver`
  Protocol, which any entrypoint may implement without this package or
  the Kernel at all.

**Still not wired into production.** ``kernel/bootstrap.py``,
``EntrypointLoader``, ``SqlAgentRegistry``, and every pack are untouched
by this step — a real caller invoking :func:`build_pack_context` and
then ``bind_pack_context`` for every entrypoint ``SqlAgentRegistry``
resolves is production wiring, deliberately deferred to whichever future
step performs it (see ``platform_sdk_v1_scope.md`` step 6b's own record
for why). This package only proves the mechanism exists and genuinely
works — step 6a in isolation, step 6b end-to-end through a **test**
entrypoint — against real underlying Kernel objects; migrating any real
agent onto it is steps 9–14.
"""

from __future__ import annotations
