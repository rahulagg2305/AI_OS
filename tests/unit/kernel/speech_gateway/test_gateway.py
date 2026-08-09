"""Unit tests for `DispatchingSpeechGateway` (`P06-S06-M25-T01`) —
real alias-based routing to a configured provider, and a real, clear
refusal for an unconfigured alias (deny, do not guess — the identical
behaviour `StaticRouter` already establishes for an unknown
``model_alias``).
"""

from __future__ import annotations

import asyncio

import pytest

from ai_os_kernel.speech_gateway.echo_adapter import (
    EchoSpeechToTextProvider,
    EchoTextToSpeechProvider,
    EchoWakeWordProvider,
)
from ai_os_kernel.speech_gateway.errors import SpeechProviderError
from ai_os_kernel.speech_gateway.gateway import DispatchingSpeechGateway
from ai_os_kernel.speech_gateway.models import (
    SynthesisRequest,
    TranscriptionRequest,
    WakeWordRequest,
)


def _gateway() -> DispatchingSpeechGateway:
    return DispatchingSpeechGateway(
        stt_providers={"stt-default": EchoSpeechToTextProvider()},
        tts_providers={"tts-default": EchoTextToSpeechProvider()},
        wake_word_providers={"wake-default": EchoWakeWordProvider()},
    )


def test_transcribe_dispatches_to_the_real_configured_alias() -> None:
    request = TranscriptionRequest(
        stt_alias="stt-default", audio_bytes=b"\x00\x01", sample_rate_hz=16_000, encoding="pcm16"
    )

    result = asyncio.run(_gateway().transcribe(request))

    assert result.provider == "echo"


def test_transcribe_refuses_a_genuinely_unconfigured_alias() -> None:
    request = TranscriptionRequest(
        stt_alias="stt-nope", audio_bytes=b"\x00\x01", sample_rate_hz=16_000, encoding="pcm16"
    )

    with pytest.raises(SpeechProviderError, match="stt-nope"):
        asyncio.run(_gateway().transcribe(request))


def test_synthesize_dispatches_to_the_real_configured_alias() -> None:
    result = asyncio.run(
        _gateway().synthesize(SynthesisRequest(tts_alias="tts-default", text="hi"))
    )

    assert result.provider == "echo"


def test_synthesize_refuses_a_genuinely_unconfigured_alias() -> None:
    with pytest.raises(SpeechProviderError, match="tts-nope"):
        asyncio.run(_gateway().synthesize(SynthesisRequest(tts_alias="tts-nope", text="hi")))


def test_detect_wake_word_dispatches_to_the_real_configured_alias() -> None:
    request = WakeWordRequest(
        wake_word_alias="wake-default", audio_bytes=b"\x00\x00", sample_rate_hz=16_000
    )

    result = asyncio.run(_gateway().detect_wake_word(request))

    assert result.provider == "echo"


def test_detect_wake_word_refuses_a_genuinely_unconfigured_alias() -> None:
    request = WakeWordRequest(
        wake_word_alias="wake-nope", audio_bytes=b"\x00\x00", sample_rate_hz=16_000
    )

    with pytest.raises(SpeechProviderError, match="wake-nope"):
        asyncio.run(_gateway().detect_wake_word(request))


def test_stt_and_tts_alias_namespaces_are_genuinely_distinct() -> None:
    # An alias name shared across both real namespaces must never
    # accidentally resolve the wrong provider kind.
    gateway = DispatchingSpeechGateway(
        stt_providers={"default": EchoSpeechToTextProvider()},
        tts_providers={"default": EchoTextToSpeechProvider()},
        wake_word_providers={},
    )

    transcription = asyncio.run(
        gateway.transcribe(
            TranscriptionRequest(
                stt_alias="default",
                audio_bytes=b"\x00\x01",
                sample_rate_hz=16_000,
                encoding="pcm16",
            )
        )
    )
    synthesis = asyncio.run(gateway.synthesize(SynthesisRequest(tts_alias="default", text="hi")))

    assert transcription.provider == "echo"
    assert synthesis.provider == "echo"
