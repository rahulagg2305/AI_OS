"""The Prompt Resolver (prompt_engine.md §5) — resolve a *role* to a
concrete ``(prompt_id, version)``, then render through an existing
:class:`~ai_os_kernel.prompt_engine.renderer.PromptEngine`.

§7 step 1 says "an Agent or Workflow requests a prompt by ID" **or by
role**; step 2 says the Engine "resolves the correct version". Both
existing implementations
(:class:`~ai_os_kernel.prompt_engine.renderer.InMemoryPromptEngine`,
:class:`~ai_os_kernel.prompt_engine.catalog.SqlPromptCatalog`) require
an exact ``prompt_id`` *and* an exact ``version``, and both docstrings
name role/alias lookup as deferred. This module is that deferred piece
and nothing more.

**A wrapper, not a fourth ``PromptEngine``.** Resolution and rendering
are genuinely different concerns: resolution decides *which* prompt,
rendering produces its text. Making this a third ``PromptEngine``
implementation would have forced it to re-implement rendering, or to
resolve *and* be resolved through — so it composes one instead, the same
"one real seam, wrapped by the caller" shape
:class:`~ai_os_kernel.llm_gateway.gateway.DispatchingLLMGateway` already
uses over its per-provider gateways. Any ``PromptEngine`` works behind
it, in-memory or SQL, unchanged.

**Bindings are composition-level config, injected — never hardcoded
here.** Which role maps to which prompt is pipeline knowledge, exactly
like ``gate_sources``
(:class:`~ai_os_kernel.workflow_engine.quality_gate.QualityGateStepExecutor`)
and ``step_retry_targets``
(:class:`~ai_os_kernel.workflow_engine.advance_runner.WorkflowAdvanceRunner`)
already are. This class knows the *mechanism*, never a single real role
name.

**Why a role binds to an exact version, not "latest".** §9 makes version
selection config- and experiment-driven, and ADR-0022's reproducibility
requirement means a run must be re-launchable under identical
conditions. A resolver that silently picked the newest version would
make two runs of the same workflow differ with no recorded cause. So a
binding names an exact version, and *changing* which version a role
resolves to is a visible configuration change. Experiment-driven version
pinning (§9) layers on top of this later; it is not built here.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from ai_os_kernel.prompt_engine.errors import PromptRoleNotBoundError
from ai_os_kernel.prompt_engine.models import PromptRenderRequest, PromptRenderResponse
from ai_os_kernel.prompt_engine.renderer import PromptEngine


class PromptBinding(BaseModel):
    """The concrete ``(prompt_id, version)`` one role resolves to."""

    model_config = ConfigDict(frozen=True)

    prompt_id: str
    version: str

    @field_validator("prompt_id", "version")
    @classmethod
    def _is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("prompt_id and version must not be blank")
        return value


class PromptResolver:
    """Resolves a role to a bound prompt and renders it.

    ``bindings`` maps a role name to the :class:`PromptBinding` it
    resolves to. A role absent from the mapping raises
    :class:`~ai_os_kernel.prompt_engine.errors.PromptRoleNotBoundError`
    — deliberately **not** a silent fall-through to treating the role as
    a ``prompt_id``. Guessing would turn a typo'd or unconfigured role
    into a confusing ``PromptNotFoundError`` about an id the caller
    never named, and could resolve a role onto an unrelated prompt that
    happens to share its name.
    """

    def __init__(self, engine: PromptEngine, *, bindings: Mapping[str, PromptBinding]) -> None:
        self._engine = engine
        self._bindings = dict(bindings)

    def binding_for(self, role: str) -> PromptBinding:
        """The binding ``role`` resolves to, without rendering — for a
        caller that needs to record *which* prompt a run used (a run
        manifest, ADR-0022) without paying for a render."""
        binding = self._bindings.get(role)
        if binding is None:
            known = ", ".join(sorted(self._bindings)) or "<none>"
            raise PromptRoleNotBoundError(
                f"role {role!r} is not bound to any prompt — bound roles are: {known}"
            )
        return binding

    async def render_for_role(
        self, role: str, variables: dict[str, Any] | None = None
    ) -> PromptRenderResponse:
        """Resolve ``role``, then render it through the wrapped engine.

        The response carries the *resolved* ``prompt_id``/``version``,
        not the role — §7 step 5 requires the caller learn which prompt
        and version actually produced the text, which is precisely what
        a role indirection would otherwise hide.
        """
        binding = self.binding_for(role)
        return await self._engine.render(
            PromptRenderRequest(
                prompt_id=binding.prompt_id,
                version=binding.version,
                variables=variables or {},
            )
        )
