"""Step 2 of ``platform_sdk_v1_scope.md``: the ``AiOsError`` hierarchy
and ``StructuredError`` (``platform_sdk.md`` §4.4,
``error_handling_retry.md`` §3/§8).

The load-bearing property under test is §4.4's own claim: every
exception maps 1:1 onto a ``StructuredError`` with **no possibility of
an exception whose category disagrees with its serialised form**.
"""

import pytest
from pydantic import ValidationError

from ai_os_sdk.errors import (
    AiOsError,
    BudgetExceededError,
    ErrorCategory,
    InfrastructureError,
    PermanentError,
    QualityError,
    SecurityError,
    StructuredError,
    TransientError,
)
from ai_os_sdk.models import TraceContext

_TRACE = TraceContext(trace_id="t", span_id="s")

# The exception -> category pairing platform_sdk.md §4.4 specifies, and
# the `Retriable` column of error_handling_retry.md §3 for each.
_HIERARCHY: list[tuple[type[AiOsError], ErrorCategory, bool]] = [
    (TransientError, ErrorCategory.TRANSIENT, True),
    (PermanentError, ErrorCategory.PERMANENT, False),
    (QualityError, ErrorCategory.QUALITY, False),
    (InfrastructureError, ErrorCategory.INFRASTRUCTURE, False),
    (BudgetExceededError, ErrorCategory.BUDGET, False),
    (SecurityError, ErrorCategory.SECURITY, False),
]


class TestErrorCategory:
    def test_defines_exactly_the_six_documented_categories(self) -> None:
        """error_handling_retry.md §3 is explicit that this is "the single
        platform error taxonomy". Six, not the LLM Gateway's narrower four."""
        assert {c.value for c in ErrorCategory} == {
            "transient",
            "permanent",
            "quality",
            "infrastructure",
            "budget",
            "security",
        }


class TestHierarchy:
    def test_the_base_is_not_raisable(self) -> None:
        """It declares no category, so it has nothing to report. Failing
        at construction beats an AttributeError later."""
        with pytest.raises(TypeError, match="catch-all base"):
            AiOsError("x.y", "boom")

    @pytest.mark.parametrize(("exc_type", "category", "_retriable"), _HIERARCHY)
    def test_every_subclass_is_catchable_as_the_base(
        self, exc_type: type[AiOsError], category: ErrorCategory, _retriable: bool
    ) -> None:
        with pytest.raises(AiOsError):
            raise exc_type("x.y", "boom")

    @pytest.mark.parametrize(("exc_type", "category", "_retriable"), _HIERARCHY)
    def test_category_is_fixed_by_the_class(
        self, exc_type: type[AiOsError], category: ErrorCategory, _retriable: bool
    ) -> None:
        assert exc_type.category is category
        assert exc_type("x.y", "boom").to_structured_error(trace=_TRACE).category is category

    @pytest.mark.parametrize(("exc_type", "_category", "retriable"), _HIERARCHY)
    def test_default_retriable_matches_the_documented_table(
        self, exc_type: type[AiOsError], _category: ErrorCategory, retriable: bool
    ) -> None:
        assert exc_type("x.y", "boom").retriable is retriable

    def test_infrastructure_retriability_is_overridable(self) -> None:
        """§3 records `infrastructure` as "Sometimes" — a database that is
        down is worth retrying; a missing config key is not."""
        assert InfrastructureError("db.down", "boom", retriable=True).retriable is True
        assert InfrastructureError("cfg.missing", "boom").retriable is False

    def test_message_is_the_exception_str(self) -> None:
        assert str(PermanentError("x.y", "invalid input")) == "invalid input"


class TestStructuredErrorMapping:
    def test_maps_every_field_one_to_one(self) -> None:
        error = TransientError(
            "llm.rate_limited",
            "slow down",
            retry_after_seconds=1.5,
            details={"provider": "anthropic"},
            trace=_TRACE,
        )
        structured = error.to_structured_error()
        assert structured == StructuredError(
            error_code="llm.rate_limited",
            category=ErrorCategory.TRANSIENT,
            message="slow down",
            retriable=True,
            retry_after_seconds=1.5,
            details={"provider": "anthropic"},
            trace=_TRACE,
        )

    def test_an_explicit_trace_wins_over_the_exceptions_own(self) -> None:
        """The boundary performing the conversion may know more than the
        raise site did."""
        boundary_trace = TraceContext(trace_id="t2", span_id="s2", workflow_id="wf_1")
        error = PermanentError("x.y", "boom", trace=_TRACE)
        assert error.to_structured_error(trace=boundary_trace).trace == boundary_trace

    def test_refuses_to_produce_an_uncorrelated_structured_error(self) -> None:
        """§4.4 marks retry_after_seconds/details nullable and pointedly
        does not mark `trace` — so required is the faithful reading."""
        with pytest.raises(ValueError, match="without a TraceContext"):
            PermanentError("x.y", "boom").to_structured_error()

    def test_structured_error_requires_a_trace(self) -> None:
        with pytest.raises(ValidationError):
            StructuredError(  # type: ignore[call-arg]
                error_code="x.y",
                category=ErrorCategory.PERMANENT,
                message="boom",
                retriable=False,
            )

    def test_structured_error_is_frozen(self) -> None:
        structured = PermanentError("x.y", "boom").to_structured_error(trace=_TRACE)
        with pytest.raises(ValidationError):
            structured.message = "changed"  # type: ignore[misc]

    def test_rejects_a_negative_retry_after(self) -> None:
        with pytest.raises(ValidationError):
            StructuredError(
                error_code="x.y",
                category=ErrorCategory.TRANSIENT,
                message="boom",
                retriable=True,
                retry_after_seconds=-1.0,
                trace=_TRACE,
            )
