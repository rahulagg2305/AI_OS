"""The Prompt Cache Planner (llm_gateway.md §3; ADR-0025 §2) — this
ticket's own Goal: "plan cache boundaries to reduce cost." Consumes
the real ``cache_boundary_index`` :func:`~ai_os_kernel.prompt_engine.
cache_boundary.render_with_cache_boundary` already produces
(``P02-S03-M07-T06``) — no parallel boundary-computation mechanism.

**Provider-neutral planning, provider-specific translation — the
identical split :mod:`~ai_os_kernel.llm_gateway.adapters.
anthropic_adapter` already draws between the Gateway and its one real
adapter.** This module only decides *which real characters* are
stable vs. volatile (:class:`PromptCacheSegment`); it never constructs
a provider SDK payload. :class:`~ai_os_kernel.llm_gateway.adapters.
anthropic_adapter.AnthropicAdapter` — "the ONLY place a provider SDK is
imported" (its own module docstring) — is where a segment list becomes
a real Anthropic ``TextBlockParam`` with a real
``cache_control: {"type": "ephemeral"}`` marker (verified against the
installed ``anthropic`` SDK's own ``CacheControlEphemeralParam``/
``TextBlockParam`` types, not guessed). A second real provider adapter
would add its own translation the same way, unchanged here.

**Anthropic-specific today, not a Protocol — ADR-0004's own rule.**
Only one real provider adapter exists; a ``PromptCachePlanner``
Protocol with one real implementation would be exactly the
"interface before a second real implementation exists" ADR-0004
already forbids. This module is a plain function, reused directly by
the one real adapter that needs it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from ai_os_kernel.llm_gateway.errors import LLMPromptCacheError


class PromptCacheSegment(BaseModel):
    """One real slice of content, marked whether it sits before
    (``cacheable=True``) or after (``cacheable=False``) the real cache
    boundary — ADR-0025 §2's "stable prefix"/"volatile suffix", without
    committing to any one provider's own wire shape for marking it."""

    model_config = ConfigDict(frozen=True)

    content: str
    cacheable: bool


def plan_prompt_cache_segments(content: str, cache_boundary_index: int) -> list[PromptCacheSegment]:
    """Splits ``content`` at ``cache_boundary_index`` (the real value
    :func:`~ai_os_kernel.prompt_engine.cache_boundary.
    render_with_cache_boundary` returns) into real, ordered segments —
    a stable, cacheable prefix followed by a volatile, non-cacheable
    suffix. Either side is omitted, not returned empty, when the
    boundary sits at one end of ``content``.
    """
    if not 0 <= cache_boundary_index <= len(content):
        raise LLMPromptCacheError(
            f"cache_boundary_index {cache_boundary_index} is out of range for "
            f"content of length {len(content)}"
        )

    stable = content[:cache_boundary_index]
    volatile = content[cache_boundary_index:]

    segments = []
    if stable:
        segments.append(PromptCacheSegment(content=stable, cacheable=True))
    if volatile:
        segments.append(PromptCacheSegment(content=volatile, cacheable=False))

    if not segments:
        raise LLMPromptCacheError("content must not be blank")

    return segments
