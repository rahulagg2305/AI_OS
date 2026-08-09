# ADR-0019: Speech Gateway — Platform-Level STT/TTS Abstraction

**Status:** Accepted
**Date:** 2026-07-25
**Decision Makers:** Chief Architect
**Related Documents:** `docs/14_voice_jarvis/voice_architecture.md`, `docs/14_voice_jarvis/voice_configuration.md`

---

## Context

The Voice (Jarvis) design placed STT and TTS provider adapters inside the Voice Capability Pack. That is the exact pattern the LLM Gateway exists to prevent: a pack holding provider integrations and credentials. Speech providers are external AI providers with credentials, cost, latency, quality trade-offs, and privacy implications — the same properties that justified centralising LLM access in [ADR-0002](ADR-0002-llm-gateway-single-entry-point.md).

## Decision

**Introduce a platform-level Speech Gateway, structurally parallel to the LLM Gateway.**

- Location: `platform_services/speech/`, exposed through the SDK as `SpeechGateway`.
- Responsibilities: provider abstraction for **speech-to-text**, **text-to-speech**, and **wake-word detection**; routing by alias; credential handling via Secrets Management; retry and fallback; cost, latency, and audio-duration accounting; telemetry.
- The Voice Capability Pack becomes a pure **interface pack**: wake-word orchestration, session management, intent recognition, response shaping, and platform integration. It holds no provider adapters and no provider credentials.
- Selection is by alias (`stt-default`, `stt-local`, `tts-default`), never by provider or voice ID in pack code.
- Reference adapters: local Whisper (`faster-whisper`) and a cloud STT adapter; local Piper and a cloud TTS adapter; `openWakeWord` for wake word.
- **Privacy is a first-class routing input.** Audio retention, and whether audio may leave the local machine at all, are configuration. A `local_only` policy restricts routing to local adapters, and it is the recommended default for wake-word audio.
- Intent recognition, where it uses a model, goes through the **LLM Gateway** — not the Speech Gateway — so intent classification is covered by normal model accounting and agnosticism.

## Alternatives Considered

- **Keep adapters in the Voice pack (status quo)** — Rejected: contradicts the Capability Pack Contract's prohibition on packs holding provider integrations and secrets, splits cost accounting across two mechanisms, and means a second pack needing TTS would duplicate the work.
- **Extend the LLM Gateway to cover speech** — Superficially tidy, since both are "AI providers". Rejected because the request/response contracts share almost nothing: streaming audio frames, sample rates, voice profiles, and audio-duration billing have no analogue in a token-based text contract. Merging them would produce a union type with two disjoint halves.
- **A separate Capability Pack providing speech to other packs** — Rejected: pack-to-pack dependency is prohibited by [ADR-0001](ADR-0001-modular-capability-pack-architecture.md).
- **Cloud speech only** — Rejected: sends all captured audio, including ambient audio around a wake word, to a third party, which is unacceptable as a default.

## Consequences

### Positive
- One consistent rule across all external AI providers: adapters live in the platform, not in packs.
- Speech cost and latency are measured on the same footing as model cost.
- Local-only operation is achievable through configuration, which matters for a continuously-listening interface.
- A future pack needing speech reuses the Gateway.

### Negative
- One more platform service to build and maintain; scoped to Stage F, so it does not burden the minimum viable kernel.
- Adds a small indirection for the Voice pack.

### Neutral
- Wake-word detection is included because it is the most privacy-sensitive path and must be routable to a local adapter.

## Compliance

Complies with the Capability Pack Contract (no provider integrations or secrets in packs) and the Constitution (Interface-Driven Design, Least Privilege).

## References

- `docs/06_capability_packs/voice_jarvis/overview.md`

---

## Implementation Status (updated 2026-08-09, `P06-S06-M25-T01` — not part of the Accepted decision)

**Status in code: a real first increment.** `ai_os_kernel.speech_gateway` (built inside the Kernel, not a separate `platform_services` package — no real `uv` workspace member exists for `platform_services` yet, the identical, already-established Notification Service/Git Integration packaging precedent) has real `SpeechToTextProvider`/`TextToSpeechProvider`/`WakeWordProvider` Protocols, a real `SpeechGateway` composed entry point, real alias-based routing (`DispatchingSpeechGateway` — genuinely distinct STT/TTS/wake-word alias namespaces), and one real, deterministic reference implementation (`echo_adapter.py`) proving the request/response contract end to end — mirroring `EchoLLMGateway`'s own identical role before any real LLM provider adapter existed.

**A real, disclosed gap found by direct investigation before writing any code, resolved via `AskUserQuestion`:** every one of this ADR's own named reference adapters (local Whisper/`faster-whisper`, a cloud STT adapter, local Piper, a cloud TTS adapter, `openWakeWord`) needs infrastructure this repository has none of yet — no audio/ML runtime dependency installed, and no speech-provider credential configured anywhere (unlike the Anthropic key already wired for the LLM Gateway). Wiring any real provider is real, separate, credential/dependency-gated follow-up work. Also not built: retry/fallback/circuit-breaker routing (real, later sophistication, mirroring how `DispatchingLLMGateway` itself only grew this across several separate tickets), the `local_only` privacy policy, and the Voice Capability Pack itself (still 0% built) — nothing here is wired into `bootstrap.py`, since no real caller exists yet to justify a real composition.

Live status: [`feature_inventory.md`](../../19_roadmap/feature_inventory.md) · Build history: [`history/INDEX.md`](../../19_roadmap/history/INDEX.md)
