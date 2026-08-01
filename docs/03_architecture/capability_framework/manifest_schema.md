# Manifest Schema – AI_OS

**Project:** AI_OS (AI Operating System)
**Document:** Manifest Schema
**Version:** 2.3
**Status:** Approved
**Last Updated:** 2026-08-01 (`P01-S03-M02-T03`/`T04`: entry-point discovery, and semantic rules 13/16, are now real; rule 20 newly identified as currently unenforceable rather than merely unbuilt)

**Previously:** 2026-07-28 (v2.2 — added Implementation Status and Related Documents; corrected the Validation Rules section — **none** of the semantic rules 12–21 is enforced by the Loader today — and the discovery section, which claimed entry-point discovery exists); 2026-07-28 (v2.1 — Validation Rules: added rule 11, `modelAlias` required only when an agent declares `llm:invoke`)

---

## Purpose

The manifest is the single source of truth for discovery, validation, registration, and lifecycle management of a Capability Pack. This document explains the schema and its rules.

**The machine-readable schema is authoritative:**

```text
platform_sdk/schemas/manifest.schema.json     (JSON Schema draft 2020-12)
```

The Manifest Loader validates every manifest against that file before any pack code is imported. Where this document and the JSON Schema differ, **the JSON Schema prevails** and this document is a defect to be corrected.

Version 2.0 replaces the earlier illustrative YAML sketch with a typed, enforceable schema.

---

## Implementation Status (updated 2026-08-01)

**Built:** the schema itself and the validation path around it are among the most genuinely real parts of the platform. `../../../platform_sdk/schemas/manifest.schema.json` exists, is valid draft 2020-12, and is loaded and enforced by `ai_os_kernel/manifest_loader/loader.py` — `ManifestLoader.load_one()` parses the YAML and raises `ManifestError` on any schema violation, and `ManifestLoader.scan()` reports per-pack failures without aborting the scan. **All eleven schema-level rules (1–11) below are genuinely enforced**, including rule 11's conditional `modelAlias` requirement, which is implemented as an `agents[].if`/`then` in the schema file. **Both ADR-0009 discovery mechanisms are real** (`P01-S03-M02-T03`): filesystem scan and entry-point discovery (`ai_os.capability_packs`, via `importlib.metadata`) — combined and de-duplicated by `ManifestLoader.scan()`, so "both routes validate identically" is genuinely true now, not vacuously. **Two semantic rules are real** (`P01-S03-M02-T04`): rule 13 (SDK version range) and rule 16 (workflow-definition existence + step-reference resolution) — see their own entries above for what each checks. The lifecycle state machine is real to the extent of `register → activate → deactivate`, with every transition recorded in `catalog.pack_state_transitions` by `ai_os_kernel/capability_manager/repository.py`. One real manifest validates and loads: `../../../capability_packs/software-engineering/manifest.yaml`.

**Not built:**

- **Eight of the ten semantic rules remain unenforced: 12, 14, 15, 17, 18, 19, 21, and 20 (the last currently unenforceable, not merely unbuilt — see its own entry above).** No kernel-version compatibility check, no cross-pack global ID uniqueness, no reference resolution for `requiredTools`/`requiredPrompts`/`qualityGates`, no permission-subset checks, no `modelAlias` alias-resolution check, and no comparison of declared components against what `activate()` returns.
- **Nothing calls a pack's `entryPoint`.** No code imports a pack's `CapabilityPack` class or calls `activate()`; the lifecycle repository only flips `catalog.packs.state`. It also does not parse a manifest's `agents`/`tools`/`workflows` arrays into `catalog.agents`/`catalog.tools` rows — those are written directly by tests and composition code today.
- **Of the lifecycle states below, `discovered`, `validated`, `activated`, and `deactivated` have real code paths; `installed`, `configured`, `failed`, and `uninstalled` do not have distinct implemented transitions.** "Activation of a pack that affects platform behaviour requires human approval" has no implementation at all — there is no approvals writer or reader anywhere (see `../governance/human_approval_points.md`).
- The `events`, `commands`, `qualityGates`, `tools`, `secrets`, and `health` manifest sections are all schema-valid and declarable but have **no consuming runtime**: no Event Bus, no command dispatcher, no Quality Gate Engine, no pack-declared Tool path, no per-pack secret resolution, and no health-check caller.

Authoritative, always-current status: `../../19_roadmap/feature_inventory.md` (per-module completion table — rows 2, 13, 28) and `../../19_roadmap/implementation_status.md`. Build history: `../../19_roadmap/history/INDEX.md`.

---

## Scope

Applies to every Capability Pack. Agents, workflows, tools, commands, prompts, quality gates, and events are declared **within** the pack manifest — they do not have separate manifests.

---

## Location and Discovery

```text
capability_packs/<pack_id>/manifest.yaml
```

Discovered by ([ADR-0009](../../18_decision_log/adr/ADR-0009-packaging-and-dependency-management.md)):

1. **Entry point** — installed packs register under the `ai_os.capability_packs` group. Production mechanism; supports packs installed from a package index. **Implemented** (`P01-S03-M02-T03`, `manifest_loader/discovery.py`, `discover_entry_point_manifests()`) — no pack in this repository is actually distributed via a registered entry point yet, so this is proven against a real, synthetic installed distribution in tests rather than a real pack today.
2. **Filesystem scan** — configured directories are scanned for `manifest.yaml`, one level deep. Development mechanism. **Implemented** (`manifest_loader/discovery.py`); a configured directory that does not exist is skipped rather than raised on.

Both routes validate identically — genuinely, not vacuously, now that both exist. `ManifestLoader.scan()` de-duplicates a manifest reachable by both. A pack without a valid manifest is never loaded, and a pack that fails validation leaves no partial registration.

---

## Structure

The listing below is a **complete illustrative example**, showing every section the schema permits. It is not the real `software-engineering` manifest: none of the agents, tools, workflows, gates, prompts, commands, or events named here exists in code (`backend-developer`, `build.run`, `se.product_creation`, `se.build`, `se.backend.implement`, `create-product`, `se.implementation.completed`). For the real, loading manifest — 5 agents, 1 workflow, 4 prompts, no tools, no gates, no commands, no events — read `../../../capability_packs/software-engineering/manifest.yaml`. For an authoring starting point, `../../../capability_packs/_template/manifest.yaml`.

```yaml
apiVersion: ai-os/v1
kind: CapabilityPack

metadata:
  id: software-engineering          # kebab-case, globally unique, 3–64 chars
  name: Software Engineering Pack
  version: 1.0.0                    # semantic version
  description: Autonomous software engineering capabilities.
  owner: platform-team
  organization: AI_OS
  license: Apache-2.0
  repository: https://github.com/example/ai-os
  documentation: docs/06_capability_packs/software_engineering/overview.md

compatibility:
  minKernelVersion: 1.0.0
  maxKernelVersion: 2.0.0           # optional

dependencies:
  sdkVersion: ">=1.0.0,<2.0.0"
  services: [storage, search, git, document_processing]
  python: ["libcst>=1.4"]
  packs: []                         # MUST be empty

permissions:                        # closed vocabulary
  - filesystem:read
  - filesystem:write
  - git:read
  - git:write
  - llm:invoke
  - sandbox:execute

featureFlags:
  - name: enable_parallel_implementation
    default: true

configSchema: {}                    # JSON Schema for this pack's config namespace

entryPoint: ai_os_pack_software_engineering.pack:SoftwareEngineeringPack

agents:
  - id: backend-developer           # fully qualified as software-engineering/backend-developer
    name: Backend Development Agent
    version: 1.0.0
    purpose: Implement backend services and business logic from a planned task.
    entrypoint: ai_os_pack_software_engineering.agents.backend:BackendDeveloperAgent
    inputSchema: ai_os_pack_software_engineering.agents.backend:BackendDeveloperInput
    outputSchema: ai_os_pack_software_engineering.agents.backend:BackendDeveloperOutput
    modelAlias: coding-strong       # ALIAS ONLY — a literal model id fails validation
    effort: xhigh
    requiredTools: [fs.read, fs.apply_patch, build.run]
    requiredPrompts: ["se.backend.implement@1"]
    permissions: [filesystem:read, filesystem:write, llm:invoke, sandbox:execute]
    qualityGates: [se.build, se.lint, se.type_check]
    timeoutSeconds: 900

tools:
  - id: build.run
    name: Run Build
    version: 1.0.0
    description: Execute the project build inside a sandbox.
    entrypoint: ai_os_pack_software_engineering.tools.build:BuildTool
    inputSchema: ai_os_pack_software_engineering.tools.build:BuildInput
    outputSchema: ai_os_pack_software_engineering.tools.build:BuildOutput
    trustTier: tier1_sandboxed      # mandatory for anything executing code
    permissions: [sandbox:execute, filesystem:read]
    timeoutSeconds: 600

workflows:
  - id: se.product_creation
    name: Full Product Creation
    version: 1.0.0
    description: Turn a structured specification into working software.
    definition: workflows/product_creation.yaml
    inputsSchema: ai_os_pack_software_engineering.workflows.models:ProductCreationInput
    outputsSchema: ai_os_pack_software_engineering.workflows.models:ProductCreationOutput
    permissions: [filesystem:read, filesystem:write, git:read, git:write, llm:invoke, sandbox:execute]
    trigger: api
    maxIterations: 3
    maxCostUsd: 25.0

qualityGates:
  - id: se.build
    name: Build Succeeds
    version: 1.0.0
    description: The project builds with no errors and dependencies resolve.
    entrypoint: ai_os_pack_software_engineering.gates.build:BuildGate
    severity: blocking
    successCriteria: "build exit code == 0"
    timeoutSeconds: 600

prompts:
  - id: se.backend.implement
    version: 1.0.0
    location: prompts/backend_implement.md
    inputSchema: ai_os_pack_software_engineering.prompts.models:BackendImplementVars

commands:
  - id: create-product
    name: Create Product
    description: Start the product creation workflow from a specification file.
    entrypoint: ai_os_pack_software_engineering.commands.create:CreateProductCommand
    permissions: [workflow:start]

events:
  publish:
    - eventType: se.implementation.completed
      schemaVersion: 1
      payloadSchema: ai_os_pack_software_engineering.events:ImplementationCompleted
  subscribe:
    - eventType: workflow.step.failed
      handler: ai_os_pack_software_engineering.handlers:on_step_failed

secrets:
  - name: GITHUB_TOKEN
    reference: secret://vault/git/github-token

health:
  checkEntrypoint: ai_os_pack_software_engineering.health:check
  intervalSeconds: 60
```

---

## Validation Rules

The Manifest Loader is specified to enforce all of the following. Any failure rejects the pack.

**Status of enforcement (updated 2026-08-01, `P01-S03-M02-T04`):** rules 1–11 are genuinely enforced today, and so are **rules 13 and 16** — `ManifestLoader.load_one()` now also runs `ai_os_kernel.manifest_loader.semantic.validate_sdk_version_range` and `validate_workflow_definitions` after schema validation and `metadata` extraction. **Rules 12, 14, 15, 17, 18, 19, and 21 remain specification only.** Rule 20 is a distinct case — see its own entry below: currently *unenforceable*, not merely unbuilt.

**Schema-level** (enforced by the JSON Schema — **all implemented**):
1. `apiVersion` is `ai-os/v1` and `kind` is `CapabilityPack`.
2. All required fields present; no additional properties anywhere.
3. `metadata.version` and every component `version` are valid semantic versions.
4. `metadata.id`, agent IDs, and command IDs are kebab-case; tool, workflow, gate, and prompt IDs are dot-namespaced lower snake.
5. Every `entrypoint`, `inputSchema`, `outputSchema`, and `handler` matches `module.path:Name`.
6. Every entry in `permissions` is in the **closed vocabulary**. An unknown permission is a hard failure, not a warning.
7. `trustTier` is one of the two defined tiers.
8. `dependencies.packs` is empty — pack-to-pack dependencies are prohibited.
9. `secrets[].reference` matches the `secret://` pattern. A literal secret value cannot validate.
10. `entryPoint` is required when the pack declares agents or workflows.
11. `modelAlias` is required on an `agents[]` entry only when that entry's own `permissions` declares `llm:invoke`; an agent that declares no `llm:invoke` permission (because it genuinely makes no LLM call) may omit `modelAlias` entirely (fixed 2026-07-28 — a genuine, discovered gap: the schema originally required `modelAlias` unconditionally on every agent, forcing an agent with no LLM call to declare a syntactically-valid but unused decoy value; see `docs/19_roadmap/implementation_status.md` for the discovery and `platform_sdk/schemas/manifest.schema.json`'s own `agents[].if`/`then` for the fix).

**Semantic-level** (to be enforced by the Loader beyond the schema — see the status note above for which of 12–21 are actually built):
12. `compatibility.minKernelVersion` ≤ running Kernel version ≤ `maxKernelVersion`.
13. `dependencies.sdkVersion` range includes the running SDK version. **Built** (`P01-S03-M02-T04`, `ai_os_kernel.manifest_loader.semantic.validate_sdk_version_range`) — genuinely enforceable as of this step: `ai-os-sdk` is a real, installed distribution (the Platform SDK initiative), so its real version is compared via `importlib.metadata.version("ai-os-sdk")` against the declared PEP 440 range. Was previously unenforceable, not merely unimplemented, before that package existed.
14. All IDs are globally unique across installed packs.
15. Every `requiredTools`, `requiredPrompts`, and `qualityGates` reference resolves within this pack or the Kernel.
16. Every workflow definition file exists, parses, and its step references resolve. **Built** (`P01-S03-M02-T04`, `ai_os_kernel.manifest_loader.semantic.validate_workflow_definitions`) — reuses the real `WorkflowDefinitionLoader`/`WorkflowDefinition` for existence/parsing/structural validation, then resolves each step's `agentId`/`toolId`/`promptId` against this manifest's own declared `agents[]`/`tools[]`/`prompts[]`.
17. Every agent's declared `permissions` is a **subset** of every workflow that uses it ([ADR-0023](../../18_decision_log/adr/ADR-0023-identity-roles-and-permissions.md)).
18. Every tool's declared `permissions` is a subset of the agents that require it.
19. `modelAlias`, when declared, resolves to a configured alias and is not a literal provider model ID.
20. No circular dependency among workflows and sub-workflows. **Currently unenforceable, not merely unimplemented** (confirmed `P01-S03-M02-T04`, the identical distinction rule 13 was previously in): `ai_os_kernel.workflow_engine.models.WorkflowStep`'s own docstring states plainly that sub-workflow linkage "remain[s] genuinely undocumented — no document defines a field-level contract for them yet." A `sub_workflow`-typed step declares none of the five invocation fields, so no field in the real data model today names *which* workflow a `sub_workflow` step would call — nothing to detect a cycle through. Revisit once sub-workflow linkage has a real field-level contract.
21. Declared components match the implementations returned by `activate()` exactly.

Rules 17 and 18 are what make the monotonic narrowing rule checkable at install time rather than discovered at runtime. **Because they are unimplemented, monotonic narrowing is currently not checked at install time or at runtime** — a real, open gap, tracked as part of the Security Manager (`../../19_roadmap/feature_inventory.md` row 14) and traced to FR-018.

---

## Lifecycle

There is **one** canonical Capability Pack lifecycle, defined here and in `../kernel/capability_manager.md`. Earlier documents contained three divergent lists; this is the single authority:

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
| `discovered` | Found by entry point or filesystem scan; not yet parsed |
| `validated` | Manifest passed schema and semantic validation |
| `installed` | Components registered; not yet available to workflows |
| `configured` | Configuration resolved and validated against `configSchema` |
| `activated` | `activate()` succeeded; components available to the Workflow Engine |
| `deactivated` | Cleanly withdrawn; registrations removed; reactivatable |
| `failed` | Validation, activation, or health failed; not available |
| `uninstalled` | Removed from the platform |

Every transition is recorded in `catalog.pack_state_transitions` with actor and reason — genuinely implemented, in `ai_os_kernel/capability_manager/repository.py`, for the `register → activate → deactivate` transitions that exist. `installed`, `configured`, `failed`, and `uninstalled` have no distinct implemented transition yet.

"Activation of a pack that affects platform behaviour requires human approval" is *specification only; not yet implemented* — the `approvals` table exists (migration 0003) but has no writer, no reader, and no execution path, so no activation is gated on an approval today (see `../governance/human_approval_points.md`).

---

## Not in v1

- **Signed manifests.** Not implemented; provenance is controlled by the install path plus human-approved activation. Recorded as a known gap in `../../09_security/security_architecture.md` §8.
- **Marketplace metadata.** No third-party distribution model in v1.
- **Multi-language entrypoints.** Python only ([ADR-0008](../../18_decision_log/adr/ADR-0008-primary-language-and-runtime.md)).

---

## Governance

Every manifest complies with the Project Constitution, the AI Governance Framework, the System Architecture, the Capability Pack Contract, and the Platform SDK Specification.

---

## Final Authority

Order of precedence:

1. Project Constitution
2. AI Governance Framework
3. System Architecture
4. Capability Pack Contract
5. **`../../../platform_sdk/schemas/manifest.schema.json`** (machine-readable, authoritative)
6. Manifest Schema (this document)
7. Source Code

---

## Related Documents

**Machine-readable schema and the real manifests**

- `../../../platform_sdk/schemas/manifest.schema.json` — **authoritative**; where this document and the schema differ, the schema prevails and this document is the defect
- `../../../capability_packs/software-engineering/manifest.yaml` — the one real, schema-valid, loading pack manifest
- `../../../capability_packs/_template/manifest.yaml` — the authoring scaffold

**Governing ADRs**

- [ADR-0001 — Modular Capability Pack Architecture](../../18_decision_log/adr/ADR-0001-modular-capability-pack-architecture.md) — why a manifest is the single source of truth
- [ADR-0009 — Packaging and dependency management](../../18_decision_log/adr/ADR-0009-packaging-and-dependency-management.md) — the two discovery routes; `dependencies.packs` must be empty
- [ADR-0008 — Primary language and runtime](../../18_decision_log/adr/ADR-0008-primary-language-and-runtime.md) — Python-only entrypoints (Not in v1)
- [ADR-0023 — Identity, roles, and permissions](../../18_decision_log/adr/ADR-0023-identity-roles-and-permissions.md) — the closed permission vocabulary and rules 17–18
- [ADR-0002 — LLM Gateway single entry point](../../18_decision_log/adr/ADR-0002-llm-gateway-single-entry-point.md) — `modelAlias` may never be a literal model id (rule 19)
- [ADR-0016 — Tool execution sandboxing](../../18_decision_log/adr/ADR-0016-tool-execution-sandboxing.md) — `trustTier` (rule 7)
- [ADR-0024 — Secrets management backend](../../18_decision_log/adr/ADR-0024-secrets-management-backend.md) — `secrets[].reference` (rule 9)
- [ADR-0004 — Interface-driven and configuration-over-code](../../18_decision_log/adr/ADR-0004-interface-driven-and-configuration-over-code.md) — `configSchema` and `featureFlags`
- Full index: `../../18_decision_log/README.md`

**Architecture**

- `capability_pack_contract.md` — the contract this manifest declares compliance with
- `../platform/system_architecture.md` — where the pack layer sits
- `../platform/platform_sdk.md` — §8 (`sdkVersion` semantics), §7 (`entryPoint` contract), §9 (the contract suite that would check rules 12–21 from the pack side); **specification only**
- `../kernel/manifest_loader.md` — the component that performs discovery and validation
- `../kernel/capability_manager.md` — the canonical lifecycle state machine restated above
- `../../06_capability_packs/capability_pack_development_guide.md` — authoring a manifest
- `../../09_security/security_architecture.md` §8 — the signed-manifest gap recorded under "Not in v1"

**Requirements traced to this document**

- `../../02_requirements/functional/functional_requirements.md` — FR-001 (invalid manifest rejected with a specific error, leaving no registration), FR-002 (every lifecycle transition recorded in `catalog.pack_state_transitions`), FR-003 (activate/deactivate without restart), FR-018 (monotonic narrowing, rules 17–18)

**Terminology**

- `../../20_glossary/glossary.md`

**Current state of the build**

- `../../19_roadmap/feature_inventory.md` (rows 2, 13, 28), `../../19_roadmap/implementation_status.md`, `../../19_roadmap/history/INDEX.md`
