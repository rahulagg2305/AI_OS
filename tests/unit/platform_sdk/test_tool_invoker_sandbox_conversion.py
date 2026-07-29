"""Proof that the SDK's ``ToolResult`` (``ai_os_sdk.models.tool``)
correctly and losslessly represents what the real, working sandbox
actually produces — ``platform_sdk_v1_scope.md`` step 6.

**Why this proof uses real sandbox executions, not fabricated
``SandboxResult`` values.** The specific claim under test is that
``ToolResult`` distinguishes a clean run from a timed-out one and from
a truncated one — the exact gap step 2a found in the documented §4.3
shape ("a caller parsing truncated stdout as complete output draws a
wrong conclusion silently"). Constructing a ``SandboxResult`` by hand
would only prove the *model* accepts three different inputs; running
the real ``LocalSubprocessSandbox`` against a command that actually
times out, and another that actually gets truncated, proves the
Kernel's real execution path genuinely produces the distinct outcomes
this Protocol claims to preserve.

**The conversion function below is illustrative only, not production
code**, exactly like step 5's prompt conversion — building the real,
shipped ``ToolInvoker`` adapter over ``SandboxExecutor`` is step 6a's
job, over the platform-provided
:data:`~ai_os_sdk.contracts.tool_invoker.PLATFORM_SANDBOX_RUN_COMMAND`
tool this step only defines the contract for.

**Why this file lives in the root suite rather than in
``platform_sdk/tests/``.** It imports ``ai_os_kernel.sandbox`` directly,
and ``platform_sdk/tests/`` deliberately imports nothing outside the SDK
(``platform_sdk.md`` §2 rule 1, the dependency floor) — the same
discipline every other cross-boundary proof in this directory follows.

**Nothing in the Kernel is modified by this step.** This file only runs
real subprocesses through the Kernel's own, unmodified sandbox and
converts the result.
"""

from __future__ import annotations

from pathlib import Path

from ai_os_kernel.sandbox.executor import LocalSubprocessSandbox
from ai_os_kernel.sandbox.models import SandboxResult
from ai_os_sdk.errors import PermanentError, TransientError
from ai_os_sdk.models import ToolResult, ToolStatus, TraceContext

_TRACE = TraceContext(trace_id="t", span_id="s")


def _sandbox_result_to_tool_result(result: SandboxResult) -> ToolResult:
    """Reference conversion only — see this module's own docstring.

    Mirrors exactly what ``SandboxedCommandTool.execute`` already
    returns today (``workflow_engine/sandboxed_tool.py``'s own
    ``exitCode``/``stdout``/``stderr``/``timedOut``/``truncated``/
    ``durationSeconds`` mapping), renamed to this Protocol's field
    names — the real adapter's job in step 6a is substantially this
    same mapping, not a new design.

    **The branch on ``exit_code is None``, not on ``timed_out``, is
    itself a real finding from running this exact function against the
    real sandbox.** An earlier draft branched on ``timed_out`` first and
    treated any non-``None`` ``exit_code`` as the only failure signal —
    which mis-classified a cap-breach-triggered kill (``timed_out=False``,
    ``exit_code=None``) as "exited with code None," a nonsensical claim.
    A missing ``exit_code`` means "no confirmed outcome" regardless of
    *why* the process was killed, so it is the first thing checked.
    """
    duration_ms = round(result.duration_seconds * 1000)
    if result.exit_code is None:
        error = (
            TransientError("sandbox.timed_out", "command exceeded its timeout")
            if result.timed_out
            else TransientError(
                "sandbox.killed_on_output_cap",
                "command was killed after exceeding its output cap, before it "
                "could exit on its own — no confirmed outcome is available",
            )
        ).to_structured_error(trace=_TRACE)
        return ToolResult(
            status=ToolStatus.FAILURE,
            outputs=None,
            error=error,
            exit_code=None,
            stdout=result.stdout,
            stderr=result.stderr,
            timed_out=result.timed_out,
            truncated=result.truncated,
            duration_ms=duration_ms,
        )
    if result.exit_code != 0:
        return ToolResult(
            status=ToolStatus.FAILURE,
            outputs=None,
            error=PermanentError(
                "sandbox.nonzero_exit", f"command exited {result.exit_code}"
            ).to_structured_error(trace=_TRACE),
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            timed_out=False,
            truncated=result.truncated,
            duration_ms=duration_ms,
        )
    return ToolResult(
        status=ToolStatus.SUCCESS,
        outputs={"stdout": result.stdout, "stderr": result.stderr},
        error=None,
        exit_code=result.exit_code,
        stdout=result.stdout,
        stderr=result.stderr,
        timed_out=False,
        truncated=result.truncated,
        duration_ms=duration_ms,
    )


def _sandbox() -> LocalSubprocessSandbox:
    return LocalSubprocessSandbox()


async def _run_clean() -> SandboxResult:
    """A real subprocess that completes quickly with no output cap
    hit — the baseline "nothing unusual happened" case."""
    sandbox = _sandbox()
    return await sandbox.execute(
        command=[*sandbox.python_command, "-c", "print('hello')"],
        working_directory=Path.cwd(),
        timeout_seconds=10.0,
        max_output_bytes=65536,
    )


async def _run_timed_out() -> SandboxResult:
    """A real subprocess that genuinely exceeds its timeout and is
    killed — not a fabricated timed_out=True value."""
    sandbox = _sandbox()
    return await sandbox.execute(
        command=[*sandbox.python_command, "-c", "import time; time.sleep(5)"],
        working_directory=Path.cwd(),
        timeout_seconds=0.3,
        max_output_bytes=65536,
    )


async def _run_truncated() -> SandboxResult:
    """A real subprocess whose stdout genuinely exceeds
    ``max_output_bytes`` and is capped by the sandbox itself — not a
    fabricated ``truncated=True`` value.

    **Empirically, not assumed: this reliably produces ``exit_code=None``,
    not a real exit code.** ``sandbox/executor.py``'s own cap-breach path
    kills the process as soon as the cap is detected, and on this
    platform that kill consistently outraces the process's own exit —
    confirmed by direct probing (varying ``max_output_bytes`` from 16
    down to 1 byte, every run: ``exit_code=None``). A ``ValueError``
    below documents that expectation rather than silently accepting
    whatever this run happens to produce, since the code hitting a
    different real outcome would be exactly the kind of assumption this
    whole file exists to avoid making.
    """
    sandbox = _sandbox()
    result = await sandbox.execute(
        command=[*sandbox.python_command, "-c", "print('x' * 100_000)"],
        working_directory=Path.cwd(),
        timeout_seconds=10.0,
        max_output_bytes=16,
    )
    if result.exit_code is not None:
        raise ValueError(
            "expected this cap breach to kill the process before it exited "
            f"(exit_code=None); got exit_code={result.exit_code!r} instead — "
            "the real sandbox's timing behaviour changed, and the test "
            "claims below need re-checking against the new reality, not "
            "silently passing on an unverified assumption"
        )
    return result


class TestCleanRunConvertsToSuccess:
    async def test_a_clean_run_is_success_with_no_timeout_or_truncation(self) -> None:
        sandbox_result = await _run_clean()
        assert sandbox_result.exit_code == 0
        assert sandbox_result.timed_out is False
        assert sandbox_result.truncated is False

        tool_result = _sandbox_result_to_tool_result(sandbox_result)
        assert tool_result.status is ToolStatus.SUCCESS
        assert tool_result.timed_out is False
        assert tool_result.truncated is False
        assert tool_result.exit_code == 0
        assert "hello" in tool_result.stdout


class TestTimedOutRunConvertsDistinctly:
    async def test_a_genuinely_timed_out_run_is_reported_as_such(self) -> None:
        sandbox_result = await _run_timed_out()
        assert sandbox_result.timed_out is True
        assert sandbox_result.exit_code is None

        tool_result = _sandbox_result_to_tool_result(sandbox_result)
        assert tool_result.timed_out is True
        assert tool_result.exit_code is None
        assert tool_result.status is ToolStatus.FAILURE
        assert tool_result.error is not None


class TestTruncatedRunConvertsDistinctly:
    async def test_a_genuinely_truncated_run_is_reported_as_such(self) -> None:
        sandbox_result = await _run_truncated()
        assert sandbox_result.truncated is True
        assert sandbox_result.timed_out is False
        assert len(sandbox_result.stdout.encode()) <= 16

        tool_result = _sandbox_result_to_tool_result(sandbox_result)
        assert tool_result.truncated is True
        assert tool_result.timed_out is False
        # Not a success: the process was killed on the cap breach before
        # it could confirm its own exit code (real, verified behaviour —
        # see _run_truncated's own docstring), so there is no confirmed
        # outcome to report as a success. ToolResult's model-level
        # invariants still permit a truncated-AND-successful state in
        # general (see test_tool_models.py, constructed directly) for a
        # hypothetical backend where the process exits before the kill
        # lands; this real backend, on this platform, does not produce
        # that case.
        assert tool_result.status is ToolStatus.FAILURE
        assert tool_result.exit_code is None
        assert tool_result.error is not None


class TestAllThreeOutcomesAreMutuallyDistinguishable:
    async def test_clean_timed_out_and_truncated_are_all_different(self) -> None:
        """The claim this whole file exists to prove: three genuinely
        different real executions produce three genuinely different,
        never-confusable ToolResult values."""
        clean = _sandbox_result_to_tool_result(await _run_clean())
        timed_out = _sandbox_result_to_tool_result(await _run_timed_out())
        truncated = _sandbox_result_to_tool_result(await _run_truncated())

        assert clean != timed_out
        assert clean != truncated
        assert timed_out != truncated

        assert (clean.timed_out, clean.truncated) == (False, False)
        assert (timed_out.timed_out, timed_out.truncated) == (True, False)
        assert (truncated.timed_out, truncated.truncated) == (False, True)
