"""Speech Gateway request/response contracts (ADR-0019: "provider
abstraction for speech-to-text, text-to-speech, and wake-word
detection ... cost, latency, and audio-duration accounting").

Mirrors :mod:`ai_os_kernel.llm_gateway.models`'s own real shape
(``model_config = ConfigDict(frozen=True)``, a real ``UsageRecord``-
style cost/latency accounting block on every result) — the identical
contract discipline this codebase already established for the
structurally parallel LLM Gateway, not a fresh design.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class TranscriptionRequest(BaseModel):
    """One real speech-to-text request. ``stt_alias`` selects the
    provider by alias (ADR-0019: "Selection is by alias ... never by
    provider ... in pack code") — ``"stt-default"``/``"stt-local"``
    are the ADR's own named examples, not a closed enum: any alias a
    real deployment's own routing configuration declares is valid."""

    model_config = ConfigDict(frozen=True)

    stt_alias: str
    audio_bytes: bytes
    sample_rate_hz: int
    encoding: str


class TranscriptionResult(BaseModel):
    """One real transcription outcome — cost/latency/duration
    accounted on the same footing as an LLM completion (ADR-0019)."""

    model_config = ConfigDict(frozen=True)

    text: str
    provider: str
    model_id: str
    audio_duration_seconds: float
    latency_ms: int
    cost_usd: Decimal


class SynthesisRequest(BaseModel):
    """One real text-to-speech request. ``tts_alias`` selects the
    provider by alias, the identical convention
    :class:`TranscriptionRequest` already establishes."""

    model_config = ConfigDict(frozen=True)

    tts_alias: str
    text: str
    voice_id: str | None = None


class SynthesisResult(BaseModel):
    """One real synthesis outcome."""

    model_config = ConfigDict(frozen=True)

    audio_bytes: bytes
    sample_rate_hz: int
    encoding: str
    provider: str
    model_id: str
    audio_duration_seconds: float
    latency_ms: int
    cost_usd: Decimal


class WakeWordRequest(BaseModel):
    """One real wake-word detection request over a real audio frame.
    ``wake_word_alias`` selects the provider by alias — ADR-0019 names
    wake-word detection as "the most privacy-sensitive path," routable
    to a local-only adapter independently of STT/TTS aliasing."""

    model_config = ConfigDict(frozen=True)

    wake_word_alias: str
    audio_bytes: bytes
    sample_rate_hz: int


class WakeWordResult(BaseModel):
    """One real wake-word detection outcome. ``keyword`` is ``None``
    whenever ``detected`` is ``False`` — an honest absence, not an
    empty string standing in for "nothing.\""""

    model_config = ConfigDict(frozen=True)

    detected: bool
    keyword: str | None
    provider: str
    latency_ms: int
