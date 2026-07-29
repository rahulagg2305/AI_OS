"""Unit tests for ``_bind_pack_context_if_receiver`` — the pure logic
behind ``SqlAgentRegistry``/``SqlToolRegistry``'s own step 9a real
``PackContextReceiver`` injection, isolated from any real database
(``platform_sdk_v1_scope.md`` step 9a).
"""

from __future__ import annotations

from typing import Any

import pytest

from ai_os_kernel.sandbox.executor import LocalSubprocessSandbox
from ai_os_kernel.workflow_engine.agent import EchoAgent
from ai_os_kernel.workflow_engine.errors import AgentRegistryError, ToolRegistryError
from ai_os_kernel.workflow_engine.registry import _bind_pack_context_if_receiver


class _NotAReceiver:
    pass


class _FakeReceiver:
    def __init__(self) -> None:
        self.bound_context: Any | None = None

    def bind_pack_context(self, context: Any) -> None:
        self.bound_context = context


class TestBindPackContextIfReceiver:
    def test_a_non_receiver_is_left_untouched(self) -> None:
        """Every not-yet-migrated real agent today (EchoAgent stands in
        for one) — must be a true no-op, not an error."""
        agent = EchoAgent()

        _bind_pack_context_if_receiver(
            agent,
            kind="agent",
            declared_id="some/agent",
            pack_id="some-pack",
            pack_version="0.1.0",
            required_permissions=[],
            llm_gateway=None,
            prompt_engine=None,
            sandbox=None,
        )

        assert not hasattr(agent, "bound_context")

    def test_a_receiver_is_genuinely_bound_with_a_real_pack_context(self) -> None:
        receiver = _FakeReceiver()
        sandbox = LocalSubprocessSandbox()

        _bind_pack_context_if_receiver(
            receiver,
            kind="agent",
            declared_id="some/agent",
            pack_id="some-pack",
            pack_version="0.1.0",
            required_permissions=["sandbox:execute"],
            llm_gateway=None,
            prompt_engine=None,
            sandbox=sandbox,
        )

        assert receiver.bound_context is not None
        assert receiver.bound_context.pack_id == "some-pack"
        assert receiver.bound_context.tools is not None
        assert receiver.bound_context.llm is None

    def test_a_receiver_only_gets_what_its_own_permissions_declare(self) -> None:
        """No over-provisioning even at this layer -- required_permissions
        of [] means a real PackContextReceiver gets an identity-only
        context, even though a real sandbox was available to hand it."""
        receiver = _FakeReceiver()

        _bind_pack_context_if_receiver(
            receiver,
            kind="agent",
            declared_id="some/agent",
            pack_id="some-pack",
            pack_version="0.1.0",
            required_permissions=[],
            llm_gateway=None,
            prompt_engine=None,
            sandbox=LocalSubprocessSandbox(),
        )

        assert receiver.bound_context is not None
        assert receiver.bound_context.tools is None

    def test_a_declared_permission_with_no_real_backing_raises_agent_registry_error(self) -> None:
        receiver = _FakeReceiver()

        with pytest.raises(AgentRegistryError, match="sandbox:execute"):
            _bind_pack_context_if_receiver(
                receiver,
                kind="agent",
                declared_id="some/agent",
                pack_id="some-pack",
                pack_version="0.1.0",
                required_permissions=["sandbox:execute"],
                llm_gateway=None,
                prompt_engine=None,
                sandbox=None,
            )

    def test_the_same_gap_for_a_tool_raises_tool_registry_error(self) -> None:
        """Same helper, same rule, the other error family -- used by
        SqlToolRegistry."""
        receiver = _FakeReceiver()

        with pytest.raises(ToolRegistryError, match="sandbox:execute"):
            _bind_pack_context_if_receiver(
                receiver,
                kind="tool",
                declared_id="some/tool",
                pack_id="some-pack",
                pack_version="0.1.0",
                required_permissions=["sandbox:execute"],
                llm_gateway=None,
                prompt_engine=None,
                sandbox=None,
            )
