"""Errors raised by the Configuration Manager."""


class ConfigurationError(Exception):
    """Configuration could not be loaded, merged, or validated.

    Always raised with a message naming the file and the reason, so a
    misconfigured deployment fails clearly rather than starting with a
    silently wrong value.
    """


class ConfigChangeAuditError(Exception):
    """A ``governance.config_changes`` row could not be written.

    Wraps a persistence-layer failure with a clear message; the
    underlying exception is chained via ``from`` — the same shape as
    :class:`~ai_os_kernel.observability.errors.AuditLogError`.
    """
