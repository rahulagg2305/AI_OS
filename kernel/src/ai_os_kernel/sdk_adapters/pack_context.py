"""Builds a real, permission-gated
:class:`~ai_os_kernel.capability_manager.pack_contract.PackContext` from
the three step 6a adapters (``platform_sdk_v1_scope.md`` step 6b).

**The "no over-provisioning" rule, made concrete.** ``platform_sdk.md``
§6: "Attributes are present only if the manifest declared the
corresponding capability and it was granted." This module is where that
rule is actually enforced for the three capabilities that exist today —
an entrypoint whose own declared ``permissions`` do not include
``llm:invoke`` gets ``llm=None``/``prompts=None`` back, full stop, even
if a real ``DispatchingLLMGateway``/``PromptEngine`` was passed in; the
same holds for ``tools``/``sandbox:execute``. There is no "grant" step
independent of manifest declaration yet — Security Manager enforcement
of roles/permissions (ADR-0023) is 0%-built — so this module treats
"declared" as the current, honest stand-in for "granted," the identical
simplification already implicit everywhere else permissions are
mentioned in this codebase today.

**Pass the *entrypoint's own* declared ``permissions``, not the pack's
aggregate list.** The real manifest
(``capability_packs/software-engineering/manifest.yaml``) declares
``permissions: [llm:invoke, sandbox:execute]`` at the pack level, but
each individual agent declares its own, narrower subset — ``qa-test``
declares only ``sandbox:execute`` (it makes no LLM call at all);
``requirements-analyst``/``architecture`` declare only ``llm:invoke``
(they cause no sandboxed side effect). Building every agent's
``PackContext`` from the pack's aggregate permissions instead of each
agent's own would hand every agent in the pack every capability *any*
agent in it was granted — exactly the over-provisioning §6 prohibits.
This function is deliberately called once per entrypoint, with that one
entrypoint's own declared list.

**Why ``llm:invoke`` grants both ``llm`` and ``prompts`` together, not
two independent permissions.** The closed permission vocabulary
(``manifest_schema.md``) has no separate ``prompts:*`` permission, and
rendering a prompt has no purpose for an entrypoint that cannot then
send it to an LLM — so this module reads ``llm:invoke`` as covering both.
This is a real, load-bearing design decision, not an oversight, and
belongs eventually in ``platform_sdk.md`` §6's own text as a documented
permission-to-capability mapping — recorded here, concretely, as that
future step's input.
"""

from __future__ import annotations

from collections.abc import Collection

from ai_os_kernel.capability_manager.pack_contract import PackContext
from ai_os_kernel.git_integration.service import GitIntegrationService
from ai_os_kernel.llm_gateway.gateway import LLMGateway as KernelLLMGatewayProtocol
from ai_os_kernel.prompt_engine.renderer import PromptEngine
from ai_os_kernel.sandbox.executor import SandboxExecutor
from ai_os_kernel.sdk_adapters.llm_gateway_adapter import LLMGatewayAdapter
from ai_os_kernel.sdk_adapters.prompt_registry_adapter import PromptRegistryAdapter
from ai_os_kernel.sdk_adapters.tool_invoker_adapter import ToolInvokerAdapter

_LLM_PERMISSION = "llm:invoke"
_SANDBOX_PERMISSION = "sandbox:execute"


def build_pack_context(
    *,
    pack_id: str,
    pack_version: str,
    permissions: Collection[str],
    llm_gateway: KernelLLMGatewayProtocol | None = None,
    prompt_engine: PromptEngine | None = None,
    sandbox: SandboxExecutor | None = None,
    git_service: GitIntegrationService | None = None,
) -> PackContext:
    """Build the real ``PackContext`` one entrypoint should receive,
    given *that entrypoint's own* declared ``permissions`` (see this
    module's own docstring for why the pack's aggregate list is the
    wrong thing to pass here).

    Raises :class:`ValueError` if a permission is declared but the
    matching real Kernel object was not supplied — a caller granting a
    permission it cannot actually back is a genuine configuration error,
    not something to silently downgrade to ``None``.

    ``git_service`` (``P03-S04-M31-T04``) is forwarded to
    :class:`~ai_os_kernel.sdk_adapters.tool_invoker_adapter.
    ToolInvokerAdapter` unchanged when ``sandbox:execute`` is granted —
    optional, defaulting to ``None`` (no real Git tool ids reachable),
    the identical "absent means unaffected" shape every other optional
    capability in this codebase already establishes. Deliberately not
    gated by its own separate permission check here: the closed
    manifest vocabulary's ``git:write`` is a real, disclosed, deferred
    enforcement gap (see ``git_integration.md``'s own Implementation
    Status) — today, exactly like ``platform.sandbox.run_command``,
    reachability is gated only by ``sandbox:execute``.
    """
    llm: KernelLLMGatewayProtocol | LLMGatewayAdapter | None = None
    prompts: PromptEngine | PromptRegistryAdapter | None = None
    if _LLM_PERMISSION in permissions:
        if llm_gateway is None or prompt_engine is None:
            raise ValueError(
                f"permissions declare {_LLM_PERMISSION!r} but no llm_gateway/prompt_engine "
                "was supplied to build_pack_context() — a granted permission this builder "
                "cannot actually back is a configuration error, not a silent no-op"
            )
        llm = LLMGatewayAdapter(llm_gateway)
        prompts = PromptRegistryAdapter(prompt_engine)

    tools: ToolInvokerAdapter | None = None
    if _SANDBOX_PERMISSION in permissions:
        if sandbox is None:
            raise ValueError(
                f"permissions declare {_SANDBOX_PERMISSION!r} but no sandbox was supplied to "
                "build_pack_context() — a granted permission this builder cannot actually "
                "back is a configuration error, not a silent no-op"
            )
        tools = ToolInvokerAdapter(sandbox, git_service=git_service)

    return PackContext(
        pack_id=pack_id,
        pack_version=pack_version,
        llm=llm,
        prompts=prompts,
        tools=tools,
    )
