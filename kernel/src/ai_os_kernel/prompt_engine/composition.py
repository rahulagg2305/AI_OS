"""Prompt composition and inheritance — this ticket's own Goal ("build
a prompt from reusable fragments") and title ("Composition and
inheritance"), matching prompt_engine.md §5's "Composition Engine
(optional)" and §3's "Support prompt inheritance / composition where
useful."

**A pure, in-memory fragment joiner — no new persisted schema, no new
``PromptEngine`` implementation, no parallel rendering mechanism.**
§6's Prompt Contract has no fragment/parent/``extends`` field at all,
and §5 marks the Composition Engine itself optional — there is no
documented, field-level mechanics to build against, so this module
invents none beyond what its own ticket literally asks for: joining
already-known fragment strings, then handing the joined result to the
already-real, unchanged
:func:`~ai_os_kernel.prompt_engine.renderer.render_template`. A real,
persisted fragment catalog (a new ``catalog.prompt_fragments`` table)
would be the same class of schema-authority decision
``P02-S03-M08-T10`` needed a documented section for — deliberately not
built here, since "optional"-marked scope and this ticket's own
3-line Goal/Input/Output do not ask for one.

**Inheritance is a named-fragment-map override, not a schema.** A
``parent`` is an ordered ``{name: content}`` mapping; ``overrides``
supplies new content for specific names, inheriting every other name's
content from ``parent`` unchanged. Composition order always follows
``parent``'s own key order — an override changes *what* a name
contains, never *where* it falls in the composed result. An override
naming a fragment the parent does not declare is rejected
(:class:`~ai_os_kernel.prompt_engine.errors.PromptFragmentOverrideError`),
the identical "no guessing a typo'd or unconfigured name into
something else" discipline
:class:`~ai_os_kernel.prompt_engine.resolver.PromptResolver` already
establishes for role binding — silently accepting an unknown override
name could mean a genuine typo goes unnoticed, or (accepted as a new,
appended fragment instead) invisibly changes composition order in a
way "override" does not imply.

:func:`render_composed` is the end-to-end convenience: compose, then
render through the real, unchanged :func:`render_template` — the
"prove the whole real path, not just half of it" shape already used
throughout this session's own retrieval/context work.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ai_os_kernel.prompt_engine.errors import PromptCompositionError, PromptFragmentOverrideError
from ai_os_kernel.prompt_engine.renderer import render_template

# A real, disclosed default -- blank-line separated, matching how a
# human author would naturally join independent prose sections; always
# overridable per call, never silently baked into a caller's own
# fragment content.
DEFAULT_FRAGMENT_SEPARATOR = "\n\n"


def compose_fragments(
    fragments: Sequence[str], *, separator: str = DEFAULT_FRAGMENT_SEPARATOR
) -> str:
    """Joins ordered fragment strings into one combined template —
    still containing any ``{{variable}}`` placeholders a fragment
    itself declared, unrendered until :func:`render_template` runs.
    """
    if not fragments:
        raise PromptCompositionError("fragments must not be empty")
    return separator.join(fragments)


def compose_with_inheritance(
    *,
    parent: Mapping[str, str],
    overrides: Mapping[str, str] | None = None,
    separator: str = DEFAULT_FRAGMENT_SEPARATOR,
) -> str:
    """Merges ``overrides`` onto ``parent``'s named fragments (child
    wins for any name it declares; every other name is inherited from
    ``parent`` unchanged), then composes the result in ``parent``'s own
    key order. See this module's own docstring for why an unknown
    override name is rejected, not silently accepted."""
    overrides = overrides or {}
    unknown = sorted(set(overrides) - set(parent))
    if unknown:
        raise PromptFragmentOverrideError(
            f"override(s) name fragment(s) the parent does not declare: {', '.join(unknown)}"
        )

    merged = [overrides.get(name, content) for name, content in parent.items()]
    return compose_fragments(merged, separator=separator)


def render_composed(
    fragments: Sequence[str],
    variables: dict[str, Any],
    *,
    separator: str = DEFAULT_FRAGMENT_SEPARATOR,
) -> str:
    """Composes ``fragments``, then renders the combined template
    through the real, unchanged :func:`render_template` — the full,
    real path in one call."""
    return render_template(compose_fragments(fragments, separator=separator), variables)
