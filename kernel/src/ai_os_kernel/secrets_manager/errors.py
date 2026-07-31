"""Errors raised by Secrets Management."""


class SecretResolutionError(Exception):
    """A secret reference could not be parsed, or a provider could not
    resolve it to a value.

    Always raised with a message naming the reference (never a secret
    *value* — there is never one to name at this point) and the reason,
    so a missing or malformed reference fails clearly.
    """


class AccessDeniedError(Exception):
    """A principal without ``secret:access`` attempted to resolve a
    secret through :class:`~ai_os_kernel.secrets_manager.access_broker.
    AccessBroker`. The attempt is still audited as denied
    (secrets_management.md §8) — this exception is raised *after* that
    audit row is written, never instead of it.
    """
