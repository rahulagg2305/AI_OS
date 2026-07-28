"""Minimal ``PromptRenderRequest``/``PromptRenderResponse`` contract shapes.

These model the runtime **call envelope** of the Resolution Flow
(docs/03_architecture/kernel/prompt_engine.md §7, steps 1-5: request by
id -> resolve version -> validate variables -> render -> return rendered
content with prompt id + version) — not the persisted Prompt Contract
itself (§6: id, name, version, description, owner, template,
input_schema, tags, metadata). That is a stored, versioned catalog
entity (``catalog.prompts``, already schema'd but with no reader yet);
"real prompt catalog loading beyond what is strictly needed" is this
step's own explicit fence, so nothing here reads or models that stored
shape. The same "trivial slice of the documented flow, not the whole
document" reduction already used for
:mod:`ai_os_kernel.llm_gateway.models`.

**Included, and why each survives the cut:**

- ``prompt_id`` — REQUIRED (§7 step 1: "an Agent or Workflow requests a
  prompt by ID"). Request-by-role/alias is also mentioned in step 1 but
  needs the Prompt Resolver subsystem (§5) to map a role to a concrete
  id — out of scope; callers name a prompt id directly.
- ``version`` — REQUIRED and caller-supplied explicitly. §7 step 2 says
  the Prompt Engine "resolves the correct version (config or experiment
  context)" — that resolution logic is the Version Manager/Prompt
  Resolver subsystems (§5) and §9's config-driven defaults/experiment
  pinning, all out of scope. A caller-supplied exact version is the
  honest remaining shape: nothing here silently picks a version on the
  caller's behalf.
- ``variables`` — the runtime values substituted into the template
  (§7 step 3 "required variables are validated", step 4 "template is
  rendered").
- Response ``prompt_id``/``version`` — echoed back, exactly §7 step 5's
  "rendered prompt is returned together with metadata (prompt id +
  version)".
- Response ``content`` — the rendered text itself (§7 step 4/5).

**Excluded, each belonging to an explicitly deferred subsystem:**
``cache_boundary_index`` (§12's stable-prefix/volatile-suffix split for
the LLM Gateway's prompt-cache breakpoint, ADR-0025 — caching layers are
this step's own explicit fence); the full §6 Prompt Contract fields
(``name``, ``description``, ``owner``, ``template``, ``input_schema``,
``tags``, ``metadata``) — these describe the *stored* prompt, not this
call's request/response, and belong to real prompt catalog loading;
role/alias resolution and experiment-forced version pinning (Prompt
Resolver, §9) — no resolution logic exists here, only an explicit,
caller-supplied version.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PromptRenderRequest(BaseModel):
    """A request to render one prompt — see this module's docstring for
    exactly which fields of the full §7 flow this covers, and why."""

    model_config = ConfigDict(frozen=True)

    prompt_id: str
    version: str
    variables: dict[str, Any] = Field(default_factory=dict)

    @field_validator("prompt_id")
    @classmethod
    def _prompt_id_is_not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("prompt_id must not be blank")
        return value

    @field_validator("version")
    @classmethod
    def _version_is_not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("version must not be blank")
        return value


class PromptRenderResponse(BaseModel):
    """A rendered prompt — see this module's docstring for exactly which
    fields of the full §7 flow this covers, and why."""

    model_config = ConfigDict(frozen=True)

    prompt_id: str
    version: str
    content: str
