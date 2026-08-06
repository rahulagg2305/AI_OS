"""Parses a structured Markdown specification into a validated list of
discrete requirement-item strings (FR-030, `P03-S03-M30-T02`) —
`se.delivery_pipeline`'s own new, additive, optional counterpart to its
pre-existing, still-required, free-text `requirement` input (design fork
resolved with the product owner: additive, not a breaking replacement of
`requirement` — zero behaviour change for every existing caller that
never supplies `specification`).

**The one real structural convention this module defines, since nothing
elsewhere in this codebase names one**: a "structured Markdown
specification" is a document containing one or more top-level, un-nested
bullet list items — a line starting with `-` or `*` immediately, with no
leading whitespace. Each becomes one requirement item. Any indented,
non-blank line directly beneath a bullet — including one that itself
starts with `-`/`*` — is folded into that bullet's own item text as a
continuation, not treated as a nested item of its own: a deliberate
simplification, not a full CommonMark list parser. Any other line (a
heading, a blank line, a preamble paragraph before the first bullet) is
ignored, not an error — a spec may carry prose framing around its real
list.

Used by
:mod:`ai_os_pack_software_engineering.agents.requirements_analyst`
only — this parser has no Kernel caller and no Kernel import: the
Kernel's own ``se.delivery_pipeline`` composition
(:mod:`ai_os_kernel.workflow_engine.delivery_pipeline`) never imports
pack code (every real caller in that module confirms this — only test
files cross that boundary, for fixture convenience), so parsing a
caller-supplied ``specification`` string happens inside the
Requirements Analyst agent itself, the first, and today only, real
consumer of that input.
"""

from __future__ import annotations

import re

_BULLET_PATTERN = re.compile(r"^[-*]\s+(.*)$")


class SpecificationParseError(ValueError):
    """Raised when a caller-supplied ``specification`` string is not a
    real structured Markdown specification per this module's own
    documented convention — either it names no top-level bullet item at
    all, or one of them is empty once stripped."""


def parse_markdown_specification(text: str) -> list[str]:
    """Real, deterministic, dependency-free parsing — no new dependency
    on a Markdown library, since this module's own bullet-list
    convention (see module docstring) is simple enough for a direct,
    line-based scan."""
    items: list[str] = []
    current: list[str] | None = None

    for raw_line in text.splitlines():
        bullet_match = _BULLET_PATTERN.match(raw_line)
        if bullet_match is not None:
            if current is not None:
                items.append(" ".join(current).strip())
            current = [bullet_match.group(1).strip()]
            continue
        if current is not None and raw_line.strip() and raw_line[:1].isspace():
            current.append(raw_line.strip())

    if current is not None:
        items.append(" ".join(current).strip())

    if not items:
        raise SpecificationParseError(
            "no top-level bullet item ('- ' or '* ', no leading whitespace) "
            "was found in the specification"
        )

    empty_positions = [index + 1 for index, item in enumerate(items) if not item]
    if empty_positions:
        raise SpecificationParseError(
            f"item(s) at position(s) {empty_positions} are empty after stripping"
        )

    return items
