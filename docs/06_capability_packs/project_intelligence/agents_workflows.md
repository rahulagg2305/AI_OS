# Project Intelligence Pack – Agents & Workflows – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Project Intelligence Pack – Agents & Workflows  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## Implementation Status (updated 2026-08-09, `P05-S02-M32-T04`)

**Built: four real, non-agent Tools feeding this agent's own future scope, all with real provenance tagging.** `repository.ingest` (`tools.repository_ingestion`, `tier1_sandboxed`) genuinely walks a real repository and returns a real structural model; `language.detect` (`tools.language_detection`, `tier2_trusted`) consumes that output to detect languages/build systems/frameworks with real confidence per finding; `dependency.graph` (`tools.dependency_graph`, back to `tier1_sandboxed` since it reads and parses real file content) consumes the same structural model, filtered to Python, and constructs a real, queryable module/dependency graph via stdlib `ast`; `architecture.recover` (`tools.architecture_recovery`, `tier2_trusted`) consumes that graph and performs real deterministic analysis — module-level boundary aggregation, real circular-dependency detection, real coupling metrics — together, the first four, purely mechanical activities of this document's own §2 "Typical activities: Ingest and structure a codebase" / "Detect languages, frameworks, and platforms" / "Build module and dependency views" / (the mechanical half of) "Recover architectural boundaries and patterns." Every one of the four Tools' outputs now carries a real `trust: "untrusted"` field (`provenance.py`, FR-059) — this pack's own independently-mirrored counterpart to the Context Manager's already-real `ContextItem.trust`, since `ai_os_kernel` cannot be imported here. Deliberately built as Tools, not an Agent: no LLM call is needed for any of these four mechanical operations (a design fork resolved via `AskUserQuestion` each time — `architecture.recover`'s own narrative-documentation half is real, disclosed, deferred work for the eventual Agent). Neither the `existing-project-analyzer` agent itself nor any of the five workflows below exists yet — none of the four Tools is wired into either.

Note also that most of the *supporting* agents these workflows invoke from the Software Engineering pack (`security`, `performance`, `refactoring`, `code-reviewer`) are themselves **not built** — see `../software_engineering/agents.md`'s "Currently Implemented Subset".

Authoritative, always-current status: the per-module completion table in `feature_inventory.md` and `implementation_status.md`; build history in `history/INDEX.md` (all under `docs/19_roadmap/`).

## 1. Purpose

This document defines the Agents and major Workflows of the **Project Intelligence Capability Pack**.

It focuses on understanding, documenting, and supporting the modernization of existing software systems.

This document is subordinate to:

1. Capability Pack Contract  
2. Agent Architecture & Agent Contract  
3. Agent Catalog  
4. Project Intelligence Pack – Overview  
5. Workflow Architecture & Standard Workflow Patterns  

---

## 2. Primary Agent

### Existing Project Analysis Agent

**ID:** `project-intelligence/existing-project-analyzer`

*(v1.0 of this document gave three identifiers for this one agent — `existing-project-analyzer`, `SE-015`, and `PI-001`. The fully qualified form above is the only valid identifier; the other two are withdrawn. This pack is its sole owner.)*

**Primary Responsibility:**  
Understand, analyse, and document existing or legacy codebases. Reconstruct architecture, identify technologies and dependencies, surface risks and technical debt, and produce actionable insights for modernization.

**Typical activities:**
- Ingest and structure a codebase
- Detect languages, frameworks, and platforms
- Build module and dependency views
- Recover architectural boundaries and patterns
- Identify entry points, APIs, data stores, and integration points
- Highlight areas of high complexity or risk
- Generate documentation and modernization recommendations

**Collaboration:**  
This agent frequently collaborates (via the Workflow Engine) with Architecture, Documentation, Security, Performance, and Refactoring agents from the Software Engineering Pack when deeper analysis or follow-on work is required.

---

## 3. Supporting Agents (from Software Engineering Pack)

The following agents are commonly used in Project Intelligence workflows:

- Architecture Agent
- Documentation Agent
- Security Agent
- Performance Agent
- Refactoring Agent
- Code Review Agent

They remain owned by the Software Engineering Pack but participate in workflows defined by the Project Intelligence Pack.

---

## 4. Major Workflows

### 4.1 Existing System Analysis Workflow

**Goal:** Produce a comprehensive understanding of an existing system.

**High-level flow:**
1. Ingest codebase / repository
2. Technology and structure discovery
3. Dependency and module analysis
4. Architecture recovery
5. Risk and technical debt assessment
6. Documentation generation
7. Summary and recommendations

### 4.2 Architecture Recovery Workflow

**Goal:** Reconstruct and document the architecture of an existing system.

**High-level flow:**
1. Structural analysis
2. Component and boundary identification
3. Interaction and dependency mapping
4. Architecture documentation and diagrams
5. Optional Human Approval / review

### 4.3 Legacy Documentation Generation Workflow

**Goal:** Create high-quality documentation for a poorly documented system.

**High-level flow:**
1. Code and structure analysis
2. API and data model extraction
3. Documentation generation
4. Review and refinement

### 4.4 Modernization Opportunity Assessment Workflow

**Goal:** Identify and prioritise modernization opportunities.

**High-level flow:**
1. System analysis
2. Technical debt and risk scoring
3. Opportunity identification
4. Impact and effort estimation
5. Recommendation report

### 4.5 Safe Enhancement Workflow

**Goal:** Make controlled improvements to an existing system (in collaboration with the Software Engineering Pack).

**High-level flow:**
1. Analysis of the target area
2. Change planning
3. Implementation (via Software Engineering agents)
4. Review, testing, and quality gates
5. Documentation update

---

## 5. Common Rules

- All workflows must be declared in the pack’s `manifest.yaml`
- Agents never communicate directly; coordination is performed by the Workflow Engine
- Side effects are performed only through approved Tools
- Recovered knowledge should be written back into the Knowledge Manager / Memory Manager in a structured form
- Full observability is required for every analysis run

---

## 6. Current Status

This document defines the primary agent and major workflows of the Project Intelligence Pack.

Detailed tool requirements, quality gates specific to analysis work, and concrete workflow definitions will be refined during pack development.

---

## 7. Final Authority

Order of precedence:

1. Capability Pack Contract  
2. Project Intelligence Pack – Overview  
3. Project Intelligence Pack – Agents & Workflows  
4. Source Code
