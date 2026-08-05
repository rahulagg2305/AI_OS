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
from ai_os_kernel.llm_gateway.call_recorder import LLMCallRecorder
from ai_os_kernel.llm_gateway.gateway import LLMGateway as KernelLLMGatewayProtocol
from ai_os_kernel.prompt_engine.renderer import PromptEngine
from ai_os_kernel.sandbox.executor import SandboxExecutor
from ai_os_kernel.sdk_adapters.llm_gateway_adapter import LLMGatewayAdapter
from ai_os_kernel.sdk_adapters.prompt_registry_adapter import PromptRegistryAdapter
from ai_os_kernel.sdk_adapters.tool_invoker_adapter import ToolInvokerAdapter

_LLM_PERMISSION = "llm:invoke"
_SANDBOX_PERMISSION = "sandbox:execute"
_GIT_PERMISSION = "git:write"


def build_pack_context(
    *,
    pack_id: str,
    pack_version: str,
    permissions: Collection[str],
    llm_gateway: KernelLLMGatewayProtocol | None = None,
    prompt_engine: PromptEngine | None = None,
    sandbox: SandboxExecutor | None = None,
    git_service: GitIntegrationService | None = None,
    agent_id: str | None = None,
    call_recorder: LLMCallRecorder | None = None,
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
    ToolInvokerAdapter` only when the entrypoint's own declared
    ``permissions`` include ``git:write`` **and** ``sandbox:execute``
    (``P03-S01-M24-T03``, closing the disclosed gap the previous version
    of this docstring named) — optional, defaulting to ``None`` (no real
    Git tool ids reachable) otherwise, the identical "absent means
    unaffected" shape every other optional capability in this codebase
    already establishes. This is deliberately the *declared-permission*
    term of ADR-0023's monotonic-narrowing chain, not the full
    principal ∩ workflow ∩ agent ∩ tool intersection
    (:mod:`~ai_os_kernel.security_manager.narrowing`) — the same,
    already-disclosed partial scope :func:`~ai_os_kernel.
    capability_manager.permission_grant.over_granted_permissions` (the
    pack-grant term) already carries: no ``SecurityContext``/``Principal``
    reaches this call site (:class:`~ai_os_kernel.sdk_adapters.
    tool_invoker_adapter.ToolInvokerAdapter`'s own docstring: "v1.0.0's
    ``ToolInvoker`` Protocol carries no trace or security context
    parameter at all"), so the principal term cannot be computed here —
    widening that Protocol is a distinct, later SDK step, not this one.

    **Deliberately not a `ValueError` when `git:write` is declared but
    `git_service` is absent — unlike the `llm`/`sandbox` checks above.**
    Those two raise because a real caller declaring `llm:invoke`/
    `sandbox:execute` always means it right now. `git:write` is
    different: the Git Push Agent's own manifest entry declares it
    unconditionally (a static fact about what the agent *can* do), while
    whether a real `GitIntegrationService` backs it is an environment-
    dependent fact (`AIOS_GIT_REMOTE_URL` — `P03-S01-M24-T02`) that is
    legitimately absent in every environment today. Raising here would
    make ordinary, current-day resolution of the Git Push Agent fail
    everywhere `git_service` is not yet configured — exactly the
    regression this permission check must not cause. `git_service=None`
    already means "no real Git tool ids reachable," the identical safe
    default `ToolInvokerAdapter`/`GitPushAgentEntrypoint` already handle
    (the latter raises its own clear `GitPushInstructionError` if a
    caller configured a real `remote_url` but the injected `ToolInvoker`
    still exposes no Git tools — the genuine misconfiguration case is
    still caught, just one layer up, where the caller's real intent
    (a configured `remote_url`) is actually known).

    **``agent_id``/``call_recorder`` (``P04-S01-M12-T10``) are forwarded
    only to the constructed ``LLMGatewayAdapter``** — real call
    recording for this entrypoint's own LLM calls, reusing
    ``SqlLLMCallRecorder`` unchanged (see that adapter's own module
    docstring for the full design). Both default to ``None``, so every
    existing caller is unaffected; a *tool*'s own resolution never
    passes ``agent_id`` either (a tool's id is not a real
    ``catalog.agents`` foreign key, so recording under it would be
    incorrect, not merely unimplemented).
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
        llm = LLMGatewayAdapter(llm_gateway, agent_id=agent_id, call_recorder=call_recorder)
        prompts = PromptRegistryAdapter(prompt_engine)

    tools: ToolInvokerAdapter | None = None
    if _SANDBOX_PERMISSION in permissions:
        if sandbox is None:
            raise ValueError(
                f"permissions declare {_SANDBOX_PERMISSION!r} but no sandbox was supplied to "
                "build_pack_context() — a granted permission this builder cannot actually "
                "back is a configuration error, not a silent no-op"
            )
        tools = ToolInvokerAdapter(
            sandbox,
            git_service=git_service if _GIT_PERMISSION in permissions else None,
        )

    return PackContext(
        pack_id=pack_id,
        pack_version=pack_version,
        llm=llm,
        prompts=prompts,
        tools=tools,
    )
