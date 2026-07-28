# Manifest Schema – AI_OS

**Project:** AI_OS (AI Operating System)
**Document:** Manifest Schema
**Version:** 2.1
**Status:** Approved
**Last Updated:** 2026-07-28 (Validation Rules: added rule 11 — `modelAlias` required only when an agent declares `llm:invoke`; fixed the same way in the JSON schema itself — no other content changed)

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

## Scope

Applies to every Capability Pack. Agents, workflows, tools, commands, prompts, quality gates, and events are declared **within** the pack manifest — they do not have separate manifests.

---

## Location and Discovery

```text
capability_packs/<pack_id>/manifest.yaml
```

Discovered by ([ADR-0009](../../18_decision_log/adr/ADR-0009-packaging-and-dependency-management.md)):

1. **Entry point** — installed packs register under the `ai_os.capability_packs` group. Production mechanism; supports packs installed from a package index.
2. **Filesystem scan** — configured directories are scanned for `manifest.yaml`. Development mechanism.

Both routes validate identically. A pack without a valid manifest is never loaded, and a pack that fails validation leaves no partial registration.

---

## Structure

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

The Manifest Loader enforces all of the following. Any failure rejects the pack.

**Schema-level** (enforced by the JSON Schema):
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

**Semantic-level** (enforced by the Loader beyond the schema):
12. `compatibility.minKernelVersion` ≤ running Kernel version ≤ `maxKernelVersion`.
13. `dependencies.sdkVersion` range includes the running SDK version.
14. All IDs are globally unique across installed packs.
15. Every `requiredTools`, `requiredPrompts`, and `qualityGates` reference resolves within this pack or the Kernel.
16. Every workflow definition file exists, parses, and its step references resolve.
17. Every agent's declared `permissions` is a **subset** of every workflow that uses it ([ADR-0023](../../18_decision_log/adr/ADR-0023-identity-roles-and-permissions.md)).
18. Every tool's declared `permissions` is a subset of the agents that require it.
19. `modelAlias`, when declared, resolves to a configured alias and is not a literal provider model ID.
20. No circular dependency among workflows and sub-workflows.
21. Declared components match the implementations returned by `activate()` exactly.

Rules 17 and 18 are what make the monotonic narrowing rule checkable at install time rather than discovered at runtime.

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

Every transition is recorded in `catalog.pack_state_transitions` with actor and reason. Activation of a pack that affects platform behaviour requires human approval.

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
5. **`platform_sdk/schemas/manifest.schema.json`** (machine-readable, authoritative)
6. Manifest Schema (this document)
7. Source Code
