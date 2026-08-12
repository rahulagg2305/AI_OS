# Standard AI Context Pack Structure – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Standard AI Context Pack Structure  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## Implementation Status (2026-07-28)

**Built: nothing. This document is a design specification only.** The root `ai_context/` directory and every subdirectory documented below (`platform/`, `kernel/`, `agents/`, `capability_packs/`, `services/`, `projects/`, `releases/`, `summaries/`) have **no tracked content** — no `manifest.yaml`, no pack, nothing. They are absent from a fresh clone.

No code reads this structure: the Context Manager has no AI Context Pack resolver. Strategy and rationale: `ai_context_strategy.md`.

Authoritative, always-current status: the per-module completion table in `feature_inventory.md`; build history in `history/INDEX.md` (all under `docs/19_roadmap/`).

## 1. Purpose

This document defines the standard structure and format for **AI Context Packs** in AI_OS.

A consistent structure makes context packs easier to create, maintain, version, and load by the Context Manager and by any LLM.

This document is subordinate to:

1. AI Context Pack Strategy  
2. Context Manager Design  
3. Knowledge Manager Design  

---

## 2. Design Goals

The standard structure must:

- Be simple and consistent
- Support both platform-level and project-level packs
- Make the most important information easy to find
- Support versioning
- Be usable by both humans and machines

---

## 3. Recommended Directory / File Structure

Context Packs live in **`ai_context/`**, which is the directory that actually exists in the repository and is documented in `PROJECT_INDEX.md`. (v1.0 of this document specified a `context_packs/` directory that does not exist — the path is corrected here.)

```text
ai_context/
├── platform/                   Platform-wide packs
│   └── <pack_name>/
│       ├── manifest.yaml       identity, version, type, priority
│       ├── README.md           human-oriented overview
│       ├── 00_invariants.md    non-negotiable rules
│       ├── 01_architecture.md  essential architecture context
│       ├── 02_standards.md     coding / engineering standards highlights
│       ├── 03_current_state.md current status and open decisions
│       ├── 04_task_guidance.md optional role/task guidance
│       └── assets/             optional diagrams
├── kernel/                     Kernel-subsystem packs
├── agents/                     Per-agent role packs
├── capability_packs/           Per-pack packs
├── services/                   Per-service packs
├── projects/                   Per-generated-project packs
├── releases/                   Release-scoped snapshots
└── summaries/                  Condensed cross-cutting summaries
```

Not every pack needs every file. Platform packs emphasise invariants and architecture; project packs emphasise current state.

---

## 4. Manifest Fields (Conceptual)

```yaml
id: string
name: string
version: string
type: platform | project | task
description: string
applies_to: []          # optional filters (agents, workflows, projects)
priority: number        # relative importance when assembling context
```

---

## 5. Content Guidelines

### 5.1 Invariants (`00_invariants.md`)
- Rules that must never be violated
- Drawn from Constitution, Governance, Architecture, and Coding Standards
- Short and emphatic

### 5.2 Architecture (`01_architecture.md`)
- Only the essential architecture the model must know
- Key components and their responsibilities
- Critical interaction rules (e.g., LLM Gateway, no direct agent communication)

### 5.3 Standards (`02_standards.md`)
- Most important coding and engineering standards
- Prefer concrete rules over long explanations

### 5.4 Current State (`03_current_state.md`)
- Especially important for project packs
- What has been decided, what is in progress, what is blocked
- Keep updated

### 5.5 Task Guidance (`04_task_guidance.md`)
- Optional
- Specific guidance for a role or task type

---

## 6. Assembly Rules

- The Context Manager selects and composes context packs based on the current agent, workflow step, project, and experiment.
- Higher-priority and more specific packs can override or refine more general ones when necessary.
- The total assembled context must respect token budgets; packs should be written with selectivity in mind.

---

## 7. Versioning & Maintenance

- Every context pack must have a version.
- Significant changes to content require a version bump.
- Obsolete content must be removed or clearly marked.
- Platform context packs must be updated when major architectural or governance decisions change.

---

## 8. Current Status

This document defines the standard structure for AI Context Packs.

Concrete platform and project context packs will be created using this structure.

---

## 9. Final Authority

Order of precedence:

1. AI Context Pack Strategy  
2. Standard AI Context Pack Structure  
3. Individual context pack instances  
4. Source Code
