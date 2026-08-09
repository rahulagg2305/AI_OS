"""The one real, deterministic reference implementation for this
step — mirrors :class:`~ai_os_kernel.llm_gateway.gateway.EchoLLMGateway`'s
own exact role: calls no provider, performs no real speech recognition
or synthesis, and never will need to for what it does. It exists to
prove the request/response contract works end to end, deterministic
and inspectable — never a stand-in for a real provider.

``PROVIDER_NAME = "echo"`` throughout, the identical "the response
itself honestly names what produced it" convention every real
provider adapter in this codebase already follows (``response.provider``
on a real ``AnthropicAdapter``/``LocalAdapter`` completion).
"""

from __future__ import annotations

import time
from decimal import Decimal

from ai_os_kernel.speech_gateway.models import (
    SynthesisRequest,
    SynthesisResult,
    TranscriptionRequest,
    TranscriptionResult,
    WakeWordRequest,
    WakeWordResult,
)

PROVIDER_NAME = "echo"
_MODEL_ID = "echo-v1"
_ZERO_COST = Decimal("0")

# A fake audio stream's own real, honest accounting: 16-bit PCM, so
# duration is genuinely derivable from byte count and sample rate —
# not a fabricated number, just not a *real* recording's duration
# (there is no real recording).
_BYTES_PER_SAMPLE = 2
_ECHO_SYNTHESIS_SAMPLE_RATE_HZ = 16_000

# The deterministic "wake word" this fake provider recognises — a
# real, inspectable, testable contract standing in for a real acoustic
# model, the identical role EchoLLMGateway's own literal-echo
# "completion" plays for text.
WAKE_WORD_TEST_MARKER = b"AIOS_WAKE"


class EchoSpeechToTextProvider:
    """ "Transcribes" by describing the real input it received —
    never inventing words no acoustic model actually produced."""

    async def transcribe(self, request: TranscriptionRequest) -> TranscriptionResult:
        started = time.monotonic()
        sample_count = len(request.audio_bytes) // _BYTES_PER_SAMPLE
        duration_seconds = sample_count / request.sample_rate_hz if request.sample_rate_hz else 0.0
        text = f"[echo transcription of {len(request.audio_bytes)} audio bytes]"
        latency_ms = int((time.monotonic() - started) * 1000)
        return TranscriptionResult(
            text=text,
            provider=PROVIDER_NAME,
            model_id=_MODEL_ID,
            audio_duration_seconds=duration_seconds,
            latency_ms=latency_ms,
            cost_usd=_ZERO_COST,
        )


class EchoTextToSpeechProvider:
    """ "Synthesizes" by encoding the real input text as its own real
    output bytes — genuinely reversible (a caller can decode it back),
    unlike a fabricated waveform that would only look like audio."""

    async def synthesize(self, request: SynthesisRequest) -> SynthesisResult:
        started = time.monotonic()
        audio_bytes = request.text.encode("utf-8")
        sample_count = len(audio_bytes) // _BYTES_PER_SAMPLE
        duration_seconds = sample_count / _ECHO_SYNTHESIS_SAMPLE_RATE_HZ
        latency_ms = int((time.monotonic() - started) * 1000)
        return SynthesisResult(
            audio_bytes=audio_bytes,
            sample_rate_hz=_ECHO_SYNTHESIS_SAMPLE_RATE_HZ,
            encoding="echo-utf8",
            provider=PROVIDER_NAME,
            model_id=_MODEL_ID,
            audio_duration_seconds=duration_seconds,
            latency_ms=latency_ms,
            cost_usd=_ZERO_COST,
        )


class EchoWakeWordProvider:
    """Detects the real, documented test marker
    (:data:`WAKE_WORD_TEST_MARKER`) anywhere in the given audio bytes
    — a real, deterministic, testable contract, never a guess at real
    acoustic wake-word detection."""

    async def detect(self, request: WakeWordRequest) -> WakeWordResult:
        started = time.monotonic()
        detected = WAKE_WORD_TEST_MARKER in request.audio_bytes
        latency_ms = int((time.monotonic() - started) * 1000)
        return WakeWordResult(
            detected=detected,
            keyword=WAKE_WORD_TEST_MARKER.decode("ascii") if detected else None,
            provider=PROVIDER_NAME,
            latency_ms=latency_ms,
        )
