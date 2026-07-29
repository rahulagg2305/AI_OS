"""The one platform error taxonomy: :class:`~ai_os_sdk.models.error.ErrorCategory`,
:class:`~ai_os_sdk.models.error.StructuredError`, and the :class:`AiOsError`
exception hierarchy (``platform_sdk.md`` §4.4, matching
``docs/03_architecture/workflow/error_handling_retry.md`` §3 and §8).

**Six categories, not four and not the LLM Gateway's four.**
``error_handling_retry.md`` §3 is explicit that this is "the single
platform error taxonomy … there is no second, provider-specific
taxonomy." The Kernel's existing
``ai_os_kernel.llm_gateway.error_taxonomy.ErrorCategory`` implements
four of these six (``transient``, ``permanent``, ``infrastructure``,
``budget``) and deliberately excludes ``quality``/``security`` because a
*provider call* can never be either — a correct narrowing of this set
for that one component's purpose, not a competing definition. Nothing in
the Kernel changes as a result of this module existing; migrating the
Gateway's local enum onto this one is Kernel-side work, tracked as
``feature_inventory.md`` module 44.

**Every exception maps 1:1 onto a :class:`~ai_os_sdk.models.error.StructuredError`**
(§4.4: "Each maps 1:1 onto a ``StructuredError``, so there is no
translation layer and no possibility of an exception whose category
disagrees with its serialised form"). That mapping is
:meth:`AiOsError.to_structured_error`, and the agreement is structural:
``category`` is a class attribute of the exception type, so it cannot
be set to disagree with the class that raised it.

**``ErrorCategory``/``StructuredError`` are defined in
:mod:`ai_os_sdk.models.error`, not here, and re-exported below** —
moved there in step 6 so that a *model* needing ``StructuredError``
(:class:`~ai_os_sdk.models.tool.ToolResult`) never has to import this
``errors`` package, which would create a real import cycle (this
package already imports :class:`~ai_os_sdk.models.common.TraceContext`).
See that module's own docstring for the full reasoning. Only the
exception hierarchy itself — the classes actually *raised*, as opposed
to the data shapes they carry — is defined here.

Consumed by nothing yet — the Protocols and boundary contracts that
carry these types land in later steps of
``docs/03_architecture/platform/platform_sdk_v1_scope.md``.
"""

from __future__ import annotations

from typing import Any, ClassVar

from ai_os_sdk.models.common import TraceContext
from ai_os_sdk.models.error import ErrorCategory as ErrorCategory
from ai_os_sdk.models.error import StructuredError as StructuredError

# The `Retriable` column of error_handling_retry.md §3, verbatim.
# `infrastructure` is "Sometimes" there, which is why AiOsError accepts
# an explicit `retriable` override rather than deriving it unconditionally
# from the category — see AiOsError.__init__.
_DEFAULT_RETRIABLE: dict[ErrorCategory, bool] = {
    ErrorCategory.TRANSIENT: True,
    ErrorCategory.PERMANENT: False,
    ErrorCategory.QUALITY: False,
    ErrorCategory.INFRASTRUCTURE: False,
    ErrorCategory.BUDGET: False,
    ErrorCategory.SECURITY: False,
}


class AiOsError(Exception):
    """Base of the platform exception hierarchy (``platform_sdk.md``
    §4.4). Catch this to catch every platform error regardless of
    category.

    **Not raised directly** — it declares no category, so there is
    nothing for :meth:`to_structured_error` to report. Constructing it
    raises :class:`TypeError` rather than deferring the failure to a
    later, more confusing ``AttributeError``
    (``CODING_STANDARDS_AND_BEST_PRACTICES.md``: "Fail fast and fail
    clearly"). Use one of the six subclasses.

    ``trace`` is optional here, unlike on :class:`StructuredError`: a
    raise site inside a library genuinely may not know its trace
    context, and fabricating one would be worse than requiring the
    boundary to supply the real one at conversion time.
    """

    category: ClassVar[ErrorCategory]
    """Set by each concrete subclass. Absent on this base, which is what
    makes the base non-raisable."""

    def __init__(
        self,
        error_code: str,
        message: str,
        *,
        retriable: bool | None = None,
        retry_after_seconds: float | None = None,
        details: dict[str, Any] | None = None,
        trace: TraceContext | None = None,
    ) -> None:
        if type(self) is AiOsError:
            raise TypeError(
                "AiOsError is the catch-all base of the platform error hierarchy and "
                "declares no category; raise one of its six concrete subclasses instead "
                "(TransientError, PermanentError, QualityError, InfrastructureError, "
                "BudgetExceededError, SecurityError)."
            )
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.retry_after_seconds = retry_after_seconds
        self.details = details
        self.trace = trace
        # `retriable` is overridable rather than derived purely from the
        # category because error_handling_retry.md §3 records
        # `infrastructure` as "Sometimes" — a database that is down right
        # now is worth retrying; a missing configuration key is not.
        # Every other category has a fixed value in that table, and the
        # default supplies it.
        self.retriable = _DEFAULT_RETRIABLE[type(self).category] if retriable is None else retriable

    def to_structured_error(self, *, trace: TraceContext | None = None) -> StructuredError:
        """The 1:1 mapping onto :class:`StructuredError` (§4.4).

        ``trace`` supplements the exception's own — an explicit argument
        wins, so a boundary that knows more than the raise site did can
        supply it. Raises :class:`ValueError` when neither is available,
        because a ``StructuredError`` without correlation is not a valid
        one (see that class's docstring) and silently inventing an empty
        trace would defeat the requirement.
        """
        effective_trace = trace if trace is not None else self.trace
        if effective_trace is None:
            raise ValueError(
                f"cannot convert {type(self).__name__}(error_code={self.error_code!r}) to a "
                "StructuredError without a TraceContext: platform_sdk.md §4.4 requires one. "
                "Pass trace= at the boundary, or construct the exception with trace=."
            )
        return StructuredError(
            error_code=self.error_code,
            category=type(self).category,
            message=self.message,
            retriable=self.retriable,
            retry_after_seconds=self.retry_after_seconds,
            details=self.details,
            trace=effective_trace,
        )


class TransientError(AiOsError):
    """May succeed on retry (:attr:`ErrorCategory.TRANSIENT`)."""

    category: ClassVar[ErrorCategory] = ErrorCategory.TRANSIENT


class PermanentError(AiOsError):
    """Will not succeed with the same input
    (:attr:`ErrorCategory.PERMANENT`)."""

    category: ClassVar[ErrorCategory] = ErrorCategory.PERMANENT


class QualityError(AiOsError):
    """Raised by a Quality Gate or review
    (:attr:`ErrorCategory.QUALITY`). Requires corrective work, not a
    retry."""

    category: ClassVar[ErrorCategory] = ErrorCategory.QUALITY


class InfrastructureError(AiOsError):
    """Platform-side failure (:attr:`ErrorCategory.INFRASTRUCTURE`).

    The one category whose retriability is case-by-case
    (``error_handling_retry.md`` §3: "Sometimes"), so pass
    ``retriable=True`` explicitly when the specific failure warrants it.
    Defaults to ``False``: refusing to retry something retriable costs
    one escalation, whereas retrying something permanently broken costs
    an unbounded loop.
    """

    category: ClassVar[ErrorCategory] = ErrorCategory.INFRASTRUCTURE


class BudgetExceededError(AiOsError):
    """A declared ceiling was reached (:attr:`ErrorCategory.BUDGET`).

    Named ``BudgetExceededError``, not ``BudgetError``, because
    ``platform_sdk.md`` §4.4 and ``error_handling_retry.md`` §8 both
    specify that name — and it is already referenced by that name in
    ``llm_gateway.md`` §9 and ``security_architecture.md`` §13, neither
    of which had a class to point at until now.
    """

    category: ClassVar[ErrorCategory] = ErrorCategory.BUDGET


class SecurityError(AiOsError):
    """An authorization or policy denial
    (:attr:`ErrorCategory.SECURITY`). Never retried automatically; must
    be audited (``error_handling_retry.md`` §3)."""

    category: ClassVar[ErrorCategory] = ErrorCategory.SECURITY
