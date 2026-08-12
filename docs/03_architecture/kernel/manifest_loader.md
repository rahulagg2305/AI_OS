# Plugin / Manifest Loader Design – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Plugin / Manifest Loader Design  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## 1. Purpose

This document defines the detailed design of the **Plugin / Manifest Loader**, a core component of the AI_OS Platform Kernel.

The Manifest Loader is responsible for discovering, validating, and loading Capability Packs and their declared components (Agents, Workflows, Tools, Commands, Prompts, etc.) based on the official Manifest Schema and Capability Pack Contract.

It is the primary mechanism that makes the platform extensible without modifying the Kernel.

This document is subordinate to:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Kernel Architecture  
5. Capability Pack Contract  
6. Manifest Schema  

---

## Implementation Status (2026-08-01)

**Built:** `kernel/src/ai_os_kernel/manifest_loader/` (4 modules). `discovery.py` performs **both ADR-0009 discovery mechanisms**: `discover_manifests()`, the filesystem scan over configured pack directories, and, as of `P01-S03-M02-T03`, `discover_entry_point_manifests()`, the `ai_os.capability_packs` entry-point mechanism — installed distributions are enumerated via `importlib.metadata.entry_points()`, and each one's `manifest.yaml` is located through its own recorded distribution files (`Distribution.files`/`locate_file()`), never by importing the entry point's own target (§6: "must not execute domain logic from the pack"). `ManifestLoader.scan()` in `loader.py` combines both mechanisms and de-duplicates identical resolved paths, so §3's "both validated identically" is no longer vacuous. `ManifestLoader` does YAML parsing, **JSON Schema validation against the real `platform_sdk/schemas/manifest.schema.json`** (Draft 2020-12, with the schema itself checked at construction time), and `metadata` extraction. Two entry points with deliberately different failure semantics, both real: `load_one()` **fails closed** — an invalid manifest raises `ManifestError` and is never returned — while `scan()` never raises, capturing each failure into a `ManifestLoadFailure` so one broken pack cannot hide every other pack from status reporting. `models.py` holds `PackMetadata`, `DiscoveredManifest`, `ManifestLoadFailure`, `ManifestScanReport`. Built in step 3 of `kernel/src/ai_os_kernel/bootstrap.py`. The JSON Schema itself is the most complete artifact in this area — real, versioned, and actively enforced.

**Not built:** **No semantic validation at all.** The loader performs parse + schema-validate + extract and nothing else (its own module docstring says so). That means **none** of the 10 semantic rules (12–21) in `../capability_framework/manifest_schema.md` is enforced: no kernel-version compatibility check, no `sdkVersion` range check (unenforceable — no SDK package exists), no cross-pack global ID uniqueness, no reference resolution, no dependency resolution, no circular-dependency detection, and **no permission-subset checks** — so §3's "agent permissions are a subset of every workflow using them" and the platform's monotonic-narrowing rule are not verified at install time or at runtime. **No forbidden-import verification:** §3's "no provider SDK, no `ai_os_kernel`, no other pack" check does not run — the CI step that would enforce it is gated on `scripts/check_import_boundaries.py`, which does not exist. **No Component Registrar** — nothing writes `catalog.agents` / `catalog.tools` / `catalog.workflow_definitions` rows from a manifest, and nothing calls a pack's `entryPoint`; those rows are currently written directly by other code paths. **No Audit Logger** (`governance.audit_log` has no writer anywhere for this component), so §8's per-attempt record does not exist. Of §5's ten loading-flow steps, only 1–4 are real; steps 5–10 are unimplemented. Of §4's nine components, only Pack Discovery, Manifest Parser, Schema Validator and Error Reporter exist.

Authoritative, always-current status: `../../19_roadmap/feature_inventory.md` (per-module completion table). Detailed build history: `../../19_roadmap/history/INDEX.md` (specifically `001_project_bootstrap_and_configuration.md`).

---

## 2. Design Goals

The Manifest Loader must:

- Reliably discover Capability Packs
- Strictly validate manifests against the Manifest Schema
- Enforce the Capability Pack Contract
- Register valid components with the rest of the Kernel
- Fail safely (invalid packs must not be loaded)
- Support versioning and compatibility checks
- Be fully observable and auditable
- Remain domain-agnostic

---

## 3. Core Responsibilities

- Discover packs by **entry point** (`ai_os.capability_packs`, the production mechanism) and by **filesystem scan** of configured directories (the development mechanism) — both validated identically ([ADR-0009](../../18_decision_log/adr/ADR-0009-packaging-and-dependency-management.md)). *(Both exist — see Implementation Status.)*
- Load and parse `manifest.yaml`
- Validate against **`platform_sdk/schemas/manifest.schema.json`** — the authoritative machine-readable schema, and the one file that really exists under `platform_sdk/` — plus the **10 semantic rules (12–21)** in `../capability_framework/manifest_schema.md`. *(That document's Validation Rules section is the authority on the count: 21 rules total, 11 schema-level and 10 semantic. Earlier revisions of this document said "20 semantic rules," conflating the two groups.)*
- Verify no forbidden imports: no provider SDK, no `ai_os_kernel`, no other pack
- Verify declared permissions are in the closed vocabulary, and that agent permissions are a subset of every workflow using them
- Check Kernel version compatibility
- Resolve and validate dependencies
- Detect circular dependencies
- Register Agents, Workflows, Tools, Commands, and other declared components
- Provide registration information to the Capability Manager and other Kernel components
- Emit clear errors and audit records for rejected packs

---

## 4. High-Level Structure

```text
Manifest Loader
│
├── Pack Discovery
├── Manifest Parser
├── Schema Validator
├── Contract Validator
├── Dependency Resolver
├── Compatibility Checker
├── Component Registrar
├── Error Reporter
└── Audit Logger
```

---

## 5. Loading Flow

1. Discovery of pack directories
2. Reading of `manifest.yaml`
3. Parsing into a structured object
4. Schema validation
5. Contract validation (required fields, rules, etc.)
6. Compatibility check against current Kernel version
7. Dependency resolution
8. Circular dependency detection
9. Registration of valid components
10. Handover to Capability Manager for lifecycle management

Any failure in steps 3–8 should prevent the pack from being activated.

---

## 6. Key Design Rules

- A Capability Pack without a valid manifest shall never be loaded.
- Validation must be strict; the platform prefers to reject a pack rather than load something unsafe or non-compliant.
- The loader itself must not execute domain logic from the pack.
- Registration makes components visible to the Workflow Engine, Agent Invoker, Tool Invoker, etc., but does not automatically activate them (activation is handled by the Capability Manager and configuration). *(Naming note: "Agent Invoker" and "Tool Invoker" are documented roles, not packages. The Agent Invoker role is filled by `AgentStepExecutor` in `kernel/src/ai_os_kernel/workflow_engine/step_executor.py`; there is no `tool_invoker` package anywhere, and the `ToolInvoker` Protocol in `../platform/platform_sdk.md` §5.6 is unbuilt — see `capability_manager.md` §7.)*

---

## 7. Relationship with Other Components

- **Capability Pack Contract** and **Manifest Schema** define what is valid.
- **Capability Manager** takes over after successful loading for installation, activation, health, and removal.
- **Workflow Engine**, **Agent Invoker**, and **Tool Invoker** consume the registered components.
- **Configuration Manager** influences which packs are enabled and where packs are discovered.
- **Security Manager** may participate in permission validation during registration.

---

## 8. Observability & Audit

Every load attempt must be recorded, including:

- Pack ID and version
- Success or failure
- Validation errors (if any)
- Components that were registered
- Timestamp and Kernel version

---

## 9. Current Status

This document defines the design baseline for the Plugin / Manifest Loader. The three items v1.0 of this section deferred are settled as follows — none is left open as "to be refined."

| Item | Status |
|---|---|
| **Discovery mechanisms** | **Decided and built (2026-08-01, `P01-S03-M02-T03`).** [ADR-0009](../../18_decision_log/adr/ADR-0009-packaging-and-dependency-management.md) fixes both mechanisms and which is which: the `ai_os.capability_packs` Python entry point for production, a filesystem scan of configured directories for development, validated identically — both now real in `kernel/src/ai_os_kernel/manifest_loader/discovery.py`, combined and de-duplicated by `ManifestLoader.scan()`. No pack in this repository is actually distributed via a registered entry point yet (no `ai-os-sdk`-published pack exists to register one), so this mechanism is proven against a real, synthetic installed distribution in tests rather than a real pack today — the same "mechanism real, not yet exercised by production data" shape several other Stage A components carry. |
| **Validation implementation** | **Fully specified, mostly unbuilt.** `../capability_framework/manifest_schema.md` is the authority: 21 rules, 11 enforced by `platform_sdk/schemas/manifest.schema.json` (real, and really enforced) and 10 semantic. **Named remaining gap:** none of rules 12–21 is enforced. One of them — the `sdkVersion` range check — is genuinely *unenforceable* rather than merely unbuilt, because there is no `ai-os-sdk` package to have a version; it stays blocked until the Platform SDK exists. The other nine are buildable now, and rules 17–18 (permission subsets) are the highest-value ones: without them, monotonic narrowing is checked nowhere, which `manifest_schema.md` records as an open security gap traced to FR-018. |
| **Registration APIs** | **Boundary decided, shape open.** The handover target is settled: this component validates and hands over; the Capability Manager owns lifecycle from `installed` onward (§7, `capability_manager.md` §4), and the persisted destination is the `catalog` schema (`../../08_database/data_model.md` §5). **Named remaining gap:** the in-process shape of that handover is undefined — whether the loader returns a manifest object and the Capability Manager writes catalog rows, or the loader writes them itself, has not been decided. It is worth deciding deliberately rather than by accident, because it also determines who calls a pack's `CapabilityPack.activate()` — which today nothing does at all (see `kernel/src/ai_os_kernel/capability_manager/pack_contract.py`, which records that gap explicitly). |

---

## 10. Final Authority

Order of precedence:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Capability Pack Contract  
5. Manifest Schema  
6. Kernel Architecture  
7. Plugin / Manifest Loader Design  
8. Source Code

---

## 11. Related Documents

**Governing decisions (ADRs):**
- [ADR-0001 — Modular Capability Pack Architecture](../../18_decision_log/adr/ADR-0001-modular-capability-pack-architecture.md) — packs as the only extension mechanism
- [ADR-0009 — Packaging and Dependency Management](../../18_decision_log/adr/ADR-0009-packaging-and-dependency-management.md) — the two discovery mechanisms
- [ADR-0004 — Interface-Driven and Configuration over Code](../../18_decision_log/adr/ADR-0004-interface-driven-and-configuration-over-code.md)
- [ADR-0023 — Identity, Roles and Permissions](../../18_decision_log/adr/ADR-0023-identity-roles-and-permissions.md) — the closed permission vocabulary validated here
- [ADR-0015 — Testing and CI](../../18_decision_log/adr/ADR-0015-testing-and-ci.md) — the forbidden-import check and the pack contract suite

**Defining authorities (what counts as valid):**
- `../capability_framework/manifest_schema.md` — the 21 validation rules; authoritative on the count and on which are enforced
- `../capability_framework/capability_pack_contract.md`
- `platform_sdk/schemas/manifest.schema.json` — the machine-readable schema this loader really executes

**Superior documents:**
- `../platform/system_architecture.md`
- `kernel_architecture.md`

**Interacting subsystems:**
- `capability_manager.md` — takes over at `installed`; owns lifecycle, health, removal
- `configuration_manager.md` — supplies the pack directories to scan and which packs are enabled
- `security_manager.md` — permission validation during registration (documented, not yet performed)
- `workflow_engine.md` — consumes registered agents, tools, and workflow definitions
- `observability.md` — the audit trail §8 requires
- `../platform/platform_sdk.md` §7 (pack entry point), §8 (SemVer compatibility), §9 (`pack_contract_suite`)

**Owned tables:**
- `../../08_database/data_model.md` §5 — the `catalog` schema this component's registration step will populate (`catalog.agents`, `catalog.tools`, `catalog.workflow_definitions`, `catalog.prompts`, `catalog.packs`)

**Reference:**
- `../../20_glossary/glossary.md`
- `../../19_roadmap/feature_inventory.md`, `../../19_roadmap/history/INDEX.md`
