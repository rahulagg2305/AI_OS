# Software Engineering Pack – Overview – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Software Engineering Pack – Overview  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-30 (a 6th agent, `lint`, is now real — 6 of 17, not 5 of 16 — and the growth gate is recorded as lifted, not blocked; matching `agents.md`'s own same-day update. Prior, same day: corrected a stale "5 of 15"/"the other 10" agent count to "5 of 16"/"the other 11", matching `agents.md`'s own already-corrected 2026-07-28 header. Prior: 2026-07-25)

---

## 1. Purpose

This document provides the high-level overview of the **Software Engineering Capability Pack**.

The Software Engineering Pack is the primary Capability Pack of AI_OS. It enables the platform to perform autonomous (and human-governed) software engineering tasks: turning structured requirements into production-grade software, improving existing code, and maintaining high engineering standards.

This document is subordinate to:

1. Project Constitution  
2. Capability Pack Contract  
3. System Architecture  
4. Agent Catalog  

---

## Implementation Status (2026-07-30)

**A small, real slice exists inside the much larger design this document describes.** Per `agents.md`'s own "Currently Implemented Subset": **6 of the 17 agents listed in §4 are real** (`requirements-analyst`, `architecture`, `build`, `lint` — neither in §4's original 15-agent list, `build` added 2026-07-28, `lint` added 2026-07-30, which is what makes the denominator 17 rather than 15 — `qa-test`, `documentation`); the other 11 (`technical-planner`, `backend-developer`, `frontend-developer`, `database`, `api-designer`, `devops`, `security`, `code-reviewer`, `release`, `refactoring`, `performance`) have no code. Per `workflows.md`'s own "Currently Implemented Subset": **1 of §5's 6 listed workflow categories is real** — `se.delivery_pipeline`, now a 6-agent, 2-quality-gate pipeline, not an implementation of any of §5's named workflows. §6's Quality Gates are declared as a specification (`tools_quality_gates.md`); the Quality Gate Engine itself remains largely unbuilt (7%), but two real, narrow gate instances now exist inside this pipeline — see `../../03_architecture/kernel/quality_gate_engine.md`.

**✅ The Capability Pack growth gate is lifted** (product-owner decision, 2026-07-29, `../../process/standing_rules.md`) — `lint` (2026-07-30) is the first agent added to this pack since the gate lifted, proving growth genuinely works, not merely permitted on paper.

**§7's "must not call LLM providers directly or bypass the Workflow Engine" is upheld** — all 6 real agents are invoked exclusively through the Workflow Engine's `AgentStepExecutor`, and the 4 `PromptedAgent`-backed ones (`qa-test`/`lint` are the exceptions, making no LLM call at all) go through the real LLM Gateway.

Authoritative, always-current status: `../../19_roadmap/feature_inventory.md` (module 29) and `../../19_roadmap/implementation_status.md`.

---

## 2. Goals of the Pack

The Software Engineering Pack shall enable AI_OS to:

- Create complete software products from structured specifications
- Implement backend, frontend, database, and infrastructure components
- Maintain high code quality through review, testing, and quality gates
- Support iterative improvement and refactoring
- Produce documentation and release artifacts
- Integrate with the multi-LLM experimentation and evaluation capabilities of the platform

---

## 3. Scope

### In Scope
- Requirements analysis and refinement
- Architecture and technical planning
- Backend and frontend development
- Database design and access
- API design
- Testing and quality assurance
- Code review and refactoring
- Security analysis
- DevOps and deployment configuration
- Documentation and release management
- Performance analysis

### Out of Scope (for this pack)
- Deep legacy system reverse-engineering (belongs primarily to Project Intelligence Pack)
- Domain-specific packs (IoT, Finance, etc.)
- Voice interaction (belongs to Voice / Jarvis Pack)

---

## 4. Owned Agents

This pack owns (or is the primary owner of) the following agents from the Agent Catalog:

- Requirements Analyst Agent
- Architecture Agent
- Technical Planning Agent
- Backend Development Agent
- Frontend Development Agent
- Database Agent
- API Design Agent
- DevOps Agent
- Security Agent
- QA / Test Engineer Agent
- Code Review Agent
- Documentation Agent
- Release Agent
- Refactoring Agent
- Performance Agent

---

## 5. Key Workflows (High Level)

The pack will provide at least the following major workflows:

- Full Product Creation Workflow
- Feature Addition Workflow
- Bug Fix / Maintenance Workflow
- Refactoring Workflow
- Code Review & Quality Improvement Workflow
- Release Workflow

These workflows will compose the standard patterns defined in the Workflow Patterns document (Sequential, Parallel, Request–Review–Revise, Quality Gate Pipeline, Human-in-the-Loop, etc.).

---

## 6. Quality Gates

The pack will contribute and require a strong set of Quality Gates, including:

- Build success
- Unit and integration tests passing
- Minimum coverage thresholds
- Linting and static analysis
- Security scanning
- Architecture compliance
- Documentation completeness

---

## 7. Interaction with the Platform

- All agents and workflows are declared in the pack’s `manifest.yaml`.
- The pack uses the LLM Gateway, Context Manager, Knowledge Manager, Memory Manager, and Quality Gate Engine provided by the Kernel.
- The pack must not call LLM providers directly or bypass the Workflow Engine.

---

## 8. Current Status

This document provides the high-level overview. See the Implementation Status section near the top for the real vs. designed gap: 6 of 17 agents, 1 proof-of-concept workflow of 6 documented categories.

Subsequent documents detail:

- Agents of this pack (`agents.md`)
- Workflows of this pack (`workflows.md`)
- Tools and Quality Gates of this pack (`tools_quality_gates.md`)

---

## 9. Final Authority

Order of precedence:

1. Project Constitution  
2. Capability Pack Contract  
3. Software Engineering Pack – Overview  
4. Detailed pack documents  
5. Source Code

---

## 10. Related Documents

- [`agents.md`](agents.md) · [`workflows.md`](workflows.md) — the detailed catalogs, each with its own "Currently Implemented Subset" section
- [`../../03_architecture/capability_framework/capability_pack_contract.md`](../../03_architecture/capability_framework/capability_pack_contract.md) — the Platform SDK growth gate that used to block this pack's further expansion, now lifted (this pack is fully SDK-compliant, step 14)
- [`../../process/standing_rules.md`](../../process/standing_rules.md) — the standing rule recording the gate's lift
- [`../../19_roadmap/feature_inventory.md`](../../19_roadmap/feature_inventory.md) · [`../../19_roadmap/implementation_status.md`](../../19_roadmap/implementation_status.md) — live build status
