# Voice (Jarvis) System Architecture – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Voice (Jarvis) System Architecture  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## Implementation Status (2026-08-09, `P06-S06-M33-T01`)

**Built: the §4.5 Platform Integration Layer, real — but inside the Kernel, not `capability_packs/voice_jarvis`.** A first attempt built it as a pure external HTTP-client Capability Pack, mirroring `tools/aios`'s own proven shape; `pack_contract_suite` check 7 (`platform_sdk.md` §9/§10) caught it for real — any direct HTTP client import in pack code is forbidden, full stop, including a call to the platform's own Kernel API. No SDK Protocol for "read workflow status"/"decide an approval" exists yet, so `ai_os_kernel.voice_jarvis.intent_router.PlatformIntentRouter` lives inside the Kernel instead (the identical precedent Notification Service and the Speech Gateway itself already establish), calling the real `HealthService`/`WorkflowInstanceRepository`/`ApprovalService` directly — no HTTP, no serialization round trip. 4 real intents (`check_health`, `list_workflows`, `get_workflow_status`, `decide_approval`), a real `workflow:read` permission gate, `ApprovalService`'s own real class-scoped authorization reused unchanged. No `capability_packs/voice_jarvis` distribution exists.

**Everything upstream of "an already-recognized intent" is still not built**: §4.1 Wake Word Engine, §4.2 Speech-to-Text (the platform Speech Gateway itself is real as of `P06-S06-M25-T01` but has no real provider — only a deterministic echo adapter, `ai_os_kernel.speech_gateway`'s own module docstring), §4.3 Intent Recognition (needs the LLM Gateway per §4.8 — not wired), §4.4 Voice Session Manager, and the §4.7 Text-to-Speech output half (`SpeechGateway.synthesize()` is reachable directly now that this also lives in the Kernel, but not wired this step). Stage F deliverable, partially real.

Authoritative, always-current status: the per-module completion table in `feature_inventory.md` and `implementation_status.md`; build history in `history/INDEX.md` (all under `docs/19_roadmap/`).

## 1. Purpose

This document defines the system architecture of the **Voice (Jarvis)** capability in AI_OS.

It builds on the Voice (Jarvis) Pack – High-level Design and provides a clearer architectural view of how voice interaction is implemented and integrated with the rest of the platform.

This document is subordinate to:

1. Project Constitution  
2. System Architecture  
3. Voice (Jarvis) Pack – High-level Design  
4. Human Approval Points Framework  
5. Notification Service  

---

## 2. Design Goals

The Voice system must:

- Provide reliable hands-free interaction
- Translate spoken commands into platform actions safely
- Deliver spoken feedback about status, progress, and results
- Support configurable wake word, voice, and personality
- Integrate cleanly with Workflow Engine, Dashboard, and Notification Service
- Respect security, privacy, and authorization

---

## 3. High-Level Architecture

```text
Microphone / Audio Input
        │
Wake Word Engine
        │
Speech-to-Text (STT) Adapter
        │
Text Normalizer
        │
Intent Recognition
        │
Voice Session Manager
        │
┌───────┴──────────────────────────────┐
│  Platform Integration Layer           │
│  - Command / Query Router             │
│  - Workflow Engine                    │
│  - Status / Query APIs                │
│  - Human Approval Bridge              │
│  - Notification Bridge                │
└───────┬──────────────────────────────┘
        │
Response Generator
        │
Text-to-Speech (TTS) Adapter
        │
Audio Output
```

---

## 4. Core Components

### 4.1 Wake Word Engine
- Listens for the configured wake word
- Activates the voice pipeline when detected
- Must be configurable (default “Jarvis” or user-defined)

### 4.2 Speech-to-Text — via the platform Speech Gateway
Speech-to-text is requested from the **platform-level Speech Gateway**, not from an adapter inside the Voice pack. The pack calls `SpeechGateway.transcribe()` with an alias (`stt-default`, `stt-local`); provider adapters and credentials live in the platform, exactly as they do for the LLM Gateway.

This corrects v1.0 of this document, which placed provider adapters inside the pack — the pattern the Capability Pack Contract prohibits, because it puts provider integrations and credentials in a pack and splits cost accounting ([ADR-0019](../18_decision_log/adr/ADR-0019-speech-gateway.md)).

A `local_only` routing policy restricts transcription to local adapters and is the recommended default for wake-word and ambient audio.

### 4.3 Intent Recognition
- Maps recognized text to platform intents (start workflow, ask status, approve, etc.)
- Works with a defined intent schema
- Can escalate to clarification when confidence is low

### 4.4 Voice Session Manager
- Maintains short-term conversational context
- Tracks the current voice session state
- Handles follow-up questions and multi-turn interactions

### 4.5 Platform Integration Layer
- Translates intents into actual platform API calls or events
- Never bypasses the Workflow Engine for orchestration
- Surfaces status, approvals, and notifications back to the voice channel

### 4.6 Response Generator
- Produces natural language responses suitable for speech
- Controls verbosity according to configuration
- Avoids speaking sensitive information unless allowed

### 4.7 Text-to-Speech — via the platform Speech Gateway
Synthesis is requested from the Speech Gateway by voice alias (`tts-default`). Voices, languages, and providers are configuration; the pack contains no TTS provider adapter and no provider credentials.

### 4.8 Intent recognition and the LLM Gateway
Where intent recognition uses a model, it goes through the **LLM Gateway**, not the Speech Gateway — so intent classification is covered by normal model accounting, budgets, and LLM-agnosticism.

---

## 5. Key Design Rules

- Voice is an **interface**, not an orchestrator. All real work still goes through the Workflow Engine and Kernel services.
- Agents are never invoked directly by the voice layer.
- Authorization still applies; voice commands must be authenticated and authorized.
- Sensitive data must not be spoken by default.
- All significant voice interactions must be observable (what was heard, what intent was recognized, what action was taken).

---

## 6. Relationship with Other Components

- **Workflow Engine** executes the actual work requested via voice.
- **Human Approval Points** can be notified and answered via voice (when configured).
- **Notification Service** can push important events to the voice channel.
- **Dashboard** remains the complementary visual interface.
- **Security Manager** enforces authentication and authorization for voice-initiated actions.
- **Configuration Manager** controls wake word, voice, language, verbosity, and provider settings.

---

## 7. Observability Requirements

Voice interactions should record:

- Wake word detection events
- STT results (text + confidence)
- Recognized intent
- Action taken
- TTS response summary
- Correlation with Workflow ID / Trace ID when an action is triggered

---

## 8. Current Status

This document defines the system architecture for Voice (Jarvis).

Detailed intent schemas, provider adapters, and configuration models will be refined in subsequent documents and during implementation.

---

## 9. Final Authority

Order of precedence:

1. Project Constitution  
2. System Architecture  
3. Voice (Jarvis) Pack – High-level Design  
4. Voice (Jarvis) System Architecture  
5. Source Code
