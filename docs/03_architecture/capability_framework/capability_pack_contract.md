# Capability Pack Contract – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Capability Pack Contract  
**Version:** 1.3  
**Status:** Approved  
**Last Updated:** 2026-07-28 (product-owner decision: the direct-Kernel-import exception under Platform Interaction Rules is now a **hard gate** — no new agent or Capability Pack may be added until the Platform SDK exists. The five existing Software Engineering pack agents are grandfathered and need no change.)

**Previously:** 2026-07-28 (v1.2 — added Implementation Status and Related Documents; corrected the Current Priority Packs status column, the contract-suite requirement, and the directory-structure claims against the one real pack on disk). 2026-07-28 (v1.1 — Platform Interaction Rules: added a dated exception note recording the `software-engineering` pack's real, live direct-Kernel-import compromise)

---

## Purpose

This document defines the mandatory contract that every Capability Pack must implement to integrate with the AI_OS platform.

The contract ensures that all Capability Packs are:

- Compatible with the Platform Kernel
- Independently installable
- Independently versioned
- Discoverable
- Configurable
- Secure
- Observable
- Governed
- Replaceable

No Capability Pack may be loaded by AI_OS unless it complies with this contract.

This contract is mandatory for every present and future Capability Pack.

---

## Implementation Status (2026-07-28)

**Built:** the manifest half of this contract is real and enforced. `../../../platform_sdk/schemas/manifest.schema.json` genuinely validates every manifest before any pack code is imported, and `ai_os_kernel/manifest_loader/` enforces a subset of the semantic rules on top of it. The Capability Manager (`ai_os_kernel/capability_manager/`) implements a real `register → activate → deactivate` lifecycle, recording every transition in `catalog.pack_state_transitions`, and the Agent/Tool registries resolve real catalog rows gated on pack activation. **One pack genuinely complies with the manifest contract and loads:** `../../../capability_packs/software-engineering/` — 5 declared agents (`requirements-analyst`, `architecture`, `build`, `qa-test`, `documentation`), 1 declared workflow (`se.delivery_pipeline`), 4 prompts, its own `pyproject.toml` as a real `uv` workspace member, `README.md`, `CHANGELOG.md`, and tests. `../../../capability_packs/_template/` provides a manifest + README + CHANGELOG scaffold.

**Not built:**

- **The SDK half of this contract does not exist.** There is no `ai-os-sdk` package (see `../platform/platform_sdk.md` §1a), so "interact only through the Platform SDK" is currently unenforceable — and is knowingly violated by the one real pack. See the dated exception under Platform Interaction Rules below.
- **The SDK pack contract suite does not exist**, so the Testing Requirements and Validation Checklist below are review-enforced, not tool-enforced. Nothing checks the Prohibited Practices list mechanically, including "no forbidden dependencies".
- **No pack discovery beyond a filesystem scan**, no entry-point discovery, no upgrade path, no health monitoring, and no permissions enforcement in the Capability Manager. The Health Contract below has no implementation: no pack exposes a health check and nothing would call one.
- **No Quality Gate Engine**, so the Validation Checklist's "Quality Gates passed" cannot be satisfied; **no `EventBus`**, so the Event Contract is unexercised; **no Command implementation path**; **no pack-declared Tool** (the one real tool, `SandboxedCommandTool`, is Kernel-internal and not manifest-declared); **no pack-declared Quality Gate**.
- **Three of the four scoped packs have zero tracked files, absent from a fresh clone:** `capability_packs/project_intelligence/`, `capability_packs/voice_jarvis/`, `capability_packs/benchmarking/`. (A stray, never-tracked, dead duplicate directory, `capability_packs/software_engineering/` — underscored, not the real hyphenated `software-engineering/` — was investigated and removed in the 2026-07-28 documentation consolidation audit; see `../../19_roadmap/history/025_documentation_consolidation_audit.md`.)
- **The Platform SDK gate (product-owner decision, 2026-07-28) is now active:** no new agent or Capability Pack may be added until `ai-os-sdk` exists — see the dated exception under Platform Interaction Rules below, which this gate amends. This blocks Stage C/H's remaining agent work and Stages E/D/F's remaining packs equally.

Authoritative, always-current status: `../../19_roadmap/feature_inventory.md` (per-module completion table — rows 13, 27, 29–34) and `../../19_roadmap/implementation_status.md`. Build history: `../../19_roadmap/history/INDEX.md`.

---

## Scope

This contract applies to every Capability Pack, including:

- Software Engineering
- Project Intelligence (existing/legacy system analysis)
- Voice (Jarvis)
- Benchmarking
- Future domain-specific Capability Packs

*(An earlier draft listed a "Resume Intelligence" pack. No such pack is planned, documented, or in scope; the reference is withdrawn.)*

---

## Core Design Principles

Every Capability Pack shall:

- Extend the platform without modifying the Platform Kernel
- Be completely isolated from other Capability Packs
- Be manifest-driven
- Be interface-driven
- Be configuration-driven
- Be independently testable
- Be independently deployable
- Be independently versioned
- Be independently upgradeable
- Be LLM-agnostic
- Be observable
- Be governed
- Be secure

---

## Mandatory Requirements

**Always required:**

- `manifest.yaml` — valid against `../../../platform_sdk/schemas/manifest.schema.json` *(enforced today)*
- `README.md` and `CHANGELOG.md` *(review-enforced)*
- A `CapabilityPack` entry point implementation *(declared and checked by the schema; not yet resolved/imported by any contract test)*
- Tests, including a passing run of the SDK pack contract suite *(the suite does not exist — see `../platform/platform_sdk.md` §9; packs currently ship their own tests only)*
- Semantic version and health reporting *(version enforced by the schema; health reporting has no implementation on either side)*

**Required only if the pack provides them:**

Agents · Workflows · Tools · Commands · Prompts · Quality Gates · Configuration schema · Events · Services · Models · Resources

This distinction is deliberate. v1.0 of this contract required all thirteen artifact classes from every pack, which would force the Voice and Benchmarking packs to ship empty `tools/`, `commands/`, and `models/` directories as ceremony. A pack declares what it provides; the loader validates what it declared. Empty required folders signal nothing and cost review attention.

---

## Standard Directory Structure

```text
capability_packs/
└── <pack_name>/
    ├── manifest.yaml            required
    ├── pyproject.toml           required (own distribution — ADR-0009)
    ├── README.md                required
    ├── CHANGELOG.md             required
    ├── LICENSE                  required
    ├── src/ai_os_pack_<name>/   required — implementation
    │   ├── pack.py              the CapabilityPack entry point
    │   ├── agents/              if the pack provides agents
    │   ├── tools/               if the pack provides tools
    │   ├── gates/               if the pack provides quality gates
    │   ├── commands/            if the pack provides commands
    │   └── models/              Pydantic I/O models
    ├── workflows/               workflow definition files, if any
    ├── prompts/                 versioned prompt files, if any
    ├── tests/                   required
    └── docs/                    required
```

Only the folders a pack actually uses need to exist. Additional folders may be added when justified.

**How the one real pack compares (updated 2026-07-29).** `../../../capability_packs/software-engineering/` has `manifest.yaml`, `pyproject.toml`, `README.md`, `CHANGELOG.md`, `src/ai_os_pack_software_engineering/` (with `pack.py`, `agents/`, `workflows/models.py`), `workflows/`, `prompts/`, and `tests/`. It has **no `LICENSE`** and **no `docs/`**, both listed as required above — a real, open gap, not a permitted omission (the "only the folders a pack actually uses" allowance covers the conditional folders, not the required ones). Its pack-level documentation currently lives outside the pack, in `../../06_capability_packs/software_engineering/`. Closing this means either adding `LICENSE` + `docs/` to the pack or amending this contract; it is recorded here rather than left as silent drift. **(2026-07-29):** this pack's own `pipeline.py` — test-harness workflow composition, never pack-facing capability, imported only by two Kernel-side tests — was relocated out of `src/ai_os_pack_software_engineering/` into `../../../tests/integration/_delivery_pipeline.py` (`platform_sdk_v1_scope.md` step 7), since leaving it inside the pack's own shipped wheel meant `pack_contract_suite` check 7 (forbidden imports) could never pass on this pack.

---

## Manifest Contract

Every Capability Pack shall include a `manifest.yaml` file.

The manifest shall contain, at minimum:

- Pack ID
- Name
- Version
- Description
- Author / Owner
- Compatibility
- Dependencies
- Required Platform / Kernel Version
- Registered Agents
- Registered Workflows
- Registered Tools
- Registered Commands
- Configuration Schema / Files
- Permissions
- Feature Flags
- Health Endpoint (where applicable)

The Manifest System is the single source of truth for discovery, validation, loading and lifecycle management.

---

## Identity Requirements

Each Capability Pack shall define:

- Unique Identifier
- Display Name
- Version
- Description
- Owner
- Maintainer
- License
- Repository
- Documentation Location

Identifiers shall remain globally unique.

---

## Dependency Rules

Capability Packs may depend on:

- Platform Kernel interfaces — meaning **the Kernel-implemented interfaces as published by the Platform SDK**, never the `ai_os_kernel` distribution itself. `../platform/platform_sdk.md` §2 rule 1 is the binding form: a pack depending on `ai-os-kernel` fails CI. This clarification resolves an apparent contradiction between this list and Platform Interaction Rules' "Direct Kernel access is prohibited" below — they are consistent; the phrase above was ambiguous, not permissive.
- Platform SDK
- Approved Platform Services

Capability Packs shall not:

- Depend on another Capability Pack’s internal implementation
- Modify Platform Kernel behavior
- Introduce circular dependencies

---

## Configuration Contract

All configuration shall be externalized.

Examples include:

- Feature flags
- Timeouts
- Retry counts
- Model selection
- Thresholds
- Prompt selection
- Paths
- Logging levels

Secrets shall never be stored inside the Capability Pack source code.

---

## Agent Contract

Every registered agent shall define:

- Unique ID
- Name
- Description
- Purpose
- Required Inputs
- Produced Outputs
- Required Permissions
- Supported Workflows

Agents shall only communicate through the Workflow Engine.  
Direct agent-to-agent communication is prohibited.

---

## Workflow Contract

Every workflow shall define:

- Workflow ID
- Name
- Description
- Entry point
- Inputs
- Outputs
- Execution steps
- Required / Participating Agents
- Quality Gates
- Human Approval Points
- Failure Handling

Workflow execution is managed exclusively by the Workflow Engine.

---

## Tool Contract

Every tool shall define:

- Tool ID
- Name
- Description
- Input Schema
- Output Schema
- Permissions
- Error Behaviour

Tools shall expose stable contracts.

---

## Prompt Contract

Every prompt shall:

- Have a unique identifier
- Be versioned
- Be documented
- Support configuration where applicable
- Be discoverable through the Manifest System

Prompts shall never be hardcoded inside business logic.

---

## Command Contract

Commands shall define:

- Command ID
- Name
- Description
- Parameters
- Permissions
- Execution Behaviour

Commands shall remain backward compatible where practical.

---

## API Contract

If a Capability Pack exposes APIs, they shall:

- Be versioned
- Be documented
- Validate inputs
- Return consistent responses
- Follow platform API standards

---

## Event Contract

Capability Packs may publish or subscribe to platform events.

Events shall:

- Have documented schemas
- Be versioned where required
- Remain backward compatible whenever practical

---

## Security Contract

Capability Packs shall:

- Apply least privilege
- Validate all external input
- Protect sensitive information
- Use approved secret management
- Support auditing

Capability Packs shall never bypass platform security controls.

---

## Observability Contract

Capability Packs shall support:

- Structured logging
- Metrics
- Trace IDs
- Workflow IDs
- Health reporting
- Audit logging

Observability shall comply with platform standards.

---

## Health Contract

Every Capability Pack shall expose health information.

Health status should include:

- Version
- Status
- Loaded components
- Dependency status
- Configuration status
- Startup validation

---

## Versioning Contract

Capability Packs shall follow Semantic Versioning (MAJOR.MINOR.PATCH).

Version updates shall reflect:

- Major changes (breaking)
- Minor enhancements
- Patches

Breaking changes require documentation.

---

## Lifecycle

The canonical runtime lifecycle state machine is defined in `../kernel/capability_manager.md` and is not restated here:

```text
discovered → validated → installed → configured → activated
                              → deactivated | failed → uninstalled
```

Development and manifest authoring precede `discovered` and are covered by `../../06_capability_packs/capability_pack_development_guide.md`. Upgrade is a `deactivated → validated → … → activated` cycle for the new version, not a separate state.

---

## Communication Rules

Capability Packs communicate through:

- Platform interfaces
- Platform APIs
- Event Bus
- Workflow Engine

Capability Packs shall never directly access another Capability Pack’s internal implementation.

---

## Extensibility Rules

New functionality shall be added by:

- Registering new agents
- Registering new workflows
- Registering new tools
- Registering new commands
- Updating the manifest

Platform Kernel modifications shall not be required.

---

## Platform Interaction Rules

Capability Packs interact with AI_OS only through:

- Platform SDK
- Published Interfaces / Contracts
- Event Bus
- Configuration System
- LLM Gateway
- Knowledge Interfaces
- Memory Interfaces

Direct Kernel access is prohibited.

**Dated exception, recorded rather than silently violated (2026-07-28) — now a hard gate on further growth (product-owner decision, 2026-07-28).** The `software-engineering` pack — this contract's own "Highest priority" pack — currently imports `ai_os_kernel.*` internals directly in every one of its agent modules and its pipeline composition (`ai_os_pack_software_engineering.pipeline`), not only through the Platform SDK. **Why:** no `ai-os-sdk` package exists yet (`kernel/pyproject.toml` itself lists it under "Planned, not yet scaffolded") — there is nothing else for a pack to depend on for a real LLM Gateway/Prompt Engine/database connection today, and this pack's own agents need all three to genuinely call a model and persist results. This is a real, live violation of the rule stated above, not a hypothetical one — a fresh reader should not be misled into thinking it is categorically impossible.

**The exception is bounded to the pack surface that already exists.** It is *not* a licence to keep growing that surface. **The Platform SDK (`ai-os-sdk`) must be built before any new agent is added to any Capability Pack, and before any new Capability Pack is added, full stop.** This is a hard blocker, not a soft "temporary" note — no exception, no schedule slip, no "just this once." The five existing Software Engineering pack agents (`requirements-analyst`, `architecture`, `build`, `qa-test`, `documentation`) are grandfathered as-is; nothing about them needs to change today, and this gate does not require retrofitting them before the SDK exists. It blocks only the *next* addition.

**What removes it:** a real Platform SDK package (`ai-os-sdk`) exposing the LLM Gateway/Prompt Engine/database access packs currently reach through Kernel internals — at that point every pack, including the five existing agents, migrates onto the SDK, and this exception closes for good. Building that package is explicitly its own dedicated, scoped step — see `docs/19_roadmap/implementation_status.md` §4 and `docs/19_roadmap/feature_inventory.md` module 27 for current status, and `docs/process/standing_rules.md` for the standing rule this gate is recorded under. Each affected module's own docstring records the same compromise at the code level.

---

## Testing Requirements

Every Capability Pack shall include:

- Unit Tests
- Integration Tests
- Workflow Tests
- Contract Tests
- Regression Tests
- Security Tests (where applicable)

Critical functionality should include performance testing where relevant.

---

## Documentation Requirements

Each Capability Pack shall include:

- README
- Architecture Overview
- Installation Guide
- Configuration Guide
- Usage Guide
- API Documentation (if applicable)
- Troubleshooting Guide
- CHANGELOG

Documentation shall remain synchronized with implementation.

---

## Current Priority Packs

Status column refreshed 2026-07-28 against what is actually on disk; see Implementation Status above and `../../19_roadmap/feature_inventory.md` rows 29–34 for the authoritative figures.

| Capability Pack                  | Priority | Status   |
|----------------------------------|----------|----------|
| Software Engineering             | Highest  | **Partially built** — `capability_packs/software-engineering/`: 5 agents, 1 workflow (`se.delivery_pipeline`), 4 prompts, real and loading; no pack-declared tools or quality gates; imports Kernel internals under the dated exception below |
| Existing Project Intelligence    | High     | Not started — `capability_packs/project_intelligence/` is an empty directory; documented in `../../06_capability_packs/project_intelligence/` |
| Voice (Jarvis)                   | High     | Not started — `capability_packs/voice_jarvis/` is an empty directory; documented in `../../14_voice_jarvis/` |
| Benchmarking                     | Medium   | Not started — `capability_packs/benchmarking/` is an empty directory |
| Future Domain Packs              | Future   | -        |

A fifth directory, `capability_packs/_template/`, holds a manifest + README + CHANGELOG scaffold for authoring a new pack; it is not itself a pack. `capability_packs/software_engineering/` (underscored) is a stale empty directory, not a pack.

---

## Validation Checklist

Before activation / installation, verify:

- [ ] Manifest is valid — *machine-enforced today by the JSON Schema + Manifest Loader*
- [ ] Required contracts are implemented — *review only; no SDK Protocols exist to check against*
- [ ] Dependencies are satisfied — *`dependencies.packs` emptiness is schema-enforced; `sdkVersion` is unenforceable while no SDK exists*
- [ ] Tests have passed — *the pack's own tests run in CI; there is no contract suite*
- [ ] Documentation is complete — *review only*
- [ ] Security validation passed — *review only; `tests/security/` is an empty directory*
- [ ] Configuration is valid — *`configSchema` is declared and schema-checked; pack config defaults are not yet a resolved precedence layer (`../services/configuration_management.md`)*
- [ ] Quality Gates passed — *not possible today: the Quality Gate Engine is 0%*
- [ ] No prohibited dependencies exist — *not checked by any tool; knowingly violated, see below*

---

## Prohibited Practices

Capability Packs shall not:

- Modify the Platform Kernel
- Access another Capability Pack internally
- Hardcode secrets
- Hardcode LLM providers / model names
- Bypass the LLM Gateway
- Bypass the Workflow Engine
- Bypass platform governance
- Bypass Quality Gates
- Bypass security controls
- Invent architecture or contracts
- Introduce circular dependencies

---

## Compliance

A Capability Pack is considered compliant only if it:

- Implements this contract
- Complies with the Project Constitution
- Complies with the AI Governance Framework
- Passes validation
- Passes Quality Gates
- Successfully registers through the Manifest System

Non-compliant Capability Packs shall not be loaded.

---

## Maintenance

This contract shall be reviewed whenever:

- Platform interfaces change
- Manifest schema changes
- Workflow architecture changes
- Plugin architecture evolves
- Governance requirements change

---

## Final Authority

This document defines the mandatory integration contract for every Capability Pack within AI_OS.

Where conflicts exist, the order of precedence is:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Capability Pack Contract  
5. Individual Capability Pack Documentation / Implementation  
6. Source Code

Compliance with this contract is mandatory for every Capability Pack developed for AI_OS.

---

## Related Documents

**Governing ADRs**

- [ADR-0001 — Modular Capability Pack Architecture](../../18_decision_log/adr/ADR-0001-modular-capability-pack-architecture.md) — the decision this contract implements
- [ADR-0009 — Packaging and dependency management](../../18_decision_log/adr/ADR-0009-packaging-and-dependency-management.md) — a pack is its own PEP 621 distribution; entry-point registration
- [ADR-0004 — Interface-driven and configuration-over-code](../../18_decision_log/adr/ADR-0004-interface-driven-and-configuration-over-code.md) — the Configuration Contract
- [ADR-0005 — Agents never communicate directly](../../18_decision_log/adr/ADR-0005-agents-never-communicate-directly.md) — the Agent Contract and Communication Rules
- [ADR-0002 — LLM Gateway single entry point](../../18_decision_log/adr/ADR-0002-llm-gateway-single-entry-point.md) — "shall not hardcode LLM providers / model names"
- [ADR-0006 — Quality gates are mandatory](../../18_decision_log/adr/ADR-0006-quality-gates-are-mandatory.md) · [ADR-0007 — Human governance](../../18_decision_log/adr/ADR-0007-human-governance-for-critical-decisions.md) — the Workflow Contract's gate and approval fields
- [ADR-0016 — Tool execution sandboxing](../../18_decision_log/adr/ADR-0016-tool-execution-sandboxing.md) — the Tool Contract's trust tier
- [ADR-0023 — Identity, roles, and permissions](../../18_decision_log/adr/ADR-0023-identity-roles-and-permissions.md) — the Security Contract's least-privilege rule
- [ADR-0024 — Secrets management backend](../../18_decision_log/adr/ADR-0024-secrets-management-backend.md) — "secrets shall never be stored inside pack source"
- Full index: `../../18_decision_log/README.md`

**Machine-readable schema and the one real example**

- `../../../platform_sdk/schemas/manifest.schema.json` — **authoritative**; validates every manifest before any pack code is imported
- `../../../capability_packs/software-engineering/manifest.yaml` — the one real, loading pack manifest
- `../../../capability_packs/_template/manifest.yaml` — the authoring scaffold

**Architecture**

- `../platform/system_architecture.md` — where the pack layer sits
- `../platform/platform_sdk.md` — the interface surface this contract requires packs to use (**specification only; no implementing package** — the reason for the dated exception above)
- `manifest_schema.md` — the manifest structure and every validation rule in detail
- `../kernel/capability_manager.md` — the canonical lifecycle state machine
- `../kernel/manifest_loader.md` — discovery, validation, registration
- `../agents/agent_architecture.md` · `../agents/agent_communication.md` — the Agent Contract in detail
- `../workflow/workflow_architecture.md` — the Workflow Contract in detail
- `../quality/quality_gates_framework.md` — the Quality Gate Contract in detail (unimplemented)
- `../../06_capability_packs/capability_pack_development_guide.md` — how to author a pack (pre-`discovered` phase)
- `../../06_capability_packs/software_engineering/overview.md` — the flagship pack's own documentation

**Requirements traced to this contract**

- `../../02_requirements/functional/functional_requirements.md` — FR-001 (load and validate a pack, rejecting invalid manifests without partial registration), FR-002 (lifecycle state machine recorded in `catalog.pack_state_transitions`), FR-003 (activate/deactivate without restart), FR-018 (monotonic permission narrowing)

**Terminology**

- `../../20_glossary/glossary.md`

**Current state of the build**

- `../../19_roadmap/feature_inventory.md` (rows 13, 27, 29–34), `../../19_roadmap/implementation_status.md`, `../../19_roadmap/history/INDEX.md`
