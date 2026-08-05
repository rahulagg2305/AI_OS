"""Errors raised by the Prompt Engine's minimal render path."""


class PromptNotFoundError(Exception):
    """No template is registered for the requested ``(prompt_id, version)``
    pair — raised by every :class:`~ai_os_kernel.prompt_engine.renderer.
    PromptEngine` implementation before any rendering is attempted,
    whichever backs it: :class:`~ai_os_kernel.prompt_engine.renderer.
    InMemoryPromptEngine`'s in-process map, or
    :class:`~ai_os_kernel.prompt_engine.catalog.SqlPromptCatalog`'s
    ``catalog.prompts`` lookup.
    """


class PromptCatalogError(Exception):
    """A ``catalog.prompts`` lookup failed for a reason other than "no
    such row" — a persistence-layer failure (e.g. a connection error),
    the underlying exception chained via ``from``. A missing row is
    :class:`PromptNotFoundError`, not this.
    """


class PromptRoleNotBoundError(Exception):
    """A role handed to :class:`~ai_os_kernel.prompt_engine.resolver.
    PromptResolver` is not bound to any prompt.

    Distinct from :class:`PromptNotFoundError`, which means "this role
    resolved, but the prompt it names does not exist". Keeping them
    apart matters: the first is a *configuration* gap (a missing or
    typo'd binding), the second a *catalog* gap (a missing prompt row),
    and they are fixed in completely different places.
    """


class PromptVariableMissingError(Exception):
    """The template references one or more ``{{variable}}`` placeholders
    that the request's ``variables`` did not supply.

    This is the Variable Validator (prompt_engine.md §5) reduced to its
    smallest honest form: required variables are derived from the
    placeholders literally present in this call's template text, not
    from a declared ``input_schema`` (§6's Prompt Contract field) —
    reading a declared schema would require the same deferred real
    prompt catalog loading. Raised before any substitution is performed,
    listing every missing name so a caller sees the whole problem at
    once, not one name per retry.
    """


class PromptCompositionError(Exception):
    """A fragment composition request was itself invalid — e.g. an
    empty fragment sequence, which cannot compose to any meaningful
    template (:mod:`ai_os_kernel.prompt_engine.composition`).
    """


class PromptFragmentOverrideError(Exception):
    """An inheritance override named a fragment the parent does not
    declare (:mod:`ai_os_kernel.prompt_engine.composition`).

    Deliberately not a silent no-op or a silently-appended new
    fragment — the identical "no guessing a typo'd or unconfigured
    name into something else" discipline
    :class:`PromptRoleNotBoundError` already establishes for role
    binding.
    """


class PromptCacheBoundaryError(Exception):
    """A template's real ``{{cache_boundary}}`` marker is missing, or
    appears more than once (:mod:`ai_os_kernel.prompt_engine.
    cache_boundary`) — an ambiguous split is real content the caller
    must fix, not something this module arbitrates on its behalf.
    """
