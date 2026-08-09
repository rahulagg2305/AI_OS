"""Unit tests for the Speech Gateway's one real, deterministic
reference implementation (`P06-S06-M25-T01`) — proves the
request/response contract genuinely round-trips, the identical
"deterministic, inspectable" proof `EchoLLMGateway`'s own tests
already establish for the LLM Gateway.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

from ai_os_kernel.speech_gateway.echo_adapter import (
    WAKE_WORD_TEST_MARKER,
    EchoSpeechToTextProvider,
    EchoTextToSpeechProvider,
    EchoWakeWordProvider,
)
from ai_os_kernel.speech_gateway.models import (
    SynthesisRequest,
    TranscriptionRequest,
    WakeWordRequest,
)


def test_transcribe_describes_the_real_input_and_reports_honest_zero_cost() -> None:
    audio_bytes = b"\x00\x01" * 8_000  # 16-bit PCM, 8000 real samples
    request = TranscriptionRequest(
        stt_alias="stt-default", audio_bytes=audio_bytes, sample_rate_hz=16_000, encoding="pcm16"
    )

    result = asyncio.run(EchoSpeechToTextProvider().transcribe(request))

    assert str(len(audio_bytes)) in result.text
    assert result.provider == "echo"
    assert result.cost_usd == Decimal("0")
    # 8000 real samples at 16kHz -> 0.5 real seconds, not a fabricated number.
    assert result.audio_duration_seconds == 0.5


def test_transcribe_never_divides_by_a_real_zero_sample_rate() -> None:
    request = TranscriptionRequest(
        stt_alias="stt-default", audio_bytes=b"\x00\x01", sample_rate_hz=0, encoding="pcm16"
    )

    result = asyncio.run(EchoSpeechToTextProvider().transcribe(request))

    assert result.audio_duration_seconds == 0.0


def test_synthesize_produces_genuinely_reversible_audio_bytes() -> None:
    request = SynthesisRequest(tts_alias="tts-default", text="hello world")

    result = asyncio.run(EchoTextToSpeechProvider().synthesize(request))

    assert result.audio_bytes.decode("utf-8") == "hello world"
    assert result.provider == "echo"
    assert result.cost_usd == Decimal("0")
    assert result.sample_rate_hz > 0


def test_detect_wake_word_finds_the_real_documented_marker() -> None:
    audio_bytes = b"\x00\x00" + WAKE_WORD_TEST_MARKER + b"\x00\x00"
    request = WakeWordRequest(
        wake_word_alias="wake-default", audio_bytes=audio_bytes, sample_rate_hz=16_000
    )

    result = asyncio.run(EchoWakeWordProvider().detect(request))

    assert result.detected is True
    assert result.keyword == WAKE_WORD_TEST_MARKER.decode("ascii")
    assert result.provider == "echo"


def test_detect_wake_word_is_honestly_absent_without_the_marker() -> None:
    request = WakeWordRequest(
        wake_word_alias="wake-default", audio_bytes=b"\x00\x00\x00\x00", sample_rate_hz=16_000
    )

    result = asyncio.run(EchoWakeWordProvider().detect(request))

    assert result.detected is False
    assert result.keyword is None
