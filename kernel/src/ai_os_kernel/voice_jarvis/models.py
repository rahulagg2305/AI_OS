"""The Voice pack's own real request/response contract
(`P06-S06-M33-T01`) — ``VoiceIntent`` is this ticket's own literal
Input ("A voice intent"), ``VoiceActionResult`` its literal Output
("A platform action")."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

VoiceIntentType = Literal[
    "check_health", "list_workflows", "get_workflow_status", "decide_approval"
]


class VoiceIntent(BaseModel):
    """An already-recognized, structured intent — never raw audio or
    free text (real speech-to-intent recognition is separate, unbuilt
    work; see this module's own package docstring). Fields beyond
    ``intent_type`` are optional here and validated per-type by
    :class:`~ai_os_kernel.voice_jarvis.intent_router.PlatformIntentRouter`,
    the identical "declared optional, required together" shape
    :mod:`ai_os_kernel.llm_gateway.call_recorder` already establishes
    for ``agent_id``/``prompt_id``/``prompt_version``."""

    model_config = ConfigDict(frozen=True)

    intent_type: VoiceIntentType
    workflow_id: str | None = None
    approval_id: str | None = None
    decision: str | None = None


class VoiceActionResult(BaseModel):
    """The real platform action taken, plus a real, natural-language
    response derived from the real underlying result — never a
    fabricated summary."""

    model_config = ConfigDict(frozen=True)

    intent_type: str
    platform_action: str
    response_text: str
    raw_response: dict[str, Any]
