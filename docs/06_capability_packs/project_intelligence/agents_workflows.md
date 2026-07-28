# Project Intelligence Pack – Agents & Workflows – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Project Intelligence Pack – Agents & Workflows  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

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
