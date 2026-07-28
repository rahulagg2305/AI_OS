"""Unit tests for ai_os_kernel.llm_gateway.errors' Error Taxonomy
fields on LLMProviderError/LLMRefusalError: no network, no I/O.
"""

from ai_os_kernel.llm_gateway.error_taxonomy import ErrorCategory
from ai_os_kernel.llm_gateway.errors import LLMProviderError, LLMRefusalError


def test_a_bare_llm_provider_error_defaults_to_transient_and_retriable() -> None:
    # This step's own "preserve existing behaviour where no explicit
    # classification applies" requirement: every pre-existing call site
    # (and every pre-existing test) constructs LLMProviderError with
    # just a message — this default must reproduce the identical
    # "retried by backoff, counted by the circuit breaker" behaviour
    # that was implicit before the Error Taxonomy existed.
    error = LLMProviderError("something went wrong")

    assert error.category == ErrorCategory.TRANSIENT
    assert error.error_code == "llm.unknown"
    assert error.retriable is True
    assert error.retry_after_seconds is None
    assert str(error) == "something went wrong"


def test_an_llm_provider_error_can_carry_an_explicit_classification() -> None:
    error = LLMProviderError(
        "invalid request",
        category=ErrorCategory.PERMANENT,
        error_code="llm.invalid_request",
        retriable=False,
        retry_after_seconds=None,
    )

    assert error.category == ErrorCategory.PERMANENT
    assert error.error_code == "llm.invalid_request"
    assert error.retriable is False


def test_an_llm_provider_error_can_carry_a_retry_after_hint() -> None:
    error = LLMProviderError(
        "rate limited",
        category=ErrorCategory.TRANSIENT,
        error_code="llm.rate_limited",
        retriable=True,
        retry_after_seconds=12.5,
    )

    assert error.retry_after_seconds == 12.5


def test_an_llm_refusal_error_is_always_classified_as_a_permanent_refusal() -> None:
    error = LLMRefusalError("the model declined")

    assert error.category == ErrorCategory.PERMANENT
    assert error.error_code == "llm.refusal"
    assert error.retriable is False
    assert str(error) == "the model declined"
