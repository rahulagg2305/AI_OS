"""``ToolInvokerAdapter`` — real, against a real
:class:`~ai_os_kernel.sandbox.executor.LocalSubprocessSandbox`
(``platform_sdk_v1_scope.md`` step 6a).

Runs genuine subprocesses, matching step 6's own cross-boundary proof
(``tests/unit/platform_sdk/test_tool_invoker_sandbox_conversion.py`` —
that file proves the *conversion logic* against real sandbox output;
this file proves the *production adapter* built from it, including the
timeout-precedence decision this step resolves for the first time.

**``TestPlatformPythonInterpreterSubstitution`` (step 12a, inserted
2026-07-29)** proves the fix for a real regression step 12 found: a
migrated agent (``build``) can no longer ask its own sandbox for its
``python_command`` directly, and a static constructor default only
happens to match whichever backend is active *today*. The real fix
moves interpreter resolution into this adapter — the one place that
still holds the real ``SandboxExecutor`` — via a well-known placeholder
token, :data:`~ai_os_sdk.contracts.tool_invoker.PLATFORM_PYTHON_INTERPRETER`.
The Docker half of that proof (against a real, live ``DockerSandbox``)
lives in ``tests/integration/sandbox/test_tool_invoker_adapter_docker.py``
— this file stays Docker-free, consistent with every other test here.
"""

from __future__ import annotations

import sys
import time

import pytest

from ai_os_kernel.sandbox.executor import LocalSubprocessSandbox
from ai_os_kernel.sdk_adapters.tool_invoker_adapter import ToolInvokerAdapter, UnknownToolError
from ai_os_sdk.contracts import (
    PLATFORM_PYTHON_INTERPRETER,
    PLATFORM_SANDBOX_RUN_COMMAND,
    PLATFORM_SANDBOX_RUN_COMMAND_DESCRIPTOR,
)
from ai_os_sdk.contracts import ToolInvoker as SdkToolInvoker
from ai_os_sdk.models import ToolStatus


def _real_adapter() -> ToolInvokerAdapter:
    return ToolInvokerAdapter(LocalSubprocessSandbox())


def _python_inputs(script: str, **overrides: object) -> dict[str, object]:
    sandbox = LocalSubprocessSandbox()
    fields: dict[str, object] = {
        "command": [*sandbox.python_command, "-c", script],
        "working_directory": ".",
        "timeout_seconds": 10.0,
        "max_output_bytes": 65536,
    }
    fields.update(overrides)
    return fields


class TestToolInvokerAdapterSatisfiesTheProtocol:
    def test_the_adapter_itself_is_an_sdk_tool_invoker(self) -> None:
        assert isinstance(_real_adapter(), SdkToolInvoker)


class TestAvailableTools:
    def test_includes_the_one_real_platform_tool(self) -> None:
        adapter = _real_adapter()
        assert adapter.available_tools() == (PLATFORM_SANDBOX_RUN_COMMAND_DESCRIPTOR,)


class TestInvokeAgainstARealSandbox:
    async def test_a_real_clean_command_succeeds(self) -> None:
        adapter = _real_adapter()

        result = await adapter.invoke(
            PLATFORM_SANDBOX_RUN_COMMAND, _python_inputs("print('hello')")
        )

        assert result.status is ToolStatus.SUCCESS
        assert "hello" in result.stdout
        assert result.exit_code == 0
        assert result.timed_out is False
        assert result.truncated is False

    async def test_a_real_nonzero_exit_is_reported_as_failure(self) -> None:
        adapter = _real_adapter()

        result = await adapter.invoke(
            PLATFORM_SANDBOX_RUN_COMMAND, _python_inputs("import sys; sys.exit(3)")
        )

        assert result.status is ToolStatus.FAILURE
        assert result.exit_code == 3
        assert result.error is not None

    async def test_an_unknown_tool_id_raises(self) -> None:
        adapter = _real_adapter()

        with pytest.raises(UnknownToolError, match="not.*known"):
            await adapter.invoke("some.other.tool", {})

    async def test_inputs_failing_the_declared_schema_raise(self) -> None:
        """No `command` key at all -- the schema declares it required."""
        adapter = _real_adapter()

        with pytest.raises(ValueError, match="input_schema"):
            await adapter.invoke(
                PLATFORM_SANDBOX_RUN_COMMAND,
                {"working_directory": ".", "timeout_seconds": 1.0, "max_output_bytes": 1024},
            )


class TestTimeoutPrecedence:
    """The deliberate decision this step resolves: the more restrictive
    of invoke()'s own timeout_seconds and inputs["timeout_seconds"]
    always wins. Each test proves the *effective* timeout by observing
    real elapsed time and a real outcome, not by inspecting an internal
    value.
    """

    async def test_a_tighter_outer_timeout_overrides_a_looser_inputs_timeout(self) -> None:
        adapter = _real_adapter()
        started = time.monotonic()

        result = await adapter.invoke(
            PLATFORM_SANDBOX_RUN_COMMAND,
            _python_inputs("import time; time.sleep(5)", timeout_seconds=10.0),
            timeout_seconds=0.3,
        )

        elapsed = time.monotonic() - started
        assert result.timed_out is True
        assert result.status is ToolStatus.FAILURE
        # Bounded well under the looser 10s inputs timeout -- proves the
        # tighter outer ceiling, not the tool's own value, governed.
        assert elapsed < 5.0

    async def test_a_tighter_inputs_timeout_overrides_a_looser_outer_timeout(self) -> None:
        adapter = _real_adapter()
        started = time.monotonic()

        result = await adapter.invoke(
            PLATFORM_SANDBOX_RUN_COMMAND,
            _python_inputs("import time; time.sleep(5)", timeout_seconds=0.3),
            timeout_seconds=10.0,
        )

        elapsed = time.monotonic() - started
        assert result.timed_out is True
        assert result.status is ToolStatus.FAILURE
        # Bounded well under the looser 10s outer ceiling -- proves the
        # tool's own tighter inputs timeout governed, not the outer one.
        assert elapsed < 5.0

    async def test_no_outer_timeout_uses_the_inputs_timeout_directly(self) -> None:
        adapter = _real_adapter()

        result = await adapter.invoke(
            PLATFORM_SANDBOX_RUN_COMMAND,
            _python_inputs("print('ok')", timeout_seconds=10.0),
            # timeout_seconds not passed at all -> None -> "no outer ceiling"
        )

        assert result.status is ToolStatus.SUCCESS

    async def test_two_generous_timeouts_do_not_falsely_trigger_a_timeout(self) -> None:
        """Confirms min() doesn't over-trigger when both bounds are
        genuinely loose -- a fast command still succeeds."""
        adapter = _real_adapter()

        result = await adapter.invoke(
            PLATFORM_SANDBOX_RUN_COMMAND,
            _python_inputs("print('fast')", timeout_seconds=10.0),
            timeout_seconds=10.0,
        )

        assert result.status is ToolStatus.SUCCESS
        assert result.timed_out is False


class TestPlatformPythonInterpreterSubstitution:
    """Step 12a's own real proof: a caller that writes
    ``PLATFORM_PYTHON_INTERPRETER`` in place of a literal interpreter
    path gets the real, current backend's own ``python_command``
    substituted in automatically — restoring the "always correct, no
    caller-side guessing" guarantee the pre-migration code had by asking
    its own injected sandbox directly. Proven against a real,
    actually-executed ``LocalSubprocessSandbox`` (this file's own,
    Docker-free tier); the ``DockerSandbox`` half of this same proof
    lives in ``test_tool_invoker_adapter_docker.py``.
    """

    async def test_the_placeholder_resolves_to_the_real_local_sandbox_interpreter(self) -> None:
        """Proves the substitution against a real, live sandbox
        genuinely produced the *correct* interpreter for this backend —
        not merely "some" command that happened to run. Compares the
        script's own reported `sys.executable` against
        `LocalSubprocessSandbox().python_command`'s own real value, the
        same fact the pre-migration `build.py` used to ask for
        directly."""
        adapter = _real_adapter()
        expected_python_command = LocalSubprocessSandbox().python_command

        result = await adapter.invoke(
            PLATFORM_SANDBOX_RUN_COMMAND,
            {
                "command": [PLATFORM_PYTHON_INTERPRETER, "-c", "import sys; print(sys.executable)"],
                "working_directory": ".",
                "timeout_seconds": 10.0,
                "max_output_bytes": 65536,
            },
        )

        assert result.status is ToolStatus.SUCCESS
        # LocalSubprocessSandbox.python_command is (sys.executable,) —
        # the real interpreter the substituted command actually ran
        # under must report that identical path back.
        assert expected_python_command == (sys.executable,)
        assert result.stdout.strip() == sys.executable

    async def test_a_multi_token_command_only_expands_the_placeholder_token(self) -> None:
        """The substitution expands in place, not 1:1 -- proven here by
        a command with a real argument *after* the placeholder, which
        must survive unchanged (LocalSubprocessSandbox.python_command
        is exactly one token today, so this also guards against a
        future multi-token python_command silently swallowing the
        following argument)."""
        adapter = _real_adapter()

        result = await adapter.invoke(
            PLATFORM_SANDBOX_RUN_COMMAND,
            {
                "command": [PLATFORM_PYTHON_INTERPRETER, "-c", "print('after placeholder')"],
                "working_directory": ".",
                "timeout_seconds": 10.0,
                "max_output_bytes": 65536,
            },
        )

        assert result.status is ToolStatus.SUCCESS
        assert result.stdout.strip() == "after placeholder"

    async def test_a_command_with_no_placeholder_is_passed_through_unchanged(self) -> None:
        """No token equals the placeholder here -- the substitution must
        be a genuine no-op, not a blanket rewrite of the whole command."""
        adapter = _real_adapter()

        result = await adapter.invoke(
            PLATFORM_SANDBOX_RUN_COMMAND,
            _python_inputs("print('no placeholder used')"),
        )

        assert result.status is ToolStatus.SUCCESS
        assert result.stdout.strip() == "no placeholder used"
