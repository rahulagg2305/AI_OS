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
  ``platform.sandbox.run_command``.

**Not wired into anything yet.** ``kernel/bootstrap.py``,
``EntrypointLoader``, and every pack are untouched by this step —
constructing and injecting these adapters into a real ``PackContext``
is step 6b (the zero-argument entrypoint blocker); migrating any agent
onto them is steps 9–14. This package only proves the adapters exist
and genuinely work in isolation, against real underlying Kernel
objects.
"""

from __future__ import annotations
