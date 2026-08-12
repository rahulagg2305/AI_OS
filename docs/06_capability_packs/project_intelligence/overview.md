# Project Intelligence Pack – Overview – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Project Intelligence Pack – Overview  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## Implementation Status (updated 2026-08-11, `P05-S02-M32-T07`)

**Updated 2026-08-11 (`P05-S02-M32-T07`): the pack's five real Tools are now manifest-declared, discoverable, and registry-resolvable.** A real, schema-valid `manifest.yaml` declares all five (`repository.ingest`, `language.detect`, `dependency.graph`, `architecture.recover`, `documentation.generate`), so the Manifest Loader genuinely discovers, registers, and resolves them; a declared Tool is now invocable through the real `SqlToolRegistry` (proven end to end), closing the "not yet manifest-declared" gap the block below still names. Deliberately no `pack.py`/`entryPoint` — the schema requires one only for a pack declaring agents or workflows, and this pack declares only tools. **Note: the paragraph below is itself older, `P05-S02-M32-T01`-dated staleness that this step did not fully rewrite — it says "one real Tool" when five Tools plus real `trust:"untrusted"` provenance (`P05-S02-M32-T02`..`T06`) now exist; see `../../19_roadmap/feature_inventory.md` module 32 for the always-current state.** The `existing-project-analyzer` agent and the five documented workflows do remain unbuilt.

**Built: the pack now exists, with one real Tool.** `capability_packs/project_intelligence/` was scaffolded (the Capability Pack growth gate is lifted, per CLAUDE.md) with one real, manifest-declarable Tool, `repository.ingest` (FR-050): walks a real repository directory inside a real, ephemeral `tier1_sandboxed` container and returns a real file/module inventory. ADR-0016's own Decision text is unconditional that repository-content-processing tools are Tier 1 — an early, incorrect Tier-2 framing was caught and corrected via `AskUserQuestion` before any code was written. Proven end to end against a real Docker daemon. Not yet manifest-declared or wired into any agent/workflow — a real, disclosed, deferred step, not an oversight. The `project-intelligence/existing-project-analyzer` agent still does not exist, nor do any of the five documented workflows. The Document Processing service this pack depends on for ingestion is now 40% built (Markdown/Plain Text/Code parsers real; PDF/DOCX deferred).

Authoritative, always-current status: the per-module completion table in `feature_inventory.md`; build history in `history/INDEX.md` (all under `docs/19_roadmap/`).

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
