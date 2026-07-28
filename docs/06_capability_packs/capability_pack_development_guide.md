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

This guide provides the baseline process for developing Capability Packs.

It will evolve as the Platform SDK and tooling mature.

---

## 11. Final Authority

Order of precedence:

1. Project Constitution  
2. Capability Pack Contract  
3. Manifest Schema  
4. Capability Pack Development Guide  
5. Source Code
