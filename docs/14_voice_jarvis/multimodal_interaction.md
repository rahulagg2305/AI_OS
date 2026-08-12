# Multi-modal Interaction Design – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Multi-modal Interaction Design  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## Implementation Status (2026-07-28)

**Built: nothing. This document is a design specification only.** No Voice/Jarvis code exists: `capability_packs/voice_jarvis/` has **no tracked content**, and the platform-level Speech Gateway it depends on (per [ADR-0019](../18_decision_log/adr/ADR-0019-speech-gateway.md)) is likewise 0% built. There is no wake-word engine, no STT/TTS adapter, no intent engine, and no voice session manager anywhere in the codebase. Stage F deliverable. Of the channels this document coordinates, **only the HTTP API partially exists** (9 routes); the Dashboard, Voice, and CLI channels are all 0% built, so no cross-channel hand-off is possible today.

Authoritative, always-current status: the per-module completion table in `feature_inventory.md`; build history in `history/INDEX.md` (all under `docs/19_roadmap/`).

## 1. Purpose

This document defines how AI_OS supports **multi-modal interaction** — the coordinated use of multiple interfaces (Dashboard, Voice, API, CLI, etc.) so that users can move fluidly between them while working with the same workflows, approvals, and experiments.

This document is subordinate to:

1. System Architecture  
2. Dashboard Architecture  
3. Voice (Jarvis) System Architecture  
4. Human Approval Points Framework  
5. Notification Service  

---

## 2. Design Goals

Multi-modal interaction must:

- Allow users to start work in one channel and continue in another
- Keep a consistent view of workflow state across channels
- Support the same core capabilities (status, approvals, experiments) across interfaces
- Avoid conflicting actions from different channels
- Preserve security and auditability regardless of channel

---

## 3. Supported Interaction Channels

- **Dashboard** — primary visual interface
- **Voice (Jarvis)** — hands-free interface
- **API** — programmatic interface
- **CLI** (optional but recommended) — developer-oriented interface
- Future channels (e.g., chat integrations, IDE extensions)

---

## 4. Core Principles

- **Single source of truth** — Workflow Engine and related Kernel services own the real state. All channels are clients.
- **Channel-agnostic core actions** — Starting a workflow, approving a decision, querying status, etc. should be available consistently.
- **Seamless hand-off** — A user can receive a voice notification about a pending approval and complete the approval on the Dashboard (or vice versa).
- **No channel privilege escalation** — Using a different channel must not bypass authorization.
- **Consistent identity** — The same principal (user) should be recognized across channels when authenticated.

---

## 5. Key Cross-Channel Scenarios

### 5.1 Approval Flow
- User is notified via Voice that an approval is pending
- User opens the Dashboard to review context and approve
- Or user issues a carefully confirmed voice approval command

### 5.2 Status Follow-up
- User starts a workflow via Dashboard or API
- User later asks Voice for status
- User drills into logs/traces on the Dashboard if needed

### 5.3 Experiment Review
- Experiment completes and Notification Service alerts the user
- User reviews comparison results on the Dashboard
- User may ask Voice for a short spoken summary

### 5.4 Error / Failure Handling
- Failure notification arrives via preferred channel
- User investigates on Dashboard (logs, traces, quality gates)
- User may trigger retry or remediation actions from the appropriate channel

---

## 6. Design Rules

- Channels must not maintain divergent state.
- Any action that changes system state must go through the same Kernel services regardless of channel.
- Notifications should be coordinated so users are not spammed across every channel for the same event (respect preferences).
- High-impact actions should have consistent confirmation patterns (especially on Voice).

---

## 7. Relationship with Other Components

- **Workflow Engine** is the central source of workflow state.
- **Human Approval Points** are accessible from multiple channels.
- **Notification Service** coordinates multi-channel delivery.
- **Dashboard** and **Voice** are the primary human-facing channels.
- **Security Manager** ensures consistent authorization.
- **Configuration Manager** stores per-user and per-channel preferences.

---

## 8. Current Status

This document defines the baseline multi-modal interaction design.

Detailed UX patterns for hand-offs and concrete API contracts for cross-channel consistency will be refined during implementation.

---

## 9. Final Authority

Order of precedence:

1. System Architecture  
2. Dashboard Architecture  
3. Voice (Jarvis) System Architecture  
4. Multi-modal Interaction Design  
5. Source Code
