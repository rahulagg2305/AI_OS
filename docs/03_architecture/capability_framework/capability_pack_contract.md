# Capability Pack Contract – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Capability Pack Contract  
**Version:** 1.1  
**Status:** Approved  
**Last Updated:** 2026-07-28 (Platform Interaction Rules: added a dated exception note recording the `software-engineering` pack's real, live direct-Kernel-import compromise — no other content changed)

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

- `manifest.yaml` — valid against `platform_sdk/schemas/manifest.schema.json`
- `README.md` and `CHANGELOG.md`
- A `CapabilityPack` entry point implementation
- Tests, including a passing run of the SDK pack contract suite
- Semantic version and health reporting

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

- Platform Kernel interfaces
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

**Dated exception, recorded rather than silently violated (2026-07-28).** The `software-engineering` pack — this contract's own "Highest priority" pack — currently imports `ai_os_kernel.*` internals directly in every one of its agent modules and its pipeline composition (`ai_os_pack_software_engineering.pipeline`), not only through the Platform SDK. **Why:** no `ai-os-sdk` package exists yet (`kernel/pyproject.toml` itself lists it under "Planned, not yet scaffolded") — there is nothing else for a pack to depend on for a real LLM Gateway/Prompt Engine/database connection today, and this pack's own agents need all three to genuinely call a model and persist results. This is a real, live violation of the rule stated above, not a hypothetical one — a fresh reader should not be misled into thinking it is categorically impossible. **What removes it:** a real Platform SDK package (`ai-os-sdk`) exposing the LLM Gateway/Prompt Engine/database access this pack currently reaches through Kernel internals — at that point this pack (and any other) can depend on the SDK instead, and this exception is closed. Tracked in `docs/19_roadmap/implementation_status.md`; each affected module's own docstring records the same compromise at the code level.

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

| Capability Pack                  | Priority | Status   |
|----------------------------------|----------|----------|
| Software Engineering             | Highest  | Planned |
| Existing Project Intelligence    | High     | Planned |
| Voice (Jarvis)                   | High     | Planned |
| Benchmarking                     | Medium   | Planned |
| Future Domain Packs              | Future   | -        |

---

## Validation Checklist

Before activation / installation, verify:

- [ ] Manifest is valid
- [ ] Required contracts are implemented
- [ ] Dependencies are satisfied
- [ ] Tests have passed
- [ ] Documentation is complete
- [ ] Security validation passed
- [ ] Configuration is valid
- [ ] Quality Gates passed
- [ ] No prohibited dependencies exist

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
