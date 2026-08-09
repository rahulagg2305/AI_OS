"""Speech Gateway (ADR-0019, `P06-S06-M25-T01`) — this ticket's own
real, first increment.

**Real scope, matching this codebase's own "smallest real slice"
precedent** (the identical shape :mod:`ai_os_kernel.llm_gateway.gateway`
itself started from, before any real provider adapter existed):
real Protocols for all three provider kinds ADR-0019 names
(speech-to-text, text-to-speech, wake-word), real alias-based routing
(``DispatchingSpeechGateway``), and one real, deterministic reference
implementation (:mod:`ai_os_kernel.speech_gateway.echo_adapter`) proving
the request/response contract end to end — mirroring
:class:`~ai_os_kernel.llm_gateway.gateway.EchoLLMGateway`'s own
identical "always succeeds, does no real work" role, not a stand-in
for it.

**Real, disclosed, NOT built this step** (a genuine structural gap,
investigated and stopped on before writing any code — resolved via
`AskUserQuestion`): every one of ADR-0019's own named reference
adapters (local Whisper/``faster-whisper``, a cloud STT adapter, local
Piper, a cloud TTS adapter, ``openWakeWord``) needs infrastructure
this repository has none of yet — no audio/ML runtime dependency
installed, and no speech-provider credential configured anywhere
(confirmed by direct inspection: unlike the Anthropic key already
wired for the LLM Gateway, no ``AIOS_SECRET_*`` speech entry exists).
Wiring a real provider is real, separate, credential/dependency-gated
follow-up work, not attempted here.

**Also, deliberately, NOT built here: retry/fallback/circuit-breaker
routing, and intent recognition.** The former is real, later LLM
Gateway-style sophistication this module's own first increment does
not need yet (mirroring how ``DispatchingLLMGateway`` itself only
grew that behaviour across several later, separate tickets). The
latter is explicitly out of this module's own scope by ADR-0019 itself:
"Intent recognition ... goes through the LLM Gateway — not the Speech
Gateway." Nothing here is wired into ``bootstrap.py`` — the same
"build real, wire later" precedent
:mod:`ai_os_kernel.evaluation_engine.metrics_collector` and the
Benchmarking Pack's own ``experiment_definition.py`` already establish:
no real caller (a Voice Capability Pack, still 0% built) exists yet to
justify a real composition.
"""

from __future__ import annotations

from typing import Protocol

from ai_os_kernel.speech_gateway.errors import SpeechProviderError
from ai_os_kernel.speech_gateway.models import (
    SynthesisRequest,
    SynthesisResult,
    TranscriptionRequest,
    TranscriptionResult,
    WakeWordRequest,
    WakeWordResult,
)


class SpeechToTextProvider(Protocol):
    """The seam a real STT adapter (a future, credential/dependency-
    gated increment) implements — the identical
    interface-driven-configuration-over-code shape ADR-0004 already
    establishes for :class:`~ai_os_kernel.llm_gateway.gateway.LLMGateway`."""

    async def transcribe(self, request: TranscriptionRequest) -> TranscriptionResult: ...


class TextToSpeechProvider(Protocol):
    """The seam a real TTS adapter implements."""

    async def synthesize(self, request: SynthesisRequest) -> SynthesisResult: ...


class WakeWordProvider(Protocol):
    """The seam a real wake-word adapter implements."""

    async def detect(self, request: WakeWordRequest) -> WakeWordResult: ...


class SpeechGateway(Protocol):
    """The one real composed entry point a caller (a future Voice
    Capability Pack) depends on — never a specific provider directly,
    the identical "callers depend on the Gateway, not a provider"
    shape ADR-0002/ADR-0019 both establish."""

    async def transcribe(self, request: TranscriptionRequest) -> TranscriptionResult: ...

    async def synthesize(self, request: SynthesisRequest) -> SynthesisResult: ...

    async def detect_wake_word(self, request: WakeWordRequest) -> WakeWordResult: ...


class DispatchingSpeechGateway:
    """The real, minimal multi-provider :class:`SpeechGateway` —
    routes each request to the provider configured under its own real
    alias, exactly as ADR-0019 requires ("Selection is by alias").

    A deliberately flat, per-kind mapping (three separate
    ``dict[alias, provider]``s, not one unified registry) — STT, TTS,
    and wake-word aliases are three genuinely distinct namespaces
    (ADR-0019's own examples: ``stt-default``/``stt-local`` vs.
    ``tts-default``), so a caller configuring one kind's aliases can
    never accidentally shadow another's.

    No retry, no fallback, no circuit breaker — see this module's own
    docstring for why that is real, disclosed, later work, not an
    oversight.
    """

    def __init__(
        self,
        *,
        stt_providers: dict[str, SpeechToTextProvider],
        tts_providers: dict[str, TextToSpeechProvider],
        wake_word_providers: dict[str, WakeWordProvider],
    ) -> None:
        self._stt_providers = dict(stt_providers)
        self._tts_providers = dict(tts_providers)
        self._wake_word_providers = dict(wake_word_providers)

    async def transcribe(self, request: TranscriptionRequest) -> TranscriptionResult:
        provider = self._stt_providers.get(request.stt_alias)
        if provider is None:
            raise SpeechProviderError(
                f"no speech-to-text provider configured for alias {request.stt_alias!r}"
            )
        return await provider.transcribe(request)

    async def synthesize(self, request: SynthesisRequest) -> SynthesisResult:
        provider = self._tts_providers.get(request.tts_alias)
        if provider is None:
            raise SpeechProviderError(
                f"no text-to-speech provider configured for alias {request.tts_alias!r}"
            )
        return await provider.synthesize(request)

    async def detect_wake_word(self, request: WakeWordRequest) -> WakeWordResult:
        provider = self._wake_word_providers.get(request.wake_word_alias)
        if provider is None:
            raise SpeechProviderError(
                f"no wake-word provider configured for alias {request.wake_word_alias!r}"
            )
        return await provider.detect(request)
