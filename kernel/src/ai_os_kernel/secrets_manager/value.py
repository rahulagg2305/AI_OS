"""The ``SecretValue`` wrapper (ADR-0024 rule 2, secrets_management.md
§6): a resolved secret's ``__str__``/``__repr__`` return ``***``, so
accidental logging, string interpolation, or inclusion in an error
message cannot leak it — the raw value requires an explicit
:meth:`SecretValue.reveal` call. This is enforced by the type, not by
reviewer vigilance.
"""

from __future__ import annotations


class SecretValue:
    """Holds one resolved secret value. Never compare, log, or persist
    the result of :meth:`reveal` beyond the single call site that needs
    it (ADR-0024 rule 1: resolution is late and narrow)."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        """The only way to obtain the raw secret value."""
        return self._value

    def __str__(self) -> str:
        return "***"

    def __repr__(self) -> str:
        return "SecretValue('***')"
