# Notification Service – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Notification Service  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## Implementation Status (updated 2026-08-08, `P06-S05-M22-T02`)

**Built: a real, minimal first increment — one real channel, no framework — plus durable delivery-status recording.** `ai_os_kernel.notification.service.NotificationService` genuinely subscribes to the real `InProcessEventBus` and delivers a real, typed `Notification` (§8's own fields: type, channel, status, workflow_id, trace_id, timestamp) for this ticket's own three literal categories ("approval, failure and completion notices") via one real channel, `ai_os_kernel.notification.webhook.WebhookChannel` (a real HTTP POST to a configurable URL — §4's "Webhook / external system callbacks" entry). Proven end to end against a real local HTTP server: a real published `Event` genuinely reaches it as a real POST, an unrelated event type is genuinely not notified, and closing the service genuinely unsubscribes.

**§8's "Delivery status (sent, delivered, failed, read)" requirement is now partly real** (`P06-S05-M22-T02`): every delivery attempt's real, final outcome (`sent`/`failed` — `delivered`/`read` have no real producer to report them yet) is persisted to a new `notification.notification_deliveries` table (migration `0034`) via `SqlNotificationDeliveryRecorder`, the identical insert-only shape `SqlGateResultRecorder` already establishes elsewhere in this codebase. `NotificationService` now requires a `NotificationDeliveryRecorder` collaborator (no silent no-op default, the same convention `QualityGateStepExecutor`'s required `gate_sources` establishes) and records the real outcome only after the delivery attempt completes — not before. Proven against real Postgres (3 integration tests: a real row with the given values, genuinely-null `workflow_id`/`trace_id`, and repeated calls each inserting their own distinct row) plus the existing fake-recorder unit suite (ADR-0004), which proves the service's own classification/delivery logic separately from persistence correctness.

**Two real, deliberate departures from this document's own full design, both design forks resolved via `AskUserQuestion` before writing code:**
1. **Built inside the Kernel** (`ai_os_kernel.notification`), not as the separate `platform_services/notification` package this document's own `module_path` names. `platform_services/` remains undocumented as a real `uv` workspace member (still no tracked content), and the real `EventBus` this service needs has no `ai-os-sdk` Protocol yet — only the Kernel-local one (see `event_bus.md`'s own Implementation Status). A brand-new package importing `ai_os_kernel.event_bus` directly would start a new instance of the "pack imports Kernel internals" pattern CLAUDE.md says not to copy in new work. Extracting a real, separate package is later work, once the SDK's own `EventBus` Protocol exists or a second real consumer justifies the split.
2. **One channel, no framework**: no Notification API, Preference Manager, Channel Router, Delivery Manager, retry policy, or Dashboard/Voice/Email adapters — this ticket's own literal Goal/Input/Output ("Deliver approval, failure and completion notices" / "A platform event" / "A delivered notification") does not ask for the full §5 structure.

**Still genuinely 0% wired to a real producer**: the identical, already-disclosed gap `routes/stream.py`'s own module docstring names for the WebSocket endpoint — no real Kernel component (the Human Approval Manager, the Quality Gate Engine) calls `InProcessEventBus.publish()` in production yet, confirmed again while investigating this ticket. This service is a real, proven consumer with nothing real upstream of it yet.

Authoritative, always-current status: the per-module completion table in `feature_inventory.md` and `implementation_status.md`; build history in `history/INDEX.md` (all under `docs/19_roadmap/`).

## 1. Purpose

This document defines the design of the **Notification Service**, a shared Platform Service in AI_OS.

The Notification Service is responsible for delivering timely, reliable notifications about workflow events, human approval requests, errors, quality gate failures, experiment results, and other significant platform events to users and external systems.

This document is subordinate to:

1. Project Constitution  
2. System Architecture  
3. Kernel Architecture  
4. Human Approval Points Framework  
5. Workflow Architecture  

---

## 2. Design Goals

The Notification Service must:

- Support multiple delivery channels
- Deliver notifications reliably
- Respect user preferences and configuration
- Be loosely coupled from event producers
- Support both real-time and asynchronous delivery
- Be observable and auditable
- Avoid becoming a source of spam or noise

---

## 3. Core Responsibilities

- Accept notification requests from Kernel components and Capability Packs
- Route notifications to the appropriate channels
- Manage delivery attempts and retries
- Support user / project notification preferences
- Record delivery status for audit and debugging
- Integrate with Human Approval Points (requesting decisions)
- Integrate with the Dashboard and Voice (Jarvis) channels

---

## 4. Supported Channels (Initial)

- Dashboard (in-app notifications)
- Voice / Jarvis (spoken notifications)
- Email (optional)
- Webhook / external system callbacks
- Future channels (Slack, Teams, mobile push, etc.)

---

## 5. High-Level Structure

```text
Notification Service
│
├── Notification API
├── Preference Manager
├── Channel Router
├── Channel Adapters
│     ├── Dashboard Adapter
│     ├── Voice Adapter
│     ├── Email Adapter
│     └── Webhook Adapter
├── Delivery Manager
└── Observability & Audit
```

---

## 6. Key Design Rules

- Producers should emit events or call the Notification Service; they should not implement their own delivery logic.
- Notification content should be structured and channel-appropriate (short for voice, richer for dashboard).
- Sensitive information must be handled according to security policies.
- Users must be able to configure what they receive and through which channels.
- Delivery failures should be visible and retryable where appropriate.

---

## 7. Relationship with Other Components

- **Workflow Engine** and **Human Approval Points** are major producers of notifications.
- **Quality Gate Engine** may notify on blocking failures.
- **Evaluation / Benchmarking** may notify on experiment completion.
- **Dashboard** is both a channel and a consumer of notification state.
- **Voice (Jarvis) Pack** is an important delivery channel.
- **Event Bus** may be used to decouple producers from the Notification Service.
- **Security Manager** enforces who may receive what.

---

## 8. Observability Requirements

Notification operations should record:

- Notification type and recipient
- Channel used
- Delivery status (sent, delivered, failed, read)
- Timestamp and correlation IDs (Workflow ID, Trace ID, etc.)

---

## 9. Current Status

This document defines the design baseline for the Notification Service.

Concrete channel implementations, preference models, and retry policies will be refined during implementation.

---

## 10. Final Authority

Order of precedence:

1. Project Constitution  
2. System Architecture  
3. Kernel Architecture  
4. Notification Service  
5. Source Code
