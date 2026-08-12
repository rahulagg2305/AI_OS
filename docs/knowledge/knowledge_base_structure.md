# Knowledge Base Structure & Governance – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Knowledge Base Structure & Governance  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## Implementation Status (2026-07-28)

**Built: nothing. This document is a design specification only.** The root `knowledge/` directory and all ten documented subdirectories (`architecture_memory/`, `best_practices/`, `design_patterns/`, `anti_patterns/`, `engineering_memory/`, `lessons_learned/`, `reusable_patterns/`, `reusable_workflows/`, `known_limitations/`, `onboarding/`) have **no tracked content** and are absent from a fresh clone.

Neither of the components that would populate or read it exists: the **Knowledge Manager** and **Memory Manager** are both docstring-only stub packages. A real document/chunk writer and a keyword searcher do exist one layer down in `kernel/src/ai_os_kernel/persistence/`, but nothing calls them and no Context Manager resolver reads from them.

Authoritative, always-current status: the per-module completion table in `feature_inventory.md`; build history in `history/INDEX.md` (all under `docs/19_roadmap/`).

## 1. Purpose

This document defines the structure and governance rules for the **Knowledge Base** in AI_OS.

The Knowledge Base is the durable, organized body of knowledge that the platform (and any LLM working on it) relies on. It includes both platform knowledge and project knowledge and is managed primarily through the Knowledge Manager.

This document is subordinate to:

1. Project Constitution  
2. AI Governance Framework  
3. Knowledge Manager Design  
4. AI Context Pack Strategy  

---

## 2. Design Goals

The Knowledge Base must:

- Remain the authoritative long-term memory of the platform and projects
- Be well-structured and navigable
- Support both human readers and AI Context Pack generation
- Enforce clear ownership and update rules
- Prevent uncontrolled growth and contradiction

---

## 3. High-Level Structure

**This matches the actual repository layout.** v1.0 of this document proposed a `knowledge/platform/…` and `knowledge/projects/…` structure that did not exist on disk and admitted it was "conceptual"; the layout below is the real one, as recorded in `PROJECT_INDEX.md`.

```text
knowledge/
├── architecture_memory/     Architectural decisions and rationale as durable knowledge
├── best_practices/          Proven engineering practices
├── design_patterns/         Reusable design patterns
├── anti_patterns/           Patterns to avoid, with reasons
├── engineering_memory/      What worked, what failed, and why (promoted memory)
├── lessons_learned/         Retrospective findings
├── reusable_patterns/       Concrete reusable solution templates
├── reusable_workflows/      Proven workflow compositions
├── known_limitations/       Documented platform and model limitations
└── onboarding/              Orientation material for humans and models
```

**Project knowledge does not live here.** Per-project requirements, architecture, design, and state are stored under `projects/<project_name>/` and indexed by the Knowledge Manager with `project_id` scoping. Keeping platform knowledge and project knowledge in separate trees prevents one project's content from being retrieved into another's context.

**Authoritative documents are not duplicated here.** The Constitution, architecture documents, and ADRs live in `docs/` and are ingested by the Knowledge Manager from there. This directory holds *derived, durable* knowledge — patterns, lessons, memory — not copies. A copy would create two sources of truth, which the Constitution prohibits.

---

## 4. Governance Rules

### 4.1 Authority
- Documentation in the repository is the primary source of truth.
- The Knowledge Base must not invent facts that are not grounded in approved documents or verified project artifacts.

### 4.2 Ownership
- Platform knowledge is owned by the platform maintainers / architects.
- Project knowledge is owned by the project team (or the agents acting under project workflows).
- Every knowledge area should have a clear owner.

### 4.3 Update Rules
- Knowledge must be updated when the corresponding reality changes (architecture decisions, standards, project state, etc.).
- Significant changes should be traceable (who/what changed it and why).
- Obsolete knowledge must be marked or removed.

### 4.4 Quality Rules
- Prefer clear, concise, structured content.
- Avoid duplication; link to the canonical document when possible.
- Contradictions must be resolved, not left living side by side.

---

## 5. Relationship with Other Components

- **Knowledge Manager** is the runtime system that indexes and retrieves from the Knowledge Base.
- **AI Context Packs** are curated views derived from the Knowledge Base.
- **Context Manager** consumes knowledge at runtime.
- **Documentation process** (and Documentation Agent) is the main way knowledge is written and updated.
- **Traceability Model** links knowledge artifacts to requirements, code, and tests.
- **Memory Manager** complements the Knowledge Base with more experiential / dynamic memory.

---

## 6. Current Status

This document defines the structure and governance rules for the Knowledge Base.

Concrete folder mappings, ownership assignments, and maintenance workflows will be refined as the platform matures.

---

## 7. Final Authority

Order of precedence:

1. Project Constitution  
2. AI Governance Framework  
3. Knowledge Manager Design  
4. Knowledge Base Structure & Governance  
5. Source Code
