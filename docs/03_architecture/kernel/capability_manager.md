# Capability Manager Design – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Capability Manager Design  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## 1. Purpose

This document defines the design of the **Capability Manager**, a core component of the AI_OS Platform Kernel.

The Capability Manager is responsible for the lifecycle of Capability Packs after they have been discovered and validated by the Manifest Loader. It controls installation, activation, deactivation, upgrades, health monitoring, and removal of packs.

This document is subordinate to:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Kernel Architecture  
5. Capability Pack Contract  
6. Manifest Schema  
7. Plugin / Manifest Loader Design  

---

## 2. Design Goals

The Capability Manager must:

- Manage the full lifecycle of Capability Packs
- Enforce that only valid, compatible packs are activated
- Support safe activation and deactivation
- Provide health and status information
- Coordinate with the Configuration Manager for enable/disable decisions
- Remain domain-agnostic
- Be fully observable and auditable

---

## 3. Core Responsibilities

- Track all known Capability Packs (loaded via Manifest Loader)
- Activate and deactivate packs according to configuration
- Manage pack versions and upgrades
- Monitor health of activated packs
- Provide status information to the rest of the platform and to the Dashboard
- Ensure clean removal of packs
- Prevent activation of packs that violate contracts or compatibility rules

---

## 4. Lifecycle States

**This is the canonical Capability Pack lifecycle.** It is the single authority; the Capability Pack Contract and the Manifest Schema reference it rather than defining their own (v1.0 of those three documents contained three divergent lists).

```text
discovered → validated → installed → configured → activated
                                                     │
                                         ┌───────────┴───────────┐
                                         ▼                       ▼
                                   deactivated                failed
                                         │
                                         ▼
                                   uninstalled
```

| State | Meaning |
|---|---|
| `discovered` | Found via entry point or filesystem scan; not yet parsed |
| `validated` | Manifest passed schema and semantic validation |
| `installed` | Components registered; not yet available to workflows |
| `configured` | Configuration resolved and validated against `configSchema` |
| `activated` | `activate()` succeeded; components available to the Workflow Engine |
| `deactivated` | Cleanly withdrawn; registrations removed; reactivatable |
| `failed` | Validation, activation, or health check failed; not available |
| `uninstalled` | Removed from the platform |

Every transition is recorded in `catalog.pack_state_transitions` with actor, reason, and timestamp. Activation of a pack that affects platform behaviour requires human approval ([ADR-0007](../../18_decision_log/adr/ADR-0007-human-governance-for-critical-decisions.md)).

---

## 5. High-Level Structure

```text
Capability Manager
│
├── Pack Registry
├── Lifecycle Controller
├── Activation Manager
├── Health Monitor
├── Upgrade Manager
├── Status Reporter
└── Audit Logger
```

---

## 6. Key Design Rules

- Only packs that have successfully passed Manifest Loader validation may be activated.
- Activation must respect configuration (enabled/disabled packs, feature flags).
- Deactivation and removal must be clean (no dangling registrations).
- The Capability Manager does not execute domain logic; it only manages the lifecycle of packs and their registrations.

---

## 7. Relationship with Other Components

- **Manifest Loader** hands over validated packs.
- **Configuration Manager** controls which packs are enabled.
- **Workflow Engine**, **Agent Invoker**, and **Tool Invoker** only see components from activated packs.
- **Security Manager** may enforce additional permission checks at activation time.
- **Dashboard** consumes status and health information.
- **Evaluation Engine** may need to know which packs and versions were active during an experiment.

---

## 8. Observability & Audit

Every lifecycle transition must be recorded, including:

- Pack ID and version
- Previous and new state
- Reason for the transition
- Timestamp
- Operator or system action that triggered it

---

## 9. Current Status

This document defines the design baseline for the Capability Manager.

Detailed state machine implementation, health check protocols, and upgrade strategies will be refined during development.

---

## 10. Final Authority

Order of precedence:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Capability Pack Contract  
5. Kernel Architecture  
6. Plugin / Manifest Loader Design  
7. Capability Manager Design  
8. Source Code
