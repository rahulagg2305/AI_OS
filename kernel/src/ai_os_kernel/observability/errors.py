"""Errors raised by the Observability & Audit writers."""


class AuditLogError(Exception):
    """A ``governance.audit_log`` row could not be written.

    Wraps a persistence-layer failure with a clear message; the
    underlying exception is chained via ``from`` — the identical shape
    already established for every other recorder in this codebase
    (e.g. :class:`~ai_os_kernel.llm_gateway.errors.LLMCallRecordingError`,
    :class:`~ai_os_kernel.workflow_engine.errors.GateResultRecordingError`).
    """
