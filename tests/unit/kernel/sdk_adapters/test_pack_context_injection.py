"""The step 6b injection mechanism, proven end to end: a real
:class:`~ai_os_kernel.workflow_engine.entrypoint_loader.EntrypointLoader`
zero-argument construction, a real, permission-gated
:func:`~ai_os_kernel.sdk_adapters.pack_context.build_pack_context`, a
real :class:`~ai_os_sdk.contracts.PackContextReceiver`-based injection,
and a genuine call through each of the three injected adapters — an
Echo-backed LLM completion, a real prompt render, and a real sandboxed
command (``platform_sdk_v1_scope.md`` step 6b).

**``EntrypointLoader`` itself is exercised unmodified.** ``load()`` is
called exactly as :class:`~ai_os_kernel.workflow_engine.registry.SqlAgentRegistry`
would call it — one entrypoint string in, one zero-arg-constructed
object out — proving the injection mechanism this step adds needs no
change to that class at all. What differs from today's real
``SqlAgentRegistry`` is only the one line these tests add right after
``load()`` returns: a real ``isinstance`` check against
``PackContextReceiver``, then ``bind_pack_context()`` — the "actual
unlock" step 6b was scoped to prove, not yet wired into
``SqlAgentRegistry`` itself (deliberately deferred; see this module's own
test file docstring and ``platform_sdk_v1_scope.md`` §6h).
"""

from __future__ import annotations

import pytest

from ai_os_kernel.llm_gateway.gateway import EchoLLMGateway
from ai_os_kernel.prompt_engine.renderer import InMemoryPromptEngine
from ai_os_kernel.sandbox.executor import LocalSubprocessSandbox
from ai_os_kernel.sdk_adapters.pack_context import build_pack_context
from ai_os_kernel.workflow_engine.entrypoint_loader import EntrypointLoader
from ai_os_sdk.contracts import PLATFORM_SANDBOX_RUN_COMMAND, PackContextReceiver
from ai_os_sdk.models import LLMRequest, Message, MessageRole

from ._pack_context_injection_fixtures import (
    EchoCapabilityTestEntrypoint,
    PackContextNotBoundError,
)

_ENTRYPOINT = (
    "tests.unit.kernel.sdk_adapters._pack_context_injection_fixtures:EchoCapabilityTestEntrypoint"
)

_PROMPT_ID = "requirements.analyze"
_PROMPT_VERSION = "0.1.0"
_PROMPT_TEMPLATE = "Analyze: {{requirement}}"


def _load_via_real_entrypoint_loader() -> EchoCapabilityTestEntrypoint:
    """The exact call ``SqlAgentRegistry.resolve_agent`` makes today
    (``asyncio.to_thread(self._loader.load, row.entrypoint)``, minus the
    thread hop, irrelevant to what this proves) -- real, zero-argument
    construction, ``EntrypointLoader`` completely unmodified."""
    loaded = EntrypointLoader().load(_ENTRYPOINT)
    assert isinstance(loaded, EchoCapabilityTestEntrypoint)
    return loaded


class TestTheLoadedEntrypointIsAPackContextReceiver:
    def test_isinstance_check_passes(self) -> None:
        """The real ``isinstance`` check a future SqlAgentRegistry-side
        caller would make before deciding to inject anything at all."""
        entrypoint = _load_via_real_entrypoint_loader()
        assert isinstance(entrypoint, PackContextReceiver)


class TestExecuteBeforeBindingFailsClearly:
    async def test_raises_a_clear_error_not_an_attribute_error(self) -> None:
        entrypoint = _load_via_real_entrypoint_loader()

        with pytest.raises(PackContextNotBoundError):
            await entrypoint.execute({"capability": "llm", "request": object()})


class TestInjectedLlmCapability:
    async def test_a_real_echo_completion_through_the_injected_context(self) -> None:
        entrypoint = _load_via_real_entrypoint_loader()
        context = build_pack_context(
            pack_id="software-engineering",
            pack_version="0.1.0",
            permissions=["llm:invoke"],
            llm_gateway=EchoLLMGateway(),
            prompt_engine=InMemoryPromptEngine(templates={}),
        )
        entrypoint.bind_pack_context(context)

        request = LLMRequest(
            model_alias="fast-cheap",
            messages=[Message(role=MessageRole.USER, content="hello from step 6b")],
            max_output_tokens=100,
        )
        result = await entrypoint.execute({"capability": "llm", "request": request})

        assert result["result"] == "hello from step 6b"


class TestInjectedPromptsCapability:
    async def test_a_real_prompt_render_through_the_injected_context(self) -> None:
        entrypoint = _load_via_real_entrypoint_loader()
        context = build_pack_context(
            pack_id="software-engineering",
            pack_version="0.1.0",
            permissions=["llm:invoke"],
            llm_gateway=EchoLLMGateway(),
            prompt_engine=InMemoryPromptEngine(
                templates={(_PROMPT_ID, _PROMPT_VERSION): _PROMPT_TEMPLATE}
            ),
        )
        entrypoint.bind_pack_context(context)

        result = await entrypoint.execute(
            {
                "capability": "prompts",
                "prompt_id": _PROMPT_ID,
                "variables": {"requirement": "add rate limiting"},
                "version": _PROMPT_VERSION,
            }
        )

        assert result["result"] == "Analyze: add rate limiting"


class TestInjectedToolsCapability:
    async def test_a_real_sandboxed_command_through_the_injected_context(self) -> None:
        entrypoint = _load_via_real_entrypoint_loader()
        sandbox = LocalSubprocessSandbox()
        context = build_pack_context(
            pack_id="software-engineering",
            pack_version="0.1.0",
            permissions=["sandbox:execute"],
            sandbox=sandbox,
        )
        entrypoint.bind_pack_context(context)

        result = await entrypoint.execute(
            {
                "capability": "tools",
                "tool_id": PLATFORM_SANDBOX_RUN_COMMAND,
                "tool_inputs": {
                    "command": [*sandbox.python_command, "-c", "print('from step 6b')"],
                    "working_directory": ".",
                    "timeout_seconds": 10.0,
                    "max_output_bytes": 65536,
                },
            }
        )

        assert "from step 6b" in result["result"]
