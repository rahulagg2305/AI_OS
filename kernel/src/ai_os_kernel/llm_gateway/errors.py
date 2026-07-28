"""Errors raised by the LLM Gateway's minimal call-recording writer and by
:class:`~ai_os_kernel.llm_gateway.adapters.anthropic_adapter.AnthropicAdapter`.
"""

from __future__ import annotations

from ai_os_kernel.llm_gateway.error_taxonomy import ErrorCategory


class LLMCallRecordingError(Exception):
    """An ``evaluation.llm_calls`` row could not be recorded.

    Raised for two distinct reasons, always with a clear message: (1) a
    caller-side validation failure — a blank ``workflow_id``/``step_id``,
    or an ``agent_id``/``prompt_id``/``prompt_version`` combination that
    is not either "all present" or "all absent" (the table's ``agent_id``
    and ``prompt_id`` are ``NOT NULL`` with real foreign keys —
    data_model.md §6 — so a partial combination can never be stored);
    (2) a persistence-layer failure (e.g. ``agent_id``/``prompt_id``
    naming a row that does not exist in ``catalog.agents``/
    ``catalog.prompts``), the underlying exception chained via ``from``.
    """


class LLMProviderError(Exception):
    """A real provider adapter (:class:`~ai_os_kernel.llm_gateway.adapters.
    anthropic_adapter.AnthropicAdapter`,
    :class:`~ai_os_kernel.llm_gateway.adapters.local_adapter.LocalAdapter`)
    or the Gateway's own dispatch/routing logic
    (:class:`~ai_os_kernel.llm_gateway.gateway.DispatchingLLMGateway`,
    :class:`~ai_os_kernel.llm_gateway.router.StaticRouter`) could not
    complete a request.

    Carries the LLM Gateway's Error Taxonomy classification
    (:mod:`~ai_os_kernel.llm_gateway.error_taxonomy` — see that module's
    own docstring for the full design): ``category`` and ``error_code``
    (llm_gateway.md §10's own catalogue), ``retriable`` (whether the
    Retry & Fallback Manager's backoff should retry the *same*
    candidate again), and ``retry_after_seconds`` (a provider-supplied
    hint honoured by backoff when present).

    ``category``/``retriable`` default to ``ErrorCategory.TRANSIENT``/
    ``True`` — identical to this class's own behaviour before the Error
    Taxonomy existed, when every raise site and every test constructing
    a bare ``LLMProviderError("message")`` implicitly meant "retriable,
    counts toward the circuit breaker." Only call sites this step
    explicitly updates pass a different classification; every other
    existing raise, and every pre-existing test, is unaffected.

    A model refusing the request is :class:`LLMRefusalError`, not this.
    """

    def __init__(
        self,
        message: str,
        *,
        category: ErrorCategory = ErrorCategory.TRANSIENT,
        error_code: str = "llm.unknown",
        retriable: bool = True,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.error_code = error_code
        self.retriable = retriable
        self.retry_after_seconds = retry_after_seconds


class LLMRefusalError(Exception):
    """The provider's safety classifiers declined a request
    (``stop_reason: "refusal"``) — a real, reachable outcome on
    cyber-capable models, not a fault. llm_gateway.md §5 documents this
    as a distinct outcome from a failure; this step surfaces it as a
    distinct exception for the identical reason, rather than folding it
    into :class:`LLMProviderError` or trying to map it onto this step's
    two-value :class:`~ai_os_kernel.llm_gateway.models.StopReason`.

    Always classified identically — llm_gateway.md §10's own row for
    it ("Model refused the request | permanent | llm.refusal | No") is
    the only classification a refusal can ever have, so it is fixed
    here rather than a constructor parameter.
    :class:`~ai_os_kernel.llm_gateway.gateway.DispatchingLLMGateway`
    still never catches this type at all (a refusal is a valid
    response, not a failure to route around) — these attributes exist
    for completeness and future Observability use, not because
    anything reads them today.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.category = ErrorCategory.PERMANENT
        self.error_code = "llm.refusal"
        self.retriable = False
