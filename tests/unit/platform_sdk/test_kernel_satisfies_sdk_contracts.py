"""Proof that the **real, already-shipped** Kernel and Capability Pack
implementations satisfy the new SDK ``Agent``/``Tool``/``LLMGateway``
Protocols with **zero modification** — ``platform_sdk_v1_scope.md``
steps 3 and 4.

This is the claim each narrowing decision rests on: §4.2/§4.3/§5.1 were
narrowed to the working shape *specifically* so that the five proven
agents, the two Echo stand-ins, the one real sandboxed tool, and the
real multi-provider gateway would already conform. A test built around
a fresh mock written to satisfy the Protocol would prove nothing about
that — so every subject below is an actual class imported from
``ai_os_kernel`` or from the ``software-engineering`` pack, constructed
the same way its real caller constructs it.

**Why this file lives in the root suite rather than in
``platform_sdk/tests/``.** ``platform_sdk.md`` §2 rule 1 makes the SDK
the dependency floor — it depends on no other AI_OS distribution — and
that discipline is held in its own test suite too. A test that imports
``ai_os_kernel`` *and* a pack *and* ``ai_os_sdk`` is inherently a
cross-boundary assertion, and the root suite already spans all three.

**Nothing in the Kernel or the pack is modified by steps 3 or 4.** This
file only observes them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_os_kernel.llm_gateway.gateway import DispatchingLLMGateway, EchoLLMGateway
from ai_os_kernel.llm_gateway.router import StaticRouter
from ai_os_kernel.sandbox.executor import LocalSubprocessSandbox
from ai_os_kernel.workflow_engine.agent import EchoAgent
from ai_os_kernel.workflow_engine.sandboxed_tool import SandboxedCommandTool
from ai_os_kernel.workflow_engine.tool import EchoTool
from ai_os_kernel.workflow_engine.tool import TrustTier as KernelTrustTier
from ai_os_pack_software_engineering.agents.architecture import ArchitectureAgentEntrypoint
from ai_os_pack_software_engineering.agents.build import BuildAgentEntrypoint
from ai_os_pack_software_engineering.agents.documentation import DocumentationAgentEntrypoint
from ai_os_pack_software_engineering.agents.git_push import GitPushAgentEntrypoint
from ai_os_pack_software_engineering.agents.lint import LintAgentEntrypoint
from ai_os_pack_software_engineering.agents.requirements_analyst import (
    RequirementsAnalystAgentEntrypoint,
)
from ai_os_pack_software_engineering.agents.verification import TestAgentEntrypoint
from ai_os_sdk.contracts import Agent as SdkAgent
from ai_os_sdk.contracts import LLMGateway as SdkLLMGateway
from ai_os_sdk.contracts import Tool as SdkTool
from ai_os_sdk.contracts import TrustTier as SdkTrustTier

# Every real agent-shaped entrypoint the platform ships today: the
# Kernel's own trivial stand-in, plus all seven Software Engineering
# pack agents (Git Push added 2026-08-02 — this pack's seventh, and the
# first to consume a Platform Service). Each is zero-argument
# constructible because `EntrypointLoader` only ever calls `cls()` — so
# constructing them here is exactly what the real loader does, and none
# of them performs I/O until first `execute`.
_REAL_AGENT_TYPES = [
    EchoAgent,
    ArchitectureAgentEntrypoint,
    BuildAgentEntrypoint,
    DocumentationAgentEntrypoint,
    GitPushAgentEntrypoint,
    LintAgentEntrypoint,
    RequirementsAnalystAgentEntrypoint,
    TestAgentEntrypoint,
]


def _real_sandboxed_tool() -> SandboxedCommandTool:
    """The one real, non-trivial ``Tool`` implementation in the codebase,
    constructed the way its real callers do (``agents/build.py``,
    ``agents/verification.py``). No command runs: constructing a
    ``SandboxedCommandTool`` only stores its arguments.
    """
    return SandboxedCommandTool(
        LocalSubprocessSandbox(),
        command=["true"],
        working_directory=Path.cwd(),
        timeout_seconds=1.0,
        max_output_bytes=1024,
    )


class TestRealAgentsSatisfyTheSdkAgentProtocol:
    @pytest.mark.parametrize("agent_type", _REAL_AGENT_TYPES, ids=lambda t: t.__name__)
    def test_real_agent_is_an_sdk_agent(self, agent_type: type) -> None:
        assert isinstance(agent_type(), SdkAgent)

    def test_all_seven_pack_agents_are_covered(self) -> None:
        """Guards the list above against silently drifting out of date:
        the pack declares seven agents, and all seven must be asserted,
        not a convenient subset."""
        pack_agent_types = [t for t in _REAL_AGENT_TYPES if t is not EchoAgent]
        assert len(pack_agent_types) == 7


class TestRealToolsSatisfyTheSdkToolProtocol:
    def test_echo_tool_is_an_sdk_tool(self) -> None:
        assert isinstance(EchoTool(), SdkTool)

    def test_sandboxed_command_tool_is_an_sdk_tool(self) -> None:
        assert isinstance(_real_sandboxed_tool(), SdkTool)

    def test_a_real_agent_is_not_an_sdk_tool(self) -> None:
        """The tier is what separates them structurally. An agent passing
        as a tool would let a mis-registered entrypoint bypass ADR-0016's
        sandbox guard."""
        assert not isinstance(EchoAgent(), SdkTool)


def _real_dispatching_gateway() -> DispatchingLLMGateway:
    """The real, working multi-provider gateway, constructed with the
    minimum real dependencies it requires: a real ``Router`` (empty
    routing table — nothing here calls ``complete``, only checks shape)
    and an empty provider mapping. No network, no provider adapter, no
    capability negotiator — none of `capabilities()`'s or `complete()`'s
    actual behaviour is exercised, only the object's shape.
    """
    return DispatchingLLMGateway(router=StaticRouter(routes={}), gateways={})


class TestRealLLMGatewaySatisfiesTheSdkLLMGatewayProtocol:
    def test_dispatching_llm_gateway_is_an_sdk_llm_gateway(self) -> None:
        assert isinstance(_real_dispatching_gateway(), SdkLLMGateway)

    def test_echo_llm_gateway_is_not_an_sdk_llm_gateway(self) -> None:
        """EchoLLMGateway implements only complete() — the Kernel's own
        internal LLMGateway Protocol (gateway.py) requires just that one
        method, which is narrower than this SDK Protocol. The SDK
        Protocol requires both complete() and capabilities(), so only
        DispatchingLLMGateway — the real, production gateway — conforms,
        not every historical Kernel implementer of the narrower internal
        Protocol.
        """
        assert not isinstance(EchoLLMGateway(), SdkLLMGateway)


class TestTrustTierAgreement:
    """The SDK defines its own ``TrustTier`` because it cannot import the
    Kernel's (§2 rule 1, dependency floor). Both mirror
    ``manifest.schema.json``'s ``tools[].trustTier`` enum independently,
    so agreement between them is a property worth asserting rather than
    assuming — nothing else would catch them drifting apart.
    """

    def test_both_enums_carry_the_same_values(self) -> None:
        assert {t.value for t in SdkTrustTier} == {t.value for t in KernelTrustTier}

    def test_the_real_sandboxed_tools_tier_matches_the_sdk_vocabulary(self) -> None:
        """The real sandboxed tool's declared tier is expressible in the
        SDK's vocabulary — which is what an adapter needs in order to
        translate one into the other in step 6a.

        Compared by ``.value``, not member-to-member: the direct
        comparison is true at runtime (both are ``StrEnum``) but
        ``mypy --strict`` correctly rejects it as non-overlapping, since
        the two enums are unrelated types. The wire value is the thing
        that actually has to agree.
        """
        tool = _real_sandboxed_tool()
        assert tool.trust_tier.value == SdkTrustTier.TIER1_SANDBOXED.value

    def test_the_two_enum_classes_are_deliberately_distinct_types(self) -> None:
        """Recorded, not lamented. Because these are separate Python
        types, a Kernel-typed tool is not *statically* assignable to the
        SDK ``Tool`` Protocol even though it satisfies it at runtime —
        exactly as §4.3's decision block states. Bridging that is the
        Kernel-side adapter's job in step 6a.
        """
        assert SdkTrustTier.__module__ != KernelTrustTier.__module__
        assert not isinstance(SdkTrustTier.TIER1_SANDBOXED, KernelTrustTier)
