"""The minimal Prompt Engine contract: one render request in, one
rendered prompt out.

This is a deliberately reduced slice of the full Prompt Engine
(docs/03_architecture/kernel/prompt_engine.md §5), which documents six
internal subsystems (Prompt Registry, Version Manager, Template
Renderer, Variable Validator, Prompt Resolver, Composition Engine
(optional), Observability Hook). Only a Template Renderer and a minimal
Variable Validator sit behind this ``Protocol`` — registry-backed
storage, version resolution, role/alias lookup, prompt composition, and
observability recording are all out of scope for this step, the same
"one Protocol, one trivial implementation" reduction already applied to
:mod:`ai_os_kernel.llm_gateway.gateway`.

**Deliberately not a proxy to the LLM Gateway.** system_architecture.md's
"LLM Abstraction Path" is explicit: "The Prompt Engine returns a
rendered prompt to the caller; it is not a proxy in the call path. The
caller then invokes the LLM Gateway." Nothing here constructs an
``LLMRequest`` or calls :class:`~ai_os_kernel.llm_gateway.gateway.
LLMGateway` — a caller renders a prompt, then separately composes an
``LLMRequest`` from the result, mirroring the same "composed explicitly
by the caller" shape already established for
:class:`~ai_os_kernel.llm_gateway.call_recorder.LLMCallRecorder`.

**Templating** is restricted to plain ``{{variable_name}}`` substitution
— prompt_engine.md §12 requires "a restricted, non-executing syntax:
variable substitution and simple conditionals only. Arbitrary code in a
template would put logic in prompts, which the Governance Framework
prohibits." Even the documented "simple conditionals" half of that
restricted syntax is deferred here: this step implements substitution
only, not a second, smaller template language of its own.

:func:`render_template` is the one substitution routine shared by every
``PromptEngine`` implementation — :class:`InMemoryPromptEngine` here and
:class:`~ai_os_kernel.prompt_engine.catalog.SqlPromptCatalog` — so the
two implementations can only ever differ in *where a template comes
from*, never in what rendering means.
"""

from __future__ import annotations

import re
from typing import Any, Protocol

from ai_os_kernel.prompt_engine.errors import PromptNotFoundError, PromptVariableMissingError
from ai_os_kernel.prompt_engine.models import PromptRenderRequest, PromptRenderResponse

_PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


def render_template(template: str, variables: dict[str, Any]) -> str:
    """Substitute every ``{{variable_name}}`` placeholder in ``template``
    with its value from ``variables``.

    Raises :class:`PromptVariableMissingError`, naming every missing
    variable at once, before any substitution is performed — required
    variables are derived from the placeholders literally present in
    ``template``, not a declared ``input_schema`` (prompt_engine.md §6),
    which would need real prompt catalog loading. Extra variables not
    referenced by the template are silently ignored.
    """
    required = set(_PLACEHOLDER_PATTERN.findall(template))
    missing = sorted(required - variables.keys())
    if missing:
        raise PromptVariableMissingError(
            f"template is missing required variables: {', '.join(missing)}"
        )

    return _PLACEHOLDER_PATTERN.sub(lambda match: str(variables[match.group(1)]), template)


class PromptEngine(Protocol):
    """The sole seam through which anything in AI_OS renders a versioned
    prompt (prompt_engine.md §1: "Agents and workflows never construct
    raw prompts in an uncontrolled way; they request prompts through the
    Prompt Engine."). No version resolution, no composition behind this
    Protocol yet — those are later steps."""

    async def render(self, request: PromptRenderRequest) -> PromptRenderResponse: ...


class InMemoryPromptEngine:
    """The one trivial in-process implementation for this step.

    Templates are supplied directly at construction time, keyed by
    ``(prompt_id, version)`` — not loaded from ``catalog.prompts``
    (see :class:`~ai_os_kernel.prompt_engine.catalog.SqlPromptCatalog`
    for the reader-backed implementation). It exists to prove the render
    contract (resolve by id+version, validate variables, substitute,
    return content + which prompt/version was used) works end to end
    with no database at all, mirroring ``EchoLLMGateway``'s "always
    honest, never disguised as a real component" role — useful for
    tests and any caller that genuinely has no catalog-backed prompt.
    """

    def __init__(self, templates: dict[tuple[str, str], str]) -> None:
        self._templates = dict(templates)

    async def render(self, request: PromptRenderRequest) -> PromptRenderResponse:
        key = (request.prompt_id, request.version)
        template = self._templates.get(key)
        if template is None:
            raise PromptNotFoundError(
                f"no template registered for prompt_id={request.prompt_id!r} "
                f"version={request.version!r}"
            )

        content = render_template(template, request.variables)

        return PromptRenderResponse(
            prompt_id=request.prompt_id,
            version=request.version,
            content=content,
        )
