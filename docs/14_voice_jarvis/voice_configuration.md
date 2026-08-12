# Voice Configuration – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Voice Configuration (Wake word, Personality, STT/TTS)  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## Implementation Status (2026-07-28)

**Built: nothing. This document is a design specification only.** No Voice/Jarvis code exists: `capability_packs/voice_jarvis/` has **no tracked content**, and the platform-level Speech Gateway it depends on (per [ADR-0019](../18_decision_log/adr/ADR-0019-speech-gateway.md)) is likewise 0% built. There is no wake-word engine, no STT/TTS adapter, no intent engine, and no voice session manager anywhere in the codebase. Stage F deliverable. No configuration key documented here is read by any code, and no schema for them exists in `config/`.

Authoritative, always-current status: the per-module completion table in `feature_inventory.md`; build history in `history/INDEX.md` (all under `docs/19_roadmap/`).

## 1. Purpose

This document defines the configuration model for the Voice (Jarvis) system in AI_OS.

All major aspects of voice behaviour must be configurable so that users can adapt the system to their preferences and environment without code changes.

This document is subordinate to:

1. Voice (Jarvis) Pack – High-level Design  
2. Voice (Jarvis) System Architecture  
3. Configuration Manager Design  

---

## 2. Design Goals

Voice configuration must:

- Be externalized (no hard-coded wake words, voices, or providers)
- Support different users and environments
- Allow safe defaults
- Integrate with the platform Configuration Manager
- Be changeable without restarting the entire platform when practical

---

## 3. Configuration Areas

### 3.1 Wake Word
- Enabled / disabled
- Wake word phrase (default: “Jarvis”)
- Sensitivity / confidence threshold
- Language / locale related to wake word detection

### 3.2 Speech-to-Text (STT)
- Provider selection (e.g., cloud provider, local model)
- Language
- Model / quality profile
- Related credentials (via Secrets Management)
- Timeout and error behaviour

### 3.3 Text-to-Speech (TTS)
- Provider selection
- Voice identity (male/female/neutral, specific voice IDs)
- Language and accent
- Speaking rate
- Related credentials (via Secrets Management)

### 3.4 Personality & Style
- Personality profile (e.g., formal, concise, friendly, professional)
- Verbosity level (minimal, normal, detailed)
- Greeting and acknowledgment style
- Error and clarification phrasing preferences

### 3.5 Session & Behaviour
- Session timeout
- Maximum turn length
- Whether follow-up questions are allowed without re-saying the wake word
- Confirmation requirements for high-impact actions

### 3.6 Notification Preferences (Voice Channel)
- Which events are spoken (workflow started, completed, failed, approval required, etc.)
- Quiet hours / do-not-disturb
- Priority filtering

### 3.7 Security & Privacy
- Whether audio is retained (and for how long)
- Whether spoken content may include potentially sensitive information
- Authentication requirements for voice commands

---

## 4. Configuration Storage & Precedence

Voice configuration follows the platform Configuration Manager rules:

- Defaults shipped with the Voice Pack
- Environment-specific overrides
- User or project-level overrides
- Runtime overrides when needed

Secrets (API keys for STT/TTS providers) are never stored in plain configuration; they are referenced and resolved through Secrets Management.

---

## 5. Key Design Rules

- Changing the wake word or voice must not require code changes.
- High-impact voice commands should still respect Human Approval Points and authorization.
- Defaults must be safe and conservative.
- Configuration changes should be auditable when they affect behaviour significantly.

---

## 6. Relationship with Other Components

- **Configuration Manager** is the primary store and resolution mechanism.
- **Secrets Management** supplies provider credentials.
- **Voice System Architecture** components read their settings from configuration.
- **Notification Service** respects voice notification preferences.
- **Security Manager** influences what actions are allowed via voice.

---

## 7. Current Status

This document defines the configuration model for Voice (Jarvis).

Concrete configuration schema, file formats, and UI for editing these settings will be refined during implementation.

---

## 8. Final Authority

Order of precedence:

1. Voice (Jarvis) System Architecture  
2. Configuration Manager Design  
3. Voice Configuration  
4. Source Code
