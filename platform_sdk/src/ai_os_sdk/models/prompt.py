"""The ``PromptRegistry`` boundary model (``platform_sdk.md`` §5.2).

**This is the narrowed v1.0.0 shape**, per §5.2's dated
*v1.0.0 Reconciliation Decision* block (recorded 2026-07-29,
``platform_sdk_v1_scope.md`` step 2a). The prose documents
``RenderedPrompt`` with five fields (``prompt_id``, ``version``,
``content``, ``variables_used``, ``cache_boundary_index?``);
``variables_used`` has no producer anywhere, and
``cache_boundary_index`` requires the Prompt Cache Planner
(ADR-0025, unbuilt). Both are additive later, once something
produces them — not invented ahead of a real caller.

This model is otherwise a field-for-field mirror of the real, working
``ai_os_kernel.prompt_engine.models.PromptRenderResponse``, which
carries exactly these same three fields.

``PromptDefinition`` (the *stored* §6 Prompt Contract — name, owner,
template, ``input_schema``, tags, metadata) is **not defined at all in
v1.0.0**: it is the return type of the deferred ``get()`` method, and no
implementation of that stored-prompt lookup exists at any layer
(``SqlPromptCatalog`` exposes ``render()`` and nothing else).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator


class RenderedPrompt(BaseModel):
    """The result of rendering one prompt (``platform_sdk.md`` §5.2).

    Records ``prompt_id`` + ``version`` for the run manifest
    ([ADR-0022](../../18_decision_log/adr/ADR-0022-reproducibility-over-determinism.md)) —
    reproducing a run requires knowing exactly which version of a
    prompt actually rendered, not merely which version was requested
    (the two agree today, since nothing resolves a default on a
    caller's behalf, but recording the *result's* own version is what
    keeps the manifest correct if that ever changes).
    """

    model_config = ConfigDict(frozen=True)

    prompt_id: str
    version: str
    content: str

    @field_validator("prompt_id", "version")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be blank")
        return value
