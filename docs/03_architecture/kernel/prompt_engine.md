# Prompt Engine Design – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Prompt Engine Design  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## Implementation Status (2026-07-28; Prompt Resolver correction + Composition/inheritance added 2026-08-05)

**Partially built.** Real: `PromptEngine` Protocol with two implementations — `InMemoryPromptEngine` and `SqlPromptCatalog` (reads `catalog.prompts` by composite `(prompt_id, version)` key) — plus a shared `render_template()` doing variable substitution, and `PromptedCompletionService` composing render→Gateway. **Correction:** the role/alias-based Prompt Resolver is real too (`kernel/src/ai_os_kernel/prompt_engine/resolver.py`'s `PromptResolver`, previously undocumented here) — resolves a role to a bound `(prompt_id, version)` via composition-injected bindings, then renders through any real `PromptEngine`; version pinning is exact-binding only, no "latest"/experiment-driven resolution. **As of `P02-S03-M07-T05`**, prompt composition/inheritance is real too — `composition.py`'s `compose_fragments()`/`compose_with_inheritance()`/`render_composed()`: a pure, in-memory fragment joiner (no new persisted schema — §6's Prompt Contract has no fragment field to build against, and §5 marks this box "optional") layered on the unchanged `render_template()`. Inheritance is a named-fragment-map override (child overrides specific names, inherits the rest from parent, in parent's own key order); an override naming an unknown parent fragment is rejected, not silently accepted or appended.

**Not built:** version *resolution* beyond exact-binding role lookup (nothing resolves "latest" or an experiment-pinned version), the `cache_boundary_index` cache-boundary split ([ADR-0025](../../18_decision_log/adr/ADR-0025-caching-strategy.md)), a persisted fragment catalog (fragments are supplied directly by the caller, not stored/versioned of their own accord), and a dedicated Observability writer. Note the interface path this document's own Current Status section once cited (`platform_sdk/contracts/prompts.py`) **does not exist** — there is no SDK package; the real code is `kernel/src/ai_os_kernel/prompt_engine/`.

Authoritative, always-current status: `../../19_roadmap/feature_inventory.md` and `../../19_roadmap/implementation_status.md`. Build history: `../../19_roadmap/history/INDEX.md`.

## 1. Purpose

This document defines the design of the **Prompt Engine**, a core component of the AI_OS Platform Kernel.

The Prompt Engine is responsible for managing, versioning, rendering, and supplying prompts to the rest of the platform in a controlled, auditable, and configuration-driven manner.

It works in close collaboration with the LLM Gateway. Agents and workflows never construct raw prompts in an uncontrolled way; they request prompts through the Prompt Engine.

This document is subordinate to:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Kernel Architecture  
5. LLM Gateway Architecture  
6. Agent Architecture & Agent Contract  
7. Capability Pack Contract  

---

## 2. Design Goals

The Prompt Engine must:

- Treat prompts as first-class, versioned artifacts
- Prevent hardcoding of prompts inside business logic or agents
- Support prompt templates with clear variables
- Allow prompts to be owned by Capability Packs
- Provide a stable interface for Agents and the Workflow Engine
- Enable A/B testing and multi-LLM experiments with identical prompts
- Be fully observable and auditable
- Remain LLM-agnostic

---

## 3. Core Responsibilities

- Store and version prompts
- Resolve the correct prompt version for a given request
- Render templates with runtime variables
- Validate that required variables are supplied
- Support prompt inheritance / composition where useful
- Expose prompts via a clean interface
- Record which prompt version was used in every LLM call (for traceability and benchmarking)

---

## 4. Key Concepts

### Prompt
A named, versioned artifact that contains the instructions sent to an LLM.

### Prompt Template
A prompt that contains placeholders (variables) that are filled at runtime.

### Prompt Family / Role
Logical grouping (e.g., `code-generation`, `code-review`, `architecture-design`, `requirements-analysis`).

### Prompt Ownership
Prompts are primarily owned by Capability Packs and declared (or referenced) in the pack’s manifest.

---

## 5. High-Level Structure

```text
Prompt Engine
│
├── Prompt Registry
├── Version Manager
├── Template Renderer
├── Variable Validator
├── Prompt Resolver
├── Composition Engine (optional)
└── Observability Hook
```

---

## 6. Prompt Contract (Conceptual)

Every prompt should define:

- id (unique within its pack)
- name
- version (semantic)
- description
- owner (Capability Pack)
- template (the actual content with variables)
- input_schema (expected variables)
- tags / labels
- metadata (model preferences, temperature hints, etc. – optional)

---

## 7. Resolution Flow

1. An Agent or Workflow requests a prompt by ID (or by role/alias).
2. Prompt Engine resolves the correct version (based on configuration or experiment context).
3. Required variables are validated.
4. Template is rendered.
5. Rendered prompt is returned together with metadata (prompt id + version).
6. The caller passes the rendered prompt to the LLM Gateway.
7. The Gateway and Observability layer record which prompt version was used.

---

## 8. Versioning Rules

- Prompts follow Semantic Versioning.
- Breaking changes in prompt behaviour or required variables require a major version bump.
- The platform must be able to pin specific prompt versions for experiments and reproducibility.

---

## 9. Configuration & Overrides

- Default prompt versions can be configured globally or per environment.
- Experiments can force specific prompt versions.
- Capability Packs ship their own prompts; the platform can override or extend them via configuration when necessary.

---

## 10. Observability & Traceability

Every use of a prompt must be traceable:

- Which prompt ID and version was used
- Which workflow / agent requested it
- Which variables were supplied
- Linkage to the subsequent LLM Gateway call

This is essential for debugging and for fair multi-LLM comparisons.

---

## 11. Relationship with Other Components

- **Capability Packs** own and ship prompts.
- **Manifest** declares or references the prompts belonging to a pack.
- **Agents** request prompts; they do not hardcode them.
- **LLM Gateway** receives the final rendered prompt.
- **Evaluation / Experiment Engine** can pin prompt versions for reproducibility.

---

## 12. Storage Format and Cache Boundary

**Storage.** A prompt is a Markdown file in the owning pack at `prompts/<name>.md`, with a variables model referenced from the manifest. Version metadata lives in the manifest entry, not in the file, so the file content is exactly what is rendered. Prompt versions are **immutable**: a change creates a new version. The `catalog.prompts` table records `content_hash` per version, so what was actually sent is verifiable after the fact.

**Templating** uses a restricted, non-executing syntax — variable substitution and simple conditionals only. Arbitrary code in a template would put logic in prompts, which the Governance Framework prohibits.

**Cache boundary.** A rendered prompt returns `cache_boundary_index`, marking the split between the stable prefix (system content, invariant instructions) and the volatile suffix (this step's task and data). The LLM Gateway uses it to place a provider cache breakpoint ([ADR-0025](../../18_decision_log/adr/ADR-0025-caching-strategy.md)). Because provider prompt caching is prefix-matched, prompts must not interpolate timestamps, run IDs, or UUIDs before the boundary — doing so silently destroys the cache hit rate without any visible error.

**Untrusted content** is always placed after the boundary and wrapped in explicit data delimiters by this engine, never concatenated into instruction text.

---

## 13. Current Status

This document defines the Prompt Engine design. Concrete interfaces live in `platform_sdk/contracts/prompts.py`.

---

## 13. Final Authority

Order of precedence:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Kernel Architecture  
5. LLM Gateway Architecture  
6. Prompt Engine Design  
7. Source Code
