# Capability Manager Design – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Capability Manager Design  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-30

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

## Implementation Status (2026-07-30)

**Built:** a real pack lifecycle *write path* in `kernel/src/ai_os_kernel/capability_manager/` (6 modules). `PackLifecycleRepository` (Protocol) with one implementation, `SqlPackLifecycleRepository` in `repository.py`, performs `register()` (recorded as `discovered → installed`, and — since the manifest → catalog installer step, extended `P03-S05-M14-T10` to also derive `catalog.workflow_definitions` rows (declared permissions included) — genuinely deriving `catalog.agents`/`catalog.prompts`/`catalog.tools`/`catalog.workflow_definitions` rows from the pack's own manifest when a real pack directory is supplied), `activate()`, `deactivate()`, and (as of this step) `mark_failed()`, writing `catalog.packs` and `catalog.pack_state_transitions` in **one transaction** with `SELECT … FOR UPDATE` on the pack row, so two concurrent transitions cannot both observe the same pre-state ([ADR-0011](../../18_decision_log/adr/ADR-0011-persistence-and-workflow-state.md)). **Real automated discovery now exists**: `ai_os_kernel.bootstrap._register_and_activate_discovered_packs`, called from `_lifespan` on every real Kernel startup, genuinely registers and activates every schema-valid pack the Manifest Loader finds — no manual `register()` call required, idempotent across restarts. **§9's own named "health check protocols" gap is resolved (2026-07-30) — the Pack Health Collector's smallest real slice**: `ai_os_kernel.capability_manager.health_poller.poll_pack_health()` genuinely resolves every one of a pack's own `catalog.agents` rows through a real `AgentRegistry`, writes a real `catalog.packs.health` snapshot via the new `record_health()` (status/details/consecutive_failures/checked_at, healthy or not), and — after `CONSECUTIVE_FAILURE_THRESHOLD` (3) consecutive unhealthy polls — genuinely calls the new `mark_failed()`, the one real `-> failed` transition this module gains. The three-value policy §9 named is decided (`POLL_INTERVAL_SECONDS`=30.0, `POLL_TIMEOUT_SECONDS`=5.0, `CONSECUTIVE_FAILURE_THRESHOLD`=3, all named constants in `health_poller.py`) — **and, as of this step, `POLL_INTERVAL_SECONDS` is genuinely enforced**: `health_poller.run_health_polling_loop()`, the first real, continuously-running background task this codebase has ever started, re-polls every discovered pack on that real interval for the life of the Kernel process, started in `_lifespan` immediately after the existing one-shot startup poll and cleanly cancelled (awaited, not merely abandoned) before the database engine it queries is disposed. `models.py` holds `PackRecord` (including its own `health: dict[str, Any] | None` field); `pack_contract.py` holds a deliberately reduced `CapabilityPack` Protocol, `PackContext`, `PackRegistration` and `HealthReport`; `errors.py` holds `PackAlreadyRegisteredError`, `PackNotFoundError`, `InvalidPackTransitionError`, `PackRegistrationError`. Four HTTP routes are live and permission-gated on `pack:manage` / `pack:read` — `POST /api/v1/packs`, `.../activate`, `.../deactivate`, `GET /api/v1/packs/{id}` (`kernel/src/ai_os_kernel/routes/packs.py`). The lifecycle-state vocabulary in §4 is enforced in code: all 8 states are a `CHECK` constraint in `kernel/src/ai_os_kernel/persistence/catalog_schema.py` and a `PackState` enum in `kernel/src/ai_os_kernel/workflow_engine/pack_state.py`.

**Not built:** the `configured` and `uninstalled` transitions (2 of the 8 §4 states remain vocabulary only, with no write path — `failed` is now real). No component in §5 exists as its own dedicated unit apart from the Pack Registry / Lifecycle Controller / Activation Manager slice, plus a real slice of the **Health Monitor** (health_lifecycle.md's own diagram names the identical role "Pack Health Collector" — two documents, one real component, `health_poller.py`) and, as of `P02-S05-M13-T07`, a real slice of the **Upgrade Manager** (`SqlPackLifecycleRepository.upgrade()` — real version-comparison and catalog-row migration; see §9's own updated row for exactly what it does and does not decide): a `FAILED` pack still has no re-activation path today — `_ACTIVATABLE_FROM_STATES` deliberately excludes it, an explicit, deferred recovery-path gap, distinct from an upgrade (which only ever starts from `activated`). **No Status Reporter** beyond the single `GET /api/v1/packs/{id}` read (which does now surface real `health`, since `PackRecord` already carries it), and **no Audit Logger** (`catalog.pack_state_transitions` records actor/reason/timestamp, but `governance.audit_log` has no writer anywhere in the codebase, so §8's records exist only in the catalog schema, not the audit chain). Nothing calls a pack's own `CapabilityPack.activate()`/`.health()` methods — the real health check built this step deliberately checks agent resolvability directly (through the same real `AgentRegistry` a caller would use), not that Protocol method, which remains real but unwired (`SoftwareEngineeringPack.health()` still just returns a hardcoded `"healthy"`, per its own docstring). §4's human-approval requirement for behaviour-affecting activation ([ADR-0007](../../18_decision_log/adr/ADR-0007-human-governance-for-critical-decisions.md)) is **not enforced** — the `workflow.approvals` table exists with no writer, so there is no approval path to gate on. §7's Security-Manager permission check at activation time does not happen.

Authoritative, always-current status: `../../19_roadmap/feature_inventory.md` (per-module completion table). Detailed build history: `../../19_roadmap/history/INDEX.md` (specifically `010_capability_manager_pack_lifecycle.md`).

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
- **Workflow Engine**, **Agent Invoker**, and **Tool Invoker** only see components from activated packs. *(Naming note: "Agent Invoker" and "Tool Invoker" are documented roles, not existing packages. The Agent Invoker role is filled by `AgentStepExecutor` in `kernel/src/ai_os_kernel/workflow_engine/step_executor.py`, and the activation gate is real — `SqlAgentRegistry`/`SqlToolRegistry` in `kernel/src/ai_os_kernel/workflow_engine/registry.py` resolve catalog rows only for activated packs. The `ToolInvoker` Protocol in `../platform/platform_sdk.md` §5.6 does not exist as code; there is no `tool_invoker` package anywhere. Its nearest real substitute is `ToolStepExecutor` + `SandboxedCommandTool`, also inside `workflow_engine/`.)*
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

This document defines the design baseline for the Capability Manager. The three items v1.0 of this section deferred are settled as follows — none is left open as "to be refined."

| Item | Status |
|---|---|
| **State machine implementation** | **Decided and mostly built.** §4 above is the canonical state machine; there is no second version to design. Persistence semantics are fixed by [ADR-0011](../../18_decision_log/adr/ADR-0011-persistence-and-workflow-state.md): snapshot (`catalog.packs`) plus append-only transition log (`catalog.pack_state_transitions`) in one transaction, with the pre-state guard taken under `SELECT … FOR UPDATE`. Real for `register`/`activate`/`deactivate`/`mark_failed` (2026-07-30) in `kernel/src/ai_os_kernel/capability_manager/repository.py`. **Named remaining gap:** no write path for the `configured` or `uninstalled` transitions; no re-activation path out of `failed` (a deliberate, deferred recovery-path gap, not an oversight). |
| **Health check protocols** | **Fully decided and built — nothing remains open (revised 2026-07-30).** The return shape is `HealthReport` (`pack_contract.py`); the caller and cadence policy — "who calls a pack's health check and how often" — is `ai_os_kernel.capability_manager.health_poller.poll_pack_health()`: `POLL_INTERVAL_SECONDS`=30.0, `POLL_TIMEOUT_SECONDS`=5.0, `CONSECUTIVE_FAILURE_THRESHOLD`=3 (Kubernetes' own common `failureThreshold` default), all named constants. Genuinely resolves every one of a pack's own `catalog.agents` rows through a real `AgentRegistry`, writes a real `catalog.packs.health` snapshot every poll (`record_health()`), and calls `mark_failed()` once the threshold is crossed. **`POLL_INTERVAL_SECONDS` is now genuinely enforced (2026-07-30), closing the one gap this row used to name**: `run_health_polling_loop()` — the first real, continuously-running background task this codebase has ever started — re-polls every discovered pack on that real interval for the life of the Kernel process, started in `_lifespan` and cleanly cancelled before shutdown; see `tests/integration/test_health_polling_loop.py` for the real, both-directions proof (continuous re-polling, clean cancellation). |
| **Upgrade strategies** | **Updated 2026-08-01 (`P02-S05-M13-T07`): two of the three named questions are answered by the existing schema, and a real, buildable slice is built on that basis — the third remains genuinely open.** (c), the load-bearing one, was already decided by the schema itself: `catalog.packs` is keyed on `pack_id` alone, so no two versions of one pack can ever be simultaneously `activated` — an upgrade is necessarily an in-place migration of the one existing row, not a second row. (a) follows from the same fact plus the absence of any `upgrading` state in the canonical 8-value lifecycle (no schema migration was made to add one): `SqlPackLifecycleRepository.upgrade()` migrates an already-`activated` pack's `catalog.packs`/`catalog.agents`/`catalog.tools`/`catalog.prompts` rows to a new manifest version in one transaction — reconciling agents/tools (update what persists, delete what the new version drops, insert what it adds) and appending prompts (immutable, versioned) — refusing a same-or-older version before touching any row. **(b) — what happens to workflow instances of the old version that are mid-run — remains genuinely open**, unanswered by this step: nothing in this codebase tracks which pack version a running workflow instance is pinned to, so an in-flight instance's next step transparently resolves against whichever version is current at that moment. This was built as a real, scoped Task without first writing the ADR this row previously said the work "warrants" — a deliberate, disclosed product-owner decision to proceed, not an oversight; a retroactive ADR recording this reasoning (and formally deciding (b)) remains real, valuable follow-up work. |

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

---

## 11. Related Documents

**Governing decisions (ADRs):**
- [ADR-0001 — Modular Capability Pack Architecture](../../18_decision_log/adr/ADR-0001-modular-capability-pack-architecture.md)
- [ADR-0007 — Human Governance for Critical Decisions](../../18_decision_log/adr/ADR-0007-human-governance-for-critical-decisions.md) — activation approval
- [ADR-0009 — Packaging and Dependency Management](../../18_decision_log/adr/ADR-0009-packaging-and-dependency-management.md) — entry-point discovery
- [ADR-0010 — Composition and Dependency Injection](../../18_decision_log/adr/ADR-0010-composition-and-dependency-injection.md) — `PackContext`, no escape hatch
- [ADR-0011 — Persistence and Workflow State](../../18_decision_log/adr/ADR-0011-persistence-and-workflow-state.md) — snapshot + transition log in one transaction

**Superior documents:**
- `../platform/system_architecture.md`
- `kernel_architecture.md`
- `../capability_framework/capability_pack_contract.md`
- `../capability_framework/manifest_schema.md`
- `manifest_loader.md` — hands validated packs to this component

**Interacting subsystems:**
- `configuration_manager.md` — decides which packs are enabled
- `security_manager.md` — permission validation at activation (documented, not yet enforced)
- `health_lifecycle.md` — aggregates pack health reported here
- `evaluation_engine.md` — needs to know which pack versions were active during an experiment
- `workflow_engine.md` — sees only components from activated packs
- `../platform/platform_sdk.md` — §6 `PackContext`, §7 pack entry point, §9 `pack_contract_suite`
- `../../13_dashboard/dashboard_architecture.md` — consumes pack status and health

**Owned tables:**
- `../../08_database/data_model.md` §5 (`catalog.packs`, `catalog.pack_state_transitions`, `catalog.agents`, `catalog.tools`, `catalog.workflow_definitions`, `catalog.prompts`)

**Reference:**
- `../../20_glossary/glossary.md`
- `../../19_roadmap/feature_inventory.md`, `../../19_roadmap/history/INDEX.md`
