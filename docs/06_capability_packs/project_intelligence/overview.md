# Project Intelligence Pack – Overview – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Project Intelligence Pack – Overview  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## Implementation Status (2026-07-28)

**Built: nothing. This document is a design specification only.** `capability_packs/project_intelligence/` has **no tracked content** and is absent from a fresh clone. The `project-intelligence/existing-project-analyzer` agent does not exist, nor do any of the five documented workflows. The Document Processing service this pack depends on for ingestion is also 0% built. Stage E deliverable.

Authoritative, always-current status: the per-module completion table in `feature_inventory.md` and `implementation_status.md`; build history in `history/INDEX.md` (all under `docs/19_roadmap/`).

## 1. Purpose

This document provides the high-level overview of the **Project Intelligence Capability Pack**.

The Project Intelligence Pack enables AI_OS to understand, analyse, document, and help modernize existing software systems — especially legacy or poorly documented codebases. It complements the Software Engineering Pack, which focuses primarily on building new software.

This document is subordinate to:

1. Project Constitution  
2. Capability Pack Contract  
3. System Architecture  
4. Agent Catalog  

---

## 2. Goals of the Pack

The Project Intelligence Pack shall enable AI_OS to:

- Ingest and understand existing codebases
- Reconstruct architecture and design intent from code
- Identify technologies, dependencies, and patterns in use
- Detect technical debt, risks, and modernization opportunities
- Produce high-quality documentation for existing systems
- Support safe enhancement and modernization workflows
- Feed structured knowledge back into the platform’s Knowledge and Memory systems

---

## 3. Scope

### In Scope
- Codebase ingestion and structural analysis
- Architecture recovery
- Dependency and technology discovery
- Documentation generation for existing systems
- Technical debt and risk assessment
- Support for modernization planning
- Interaction with the Existing Project Analysis Agent

### Out of Scope (for this pack)
- Green-field product creation (belongs to Software Engineering Pack)
- Voice interaction
- Domain-specific packs (IoT, Finance, etc.)

---

## 4. Primary Agent

The pack is the primary owner of:

- **Existing Project Analysis Agent** (from the Agent Catalog)

It may also collaborate with agents from the Software Engineering Pack (Architecture, Documentation, Refactoring, Security, Performance, etc.) when modernization or enhancement work is performed.

---

## 5. Key Capabilities (High Level)

- Repository / codebase ingestion
- Language and framework detection
- Module and dependency graph construction
- Architectural view reconstruction
- Identification of entry points, APIs, and data stores
- Generation of documentation and diagrams
- Production of modernization recommendations

---

## 6. Key Workflows (High Level)

- Existing System Analysis Workflow
- Architecture Recovery Workflow
- Documentation Generation Workflow for Legacy Systems
- Modernization Opportunity Assessment Workflow
- Safe Enhancement Workflow (in collaboration with Software Engineering Pack)

---

## 7. Interaction with the Platform

- Declares its agents, tools, and workflows in `manifest.yaml`
- Uses Kernel services (LLM Gateway, Context Manager, Knowledge Manager, Memory Manager, etc.)
- Writes recovered knowledge into the Knowledge Manager / Memory Manager in a structured way
- Must not bypass the Workflow Engine or call LLM providers directly

---

## 8. Current Status

This document provides the high-level overview of the Project Intelligence Pack.

Subsequent documents will detail its agents, workflows, tools, and quality considerations.

---

## 9. Final Authority

Order of precedence:

1. Project Constitution  
2. Capability Pack Contract  
3. Project Intelligence Pack – Overview  
4. Detailed pack documents  
5. Source Code
