"""Step 6 of ``platform_sdk_v1_scope.md``: ``ToolDescriptor`` and
``ToolResult`` (``platform_sdk.md`` §4.3, §5.6, mixed narrow-and-extend
shape).

The central claim under test: ``ToolResult`` genuinely distinguishes a
clean run from a timed-out one and from a truncated one — the specific
gap step 2a found in the documented shape.
"""

import pytest
from pydantic import ValidationError

from ai_os_sdk.errors import PermanentError, TransientError
from ai_os_sdk.models import ToolDescriptor, ToolResult, ToolStatus, TraceContext, TrustTier

_TRACE = TraceContext(trace_id="t", span_id="s")


def _success(**overrides: object) -> ToolResult:
    fields: dict[str, object] = {
        "status": ToolStatus.SUCCESS,
        "outputs": {"stdout": "hello\n", "stderr": ""},
        "error": None,
        "exit_code": 0,
        "stdout": "hello\n",
        "stderr": "",
        "timed_out": False,
        "truncated": False,
        "duration_ms": 42,
    }
    fields.update(overrides)
    return ToolResult(**fields)


def _failure(**overrides: object) -> ToolResult:
    fields: dict[str, object] = {
        "status": ToolStatus.FAILURE,
        "outputs": None,
        "error": PermanentError("sandbox.nonzero_exit", "exit 1").to_structured_error(trace=_TRACE),
        "exit_code": 1,
        "stdout": "",
        "stderr": "boom",
        "timed_out": False,
        "truncated": False,
        "duration_ms": 10,
    }
    fields.update(overrides)
    return ToolResult(**fields)


class TestToolDescriptor:
    def test_accepts_a_well_formed_descriptor(self) -> None:
        descriptor = ToolDescriptor(
            tool_id="platform.sandbox.run_command",
            trust_tier=TrustTier.TIER1_SANDBOXED,
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        )
        assert descriptor.tool_id == "platform.sandbox.run_command"

    def test_is_frozen(self) -> None:
        descriptor = ToolDescriptor(
            tool_id="x",
            trust_tier=TrustTier.TIER2_TRUSTED,
            input_schema={},
            output_schema={},
        )
        with pytest.raises(ValidationError):
            descriptor.tool_id = "y"  # type: ignore[misc]


class TestToolResultCleanRun:
    def test_a_clean_successful_run_is_representable(self) -> None:
        result = _success()
        assert result.status is ToolStatus.SUCCESS
        assert result.exit_code == 0
        assert result.timed_out is False
        assert result.truncated is False
        assert result.outputs == {"stdout": "hello\n", "stderr": ""}
        assert result.error is None


class TestToolResultTimeout:
    def test_a_timed_out_run_has_no_exit_code(self) -> None:
        """Mirrors SandboxResult's own real invariant: a killed process
        never produces a real exit code worth reporting."""
        result = _failure(
            timed_out=True,
            exit_code=None,
            error=TransientError("sandbox.timed_out", "exceeded timeout").to_structured_error(
                trace=_TRACE
            ),
        )
        assert result.timed_out is True
        assert result.exit_code is None
        assert result.status is ToolStatus.FAILURE

    def test_rejects_a_timed_out_result_that_also_claims_an_exit_code(self) -> None:
        with pytest.raises(ValidationError, match="exit_code must be None when timed_out"):
            _failure(timed_out=True, exit_code=124)

    def test_a_non_timed_out_result_may_still_have_no_exit_code(self) -> None:
        """Not a typo: verified against the real, running sandbox
        (``tests/unit/platform_sdk/test_tool_invoker_sandbox_conversion.py``).
        A cap breach kills the process before it exits on its own, so
        ``truncated=True, timed_out=False, exit_code=None`` is a real,
        valid outcome — an earlier draft of this model wrongly forbade
        it. See ``ToolResult``'s own docstring."""
        result = _failure(timed_out=False, truncated=True, exit_code=None)
        assert result.exit_code is None
        assert result.timed_out is False
        assert result.truncated is True

    def test_a_clean_run_and_a_timed_out_run_are_distinguishable(self) -> None:
        """The specific claim step 2a's extension exists to make true:
        these two outcomes must not collapse into the same
        representation."""
        clean = _success()
        timed_out = _failure(
            timed_out=True,
            exit_code=None,
            error=TransientError("sandbox.timed_out", "exceeded timeout").to_structured_error(
                trace=_TRACE
            ),
        )
        assert clean != timed_out
        assert clean.timed_out != timed_out.timed_out


class TestToolResultTruncation:
    def test_truncated_output_is_representable_independently_of_success(self) -> None:
        """A run can complete successfully AND have its output capped —
        the real sandbox truncates each stream independently of whether
        the command itself succeeded (sandbox/models.py)."""
        result = _success(truncated=True, stdout="x" * 1024)
        assert result.status is ToolStatus.SUCCESS
        assert result.truncated is True

    def test_a_complete_run_and_a_truncated_run_are_distinguishable(self) -> None:
        """The other specific claim step 2a's extension exists to make
        true: a caller must be able to tell these apart, or it will
        treat capped output as complete."""
        complete = _success(truncated=False)
        truncated = _success(truncated=True)
        assert complete != truncated
        assert complete.truncated != truncated.truncated

    def test_truncation_does_not_force_failure(self) -> None:
        """Truncation and success/failure are orthogonal axes — this is
        the real sandbox's own semantics, not an SDK invention."""
        result = _success(truncated=True)
        assert result.status is ToolStatus.SUCCESS


class TestToolResultOutputsErrorConsistency:
    def test_success_requires_outputs(self) -> None:
        with pytest.raises(ValidationError, match="outputs must be set when status is success"):
            _success(outputs=None)

    def test_success_forbids_error(self) -> None:
        with pytest.raises(ValidationError, match="error must be omitted when status is success"):
            _success(error=PermanentError("x.y", "boom").to_structured_error(trace=_TRACE))

    def test_failure_requires_error(self) -> None:
        with pytest.raises(ValidationError, match="error must be set when status is failure"):
            _failure(error=None)

    def test_failure_forbids_outputs(self) -> None:
        with pytest.raises(ValidationError, match="outputs must be omitted when status is failure"):
            _failure(outputs={"stdout": "partial"})

    def test_is_frozen(self) -> None:
        result = _success()
        with pytest.raises(ValidationError):
            result.status = ToolStatus.FAILURE  # type: ignore[misc]

    def test_rejects_negative_duration(self) -> None:
        with pytest.raises(ValidationError):
            _success(duration_ms=-1)
