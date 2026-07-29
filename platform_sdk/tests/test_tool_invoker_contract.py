"""Step 6 of ``platform_sdk_v1_scope.md``: the ``ToolInvoker`` Protocol
itself (``platform_sdk.md`` §5.6, from-scratch design).

This is a from-scratch call convention, not a narrowing of an existing
Kernel shape, so — like ``PromptRegistry`` in step 5 — there is no
``isinstance`` proof against real code for the Protocol itself. What
*is* proven against real, executed sandbox behaviour is that
``ToolResult`` correctly distinguishes clean/timed-out/truncated runs;
that lives in
``tests/unit/platform_sdk/test_tool_invoker_sandbox_conversion.py``
since it exercises the real ``LocalSubprocessSandbox``. This file
covers the Protocol's own semantics with SDK-only fixtures.
"""

from typing import Any

from ai_os_sdk.contracts import PLATFORM_SANDBOX_RUN_COMMAND_DESCRIPTOR, ToolInvoker
from ai_os_sdk.models import ToolDescriptor, ToolResult, ToolStatus, TrustTier


class _MinimalInvoker:
    """Exactly the two members the Protocol requires. ``available_tools``
    returns the one real platform tool — proving §5.6's own claim that
    this design gives it a genuine, non-empty answer."""

    async def invoke(
        self, tool_id: str, inputs: dict[str, Any], *, timeout_seconds: float | None = None
    ) -> ToolResult:
        return ToolResult(
            status=ToolStatus.SUCCESS,
            outputs={"stdout": "", "stderr": ""},
            error=None,
            exit_code=0,
            stdout="",
            stderr="",
            timed_out=False,
            truncated=False,
            duration_ms=1,
        )

    def available_tools(self) -> tuple[ToolDescriptor, ...]:
        return (PLATFORM_SANDBOX_RUN_COMMAND_DESCRIPTOR,)


class TestToolInvokerProtocol:
    def test_a_conforming_object_satisfies_it(self) -> None:
        assert isinstance(_MinimalInvoker(), ToolInvoker)

    def test_an_object_missing_available_tools_does_not(self) -> None:
        class InvokeOnly:
            async def invoke(
                self, tool_id: str, inputs: dict[str, Any], *, timeout_seconds: float | None = None
            ) -> ToolResult:
                raise NotImplementedError

        assert not isinstance(InvokeOnly(), ToolInvoker)

    def test_an_object_missing_invoke_does_not(self) -> None:
        class AvailableToolsOnly:
            def available_tools(self) -> tuple[ToolDescriptor, ...]:
                return ()

        assert not isinstance(AvailableToolsOnly(), ToolInvoker)

    def test_isinstance_proves_presence_only_never_signatures(self) -> None:
        """The same limitation recorded for every other Protocol in this
        package."""

        class WrongShapeEntirely:
            def invoke(self) -> str:
                return "not even async, wrong name of args"

            def available_tools(self) -> str:
                return "not a tuple at all"

        assert isinstance(WrongShapeEntirely(), ToolInvoker)

    def test_available_tools_includes_the_one_real_platform_tool(self) -> None:
        """The specific claim §5.6's decision block makes: available_tools
        has a genuine, non-empty answer in v1.0.0, grounded in the one
        real platform-provided tool."""
        invoker = _MinimalInvoker()
        assert PLATFORM_SANDBOX_RUN_COMMAND_DESCRIPTOR in invoker.available_tools()

    async def test_invoke_accepts_the_documented_call_style(self) -> None:
        invoker = _MinimalInvoker()
        result = await invoker.invoke(
            "platform.sandbox.run_command",
            {
                "command": ["true"],
                "working_directory": ".",
                "timeout_seconds": 1.0,
                "max_output_bytes": 1024,
            },
        )
        assert result.status is ToolStatus.SUCCESS


class TestPlatformSandboxRunCommandDescriptor:
    def test_is_tier1_sandboxed(self) -> None:
        """ADR-0016: any tool executing a command MUST be
        tier1_sandboxed."""
        assert PLATFORM_SANDBOX_RUN_COMMAND_DESCRIPTOR.trust_tier is TrustTier.TIER1_SANDBOXED

    def test_input_schema_requires_exactly_what_the_real_sandbox_requires(self) -> None:
        """Mirrors SandboxExecutor.execute's own required keyword
        arguments (sandbox/executor.py:151-160) — command,
        working_directory, timeout_seconds, max_output_bytes."""
        required = set(PLATFORM_SANDBOX_RUN_COMMAND_DESCRIPTOR.input_schema["required"])
        assert required == {"command", "working_directory", "timeout_seconds", "max_output_bytes"}
