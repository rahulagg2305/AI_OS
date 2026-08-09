"""Speech Gateway's own real error type — mirrors
:class:`~ai_os_kernel.llm_gateway.errors.LLMProviderError`'s exact
shape for the identical real condition (an alias with no configured
route)."""

from __future__ import annotations


class SpeechProviderError(Exception):
    """Raised when a requested alias has no configured provider — the
    identical "deny, do not guess" behaviour
    :class:`~ai_os_kernel.llm_gateway.router.StaticRouter` already
    establishes for an unknown ``model_alias``."""
