"""Cache boundary marking (prompt_engine.md §12, ADR-0025 §2) — this
ticket's own Goal: "mark where a provider prompt cache should split."

**A real, exact computation, never a heuristic.** ADR-0025 §2
describes *what* a cache boundary separates — a stable prefix (system
content, invariant instructions) from a volatile suffix (this step's
task and data) — but gives no algorithm for detecting one
automatically from arbitrary rendered text: there is no reliable way
to tell "invariant instructions" from "this step's task" by scanning
text alone, and inventing a heuristic would be exactly the "guess
encoded as architecture" this codebase's own standing discipline
avoids (see ``P02-S04-M10-T03``'s own finding). This module instead
reuses the one place a boundary is genuinely, unambiguously known:
wherever the template's own author placed it, marked with a real,
explicit sentinel — :data:`CACHE_BOUNDARY_MARKER`, syntactically
consistent with :func:`~ai_os_kernel.prompt_engine.renderer.
render_template`'s own existing ``{{variable}}`` placeholder
convention, but a literal marker the author writes, never a value a
caller substitutes.

**The boundary index is computed on the real, *rendered* content, not
the raw template.** §12's own words: "prompts must not interpolate
timestamps, run IDs, or UUIDs before the boundary — doing so silently
destroys the cache hit rate without any visible error." A
``{{variable}}`` placeholder and its substituted value are rarely the
same length, so a boundary position measured on the unrendered
template would be wrong the moment anything before it is substituted.
:func:`render_with_cache_boundary` renders the stable and volatile
templates *separately*, through the real, unchanged
:func:`~ai_os_kernel.prompt_engine.renderer.render_template` (called
twice, once per side — never a parallel substitution routine), then
reports the real length of the rendered stable side as the boundary.

**A standalone utility, not a change to ``PromptRenderResponse`` or
either real ``PromptEngine`` implementation** — the identical
"``compose_fragments`` doesn't touch ``PromptEngine.render()`` either"
shape :mod:`ai_os_kernel.prompt_engine.composition` already
establishes (``P02-S03-M07-T05``). A caller who wants both marks the
boundary in its own already-composed template (:func:`~ai_os_kernel.
prompt_engine.composition.compose_fragments`/
``compose_with_inheritance``), then renders through this module.
"""

from __future__ import annotations

from typing import Any

from ai_os_kernel.prompt_engine.errors import PromptCacheBoundaryError
from ai_os_kernel.prompt_engine.renderer import render_template

# A real, disclosed sentinel -- syntactically consistent with
# render_template()'s own {{variable}} convention, but never a
# variable a caller substitutes: render_template() would raise
# PromptVariableMissingError for it if it ever reached that stage
# unresolved, since nothing ever supplies a "cache_boundary" value. A
# template must resolve this marker with this module first.
CACHE_BOUNDARY_MARKER = "{{cache_boundary}}"


def split_at_cache_boundary(template: str) -> tuple[str, str]:
    """Splits ``template`` into ``(stable_template, volatile_template)``
    at its one real :data:`CACHE_BOUNDARY_MARKER` — both sides may
    still contain unrendered ``{{variable}}`` placeholders of their
    own.

    Raises :class:`~ai_os_kernel.prompt_engine.errors.
    PromptCacheBoundaryError` if the marker is absent (nothing to
    mark) or appears more than once (an ambiguous split).
    """
    count = template.count(CACHE_BOUNDARY_MARKER)
    if count == 0:
        raise PromptCacheBoundaryError(
            f"template does not contain the {CACHE_BOUNDARY_MARKER!r} marker"
        )
    if count > 1:
        raise PromptCacheBoundaryError(
            f"template contains {count} {CACHE_BOUNDARY_MARKER!r} markers; exactly one is required"
        )

    index = template.index(CACHE_BOUNDARY_MARKER)
    return template[:index], template[index + len(CACHE_BOUNDARY_MARKER) :]


def render_with_cache_boundary(template: str, variables: dict[str, Any]) -> tuple[str, int]:
    """Renders ``template`` (which must contain exactly one real
    :data:`CACHE_BOUNDARY_MARKER`), returning ``(content,
    cache_boundary_index)`` — prompt_engine.md §12's own documented
    response shape. ``content[:cache_boundary_index]`` is the real,
    rendered stable prefix; ``content[cache_boundary_index:]`` is the
    real, rendered volatile suffix (ADR-0025 §2).
    """
    stable_template, volatile_template = split_at_cache_boundary(template)
    stable_content = render_template(stable_template, variables)
    volatile_content = render_template(volatile_template, variables)
    return stable_content + volatile_content, len(stable_content)
