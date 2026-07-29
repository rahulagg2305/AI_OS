# Capability Pack Development Guide – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Capability Pack Development Guide  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## 1. Purpose

This document provides practical guidance for developing new Capability Packs for AI_OS.

It helps developers and AI models create packs that comply with the Capability Pack Contract, Manifest Schema, and platform architecture so that packs can be safely discovered, loaded, activated, and used.

This document is subordinate to:

1. Project Constitution  
2. Capability Pack Contract  
3. Manifest Schema  
4. Kernel Architecture  
5. Coding Standards & Best Practices  

---

## Implementation Status (2026-07-28)

**The platform mechanics this guide assumes are real; one is not.** Verified against `kernel/src/ai_os_kernel/`: the Manifest Loader (`manifest_loader/loader.py`) and Capability Manager (`capability_manager/` — `SqlPackLifecycleRepository`, `PackRegistration`, `HealthReport`, the `CapabilityPack` Protocol) both exist and are real, so §5's "the Manifest Loader will reject packs with invalid or incomplete manifests" and §3 step 13's "register and test activation" are accurate. **§2's "depend only on published Kernel interfaces and the Platform SDK" is not achievable today** — there is no Platform SDK (`ai-os-sdk`) package; the one real pack (Software Engineering) imports Kernel internals directly, a documented exception (`../03_architecture/capability_framework/capability_pack_contract.md`).

**🛑 This guide's own practical relevance is currently gated**: per the hard blocker recorded 2026-07-28 (`../process/standing_rules.md`), no new agent may be added to any Capability Pack and no new Capability Pack may be added until the Platform SDK exists — so a developer reading this guide today to build a *new* pack or a *sixth* SE-pack agent is out of scope regardless of how well they follow it. The guide remains accurate for maintaining the existing, grandfathered Software Engineering pack.

**§4 Mandatory Artifacts is satisfied by the real pack**: `capability_packs/software-engineering/` has `manifest.yaml`, `README.md`, `CHANGELOG.md`, agent implementations, workflow definitions, and tests — matching this checklist exactly.

Authoritative, always-current status: `../19_roadmap/feature_inventory.md` (module 27, Platform SDK; module 29, SE Pack) and `../19_roadmap/implementation_status.md`.

---

## 2. Development Principles

When creating a Capability Pack you must:

- Keep the pack independent and isolated
- Depend only on published Kernel interfaces and the Platform SDK
- Declare everything important in `manifest.yaml`
- Never call LLM providers directly
- Never allow agents to communicate directly with each other
- Follow interface-driven and configuration-driven design
- Make the pack observable and auditable
- Provide tests and documentation

---

## 3. Recommended Development Steps

1. **Define the purpose and scope** of the pack
2. **Identify the agents** the pack will own
3. **Identify the workflows** the pack will provide
4. **Identify the tools** the pack needs
5. **Identify Quality Gates** specific to the pack
6. **Create the pack directory structure** (see Capability Pack Contract)
7. **Write the `manifest.yaml`** according to the Manifest Schema
8. **Implement agents, tools, and workflows** against Kernel interfaces
9. **Add prompts** (versioned, managed via Prompt Engine)
10. **Write tests** (unit, contract, workflow)
11. **Write documentation** (README, architecture notes, usage guide)
12. **Validate** the pack against the Manifest Schema and Contract
13. **Register and test** activation through the Manifest Loader and Capability Manager

---

## 4. Mandatory Artifacts

Every pack must contain at least:

- `manifest.yaml`
- `README.md`
- `CHANGELOG.md`
- Agent implementations / definitions
- Workflow definitions
- Tool definitions (if any)
- Tests
- Documentation

---

## 5. Manifest First

Treat the manifest as the single source of truth for what the pack provides.

The Manifest Loader will reject packs with invalid or incomplete manifests.  
Do not rely on implicit discovery of components that are not declared.

---

## 6. Interaction Rules (Reminder)

- Use the LLM Gateway for all model calls
- Use the Workflow Engine for all orchestration
- Use approved Tools for side effects
- Use the Context Manager for context assembly
- Respect Human Approval Points and Quality Gates
- Emit proper telemetry

---

## 7. Versioning & Compatibility

- Follow Semantic Versioning for the pack
- Declare `minKernelVersion` (and optionally `maxKernelVersion`)
- Avoid breaking changes in contracts without a major version bump
- Document migration notes in the CHANGELOG when necessary

---

## 8. Testing Expectations

A high-quality pack should include:

- Unit tests for core logic
- Contract tests (against declared interfaces)
- Workflow tests
- Integration tests with the Kernel (where practical)
- Regression tests for critical behaviour

---

## 9. Documentation Expectations

Minimum documentation:

- Purpose and scope of the pack
- List of agents and their responsibilities
- List of workflows and when to use them
- Configuration options
- Known limitations
- CHANGELOG

---

## 10. Current Status

This guide provides the baseline process for developing Capability Packs. See the Implementation Status section near the top: the Manifest Loader and Capability Manager it assumes are real, and the Platform SDK is now real and fully adopted by the one real pack (`platform_sdk_v1_scope.md` step 14, 2026-07-29) — the Platform SDK growth gate that used to block any *new* pack or agent from being built by following this guide is lifted (`docs/process/standing_rules.md`).

It will evolve as the Platform SDK and tooling mature.

---

## 11. Final Authority

Order of precedence:

1. Project Constitution  
2. Capability Pack Contract  
3. Manifest Schema  
4. Capability Pack Development Guide  
5. Source Code

---

## 12. Related Documents

- [`../03_architecture/capability_framework/capability_pack_contract.md`](../03_architecture/capability_framework/capability_pack_contract.md) — the contract this guide operationalizes, and the Platform SDK growth gate's primary home
- [`../process/standing_rules.md`](../process/standing_rules.md) — the hard blocker gating any new pack/agent this guide would otherwise help build
- [`software_engineering/overview.md`](software_engineering/overview.md) · [`software_engineering/agents.md`](software_engineering/agents.md) · [`software_engineering/workflows.md`](software_engineering/workflows.md) — the one real pack built against this guide
- [`../19_roadmap/feature_inventory.md`](../19_roadmap/feature_inventory.md) · [`../19_roadmap/implementation_status.md`](../19_roadmap/implementation_status.md) — live build status
