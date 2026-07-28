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

- Discover packs by **entry point** (`ai_os.capability_packs`, the production mechanism) and by **filesystem scan** of configured directories (the development mechanism) — both validated identically ([ADR-0009](../../18_decision_log/adr/ADR-0009-packaging-and-dependency-management.md))
- Load and parse `manifest.yaml`
- Validate against **`platform_sdk/schemas/manifest.schema.json`** — the authoritative machine-readable schema — plus the 20 semantic rules in `../capability_framework/manifest_schema.md`
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
- Registration makes components visible to the Workflow Engine, Agent Invoker, Tool Invoker, etc., but does not automatically activate them (activation is handled by the Capability Manager and configuration).

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

This document defines the design baseline for the Plugin / Manifest Loader.

Detailed discovery mechanisms, validation implementation, and registration APIs will be refined during development.

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
