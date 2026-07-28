"""Errors raised by the Configuration Manager."""


class ConfigurationError(Exception):
    """Configuration could not be loaded, merged, or validated.

    Always raised with a message naming the file and the reason, so a
    misconfigured deployment fails clearly rather than starting with a
    silently wrong value.
    """
