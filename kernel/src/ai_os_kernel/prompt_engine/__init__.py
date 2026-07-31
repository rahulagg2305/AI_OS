"""Prompt Engine — versioned, rendered prompts.

See docs/03_architecture/kernel/prompt_engine.md.

Implemented so far (Stage B, minimal slice):

- :class:`PromptEngine` — the ``Protocol`` seam, with a single
  ``render(request) -> response`` method.
- :class:`PromptRenderRequest`/:class:`PromptRenderResponse` — a
  deliberately reduced slice of the documented Resolution Flow (§7). See
  :mod:`ai_os_kernel.prompt_engine.models` for exactly which fields of
  the documented flow are included and which are deferred, and why.
- :class:`InMemoryPromptEngine` — a trivial in-process implementation,
  mirroring :class:`ai_os_kernel.llm_gateway.gateway.EchoLLMGateway`.
  Templates are supplied directly at construction time (no
  ``catalog.prompts`` reader) — useful for tests and any caller with no
  catalog-backed prompt.
- :class:`SqlPromptCatalog` — the second, ``catalog.prompts``-backed
  implementation: reads a template row by ``(prompt_id, version)``,
  SQLAlchemy 2.0 Core against Postgres (ADR-0011). Both implementations
  share the same rendering routine
  (:func:`ai_os_kernel.prompt_engine.renderer.render_template`) and can
  only ever differ in where a template comes from — see
  :mod:`ai_os_kernel.prompt_engine.catalog` for exactly what it reads
  and why.

- :class:`PromptResolver` (added 2026-07-31, ``P02-S03-M07-T04``) — the
  Prompt Resolver subsystem (§5): resolves a **role** to a concrete
  ``(prompt_id, version)`` binding, then renders through any of the
  above. A wrapper, not a third ``PromptEngine`` — resolution and
  rendering are different concerns. Bindings are injected
  composition-level config, and each names an exact version rather than
  "latest", so two runs of the same workflow cannot silently differ
  (ADR-0022). See :mod:`ai_os_kernel.prompt_engine.resolver`.

Not yet implemented: config/experiment-driven version resolution (a role
now binds to an exact version; §9's experiment pinning layers on top and
is not built), prompt composition/inheritance, the
cache-boundary split (§12, ADR-0025), prompt writing/admin APIs, and an
Observability writer recording which prompt version was used (the
existing ``evaluation.llm_calls`` writer already records
``prompt_id``/``prompt_version`` per call —
:class:`~ai_os_kernel.prompted_completion.PromptedCompletionService`).
Agents/workflows do not call this yet — no step-level contract names
which prompt a given workflow step should render (deliberately not
invented here) — and it never calls the LLM Gateway itself —
system_architecture.md's "LLM Abstraction Path" is explicit that the
Prompt Engine returns a rendered prompt to the caller; it is not a
proxy in the call path.
"""

from ai_os_kernel.prompt_engine.catalog import SqlPromptCatalog
from ai_os_kernel.prompt_engine.errors import (
    PromptCatalogError,
    PromptNotFoundError,
    PromptRoleNotBoundError,
    PromptVariableMissingError,
)
from ai_os_kernel.prompt_engine.models import PromptRenderRequest, PromptRenderResponse
from ai_os_kernel.prompt_engine.renderer import InMemoryPromptEngine, PromptEngine, render_template
from ai_os_kernel.prompt_engine.resolver import PromptBinding, PromptResolver

__all__ = [
    "InMemoryPromptEngine",
    "PromptBinding",
    "PromptCatalogError",
    "PromptEngine",
    "PromptNotFoundError",
    "PromptRenderRequest",
    "PromptRenderResponse",
    "PromptResolver",
    "PromptRoleNotBoundError",
    "PromptVariableMissingError",
    "SqlPromptCatalog",
    "render_template",
]
