"""The Voice pack's own real error type."""

from __future__ import annotations


class VoiceIntentError(Exception):
    """Raised for a genuinely invalid intent (a missing required
    field, an invalid decision value), a real permission denial, or a
    real "not found" — never silently swallowed."""
