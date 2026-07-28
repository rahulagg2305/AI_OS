"""Errors raised by Secrets Management."""


class SecretResolutionError(Exception):
    """A secret reference could not be parsed, or a provider could not
    resolve it to a value.

    Always raised with a message naming the reference (never a secret
    *value* — there is never one to name at this point) and the reason,
    so a missing or malformed reference fails clearly.
    """
