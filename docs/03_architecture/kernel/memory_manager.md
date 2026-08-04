# Memory Manager Design – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Memory Manager Design  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## 1. Purpose

This document defines the design of the **Memory Manager**, a core component of the AI_OS Platform Kernel.

The Memory Manager is responsible for storing and retrieving dynamic, experiential, and reusable engineering knowledge that goes beyond static documentation. It complements the Knowledge Manager by handling shorter-term workflow memory, longer-term engineering memory, and proven reusable assets.

This document is subordinate to:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Kernel Architecture  
5. Context Manager Design  
6. Knowledge Manager Design  

---

## Implementation Status (2026-07-28; Memory store added 2026-08-04)

**Built:** `kernel/src/ai_os_kernel/memory_manager/` itself is still a docstring-only `__init__.py`, but one layer down, **as of `P02-S04-M10-T01`**, a real Memory Writer/Retriever slice now exists: `ai_os_kernel.persistence.memory_writer.SqlMemoryStore` — `write_memory()` (real insert into the already-real `knowledge.memory_items` table, `dat­a_model.md` §7) and `query_memories()` (real, structural filtering by `memory_type`/`source_workflow_id`, deterministic order). No schema-authority gap here, unlike two Kernel steps ago (`P02-S03-M08-T10`): the table, its `memory_type` check constraint, and its real FK to `workflow.workflow_instances.workflow_id` already existed, already documented, already migrated (`0029_knowledge_schema`) — this closes the "not even a persistence-layer writer" gap this section used to name. Proven against real Postgres: a real memory item written and read back with its real optional fields (`quality_signal`/`provenance`), filtered correctly by type, and correctly isolated per `source_workflow_id`.

**Not built:** every other element of §5 — no dedicated Workflow Memory Store/Engineering Memory Store/Asset Registry as distinct components (one shared table + store covers all three `memory_type` values today, matching data_model.md §7's own single-table design), no Promotion/Demotion Logic (`promoted_at` is real but write-only-as-``NULL`` from this store — nothing ever sets it), no observability or provenance-*computation* (the `provenance` column is real and write-through, but nothing computes a value for it beyond what a caller already supplies). `MemoryService.write()`, named in §6 as the only mediated write path, does not exist in the Kernel or in the Platform SDK (`../platform/platform_sdk.md` §5.5 specifies the Protocol; `platform_sdk/` contains only `schemas/manifest.schema.json`) — `SqlMemoryStore` is a lower-level persistence boundary beneath where that Protocol would sit, the identical relationship `SqlKnowledgeWriter` has to a not-yet-real Knowledge Manager Protocol. §6's "Memory is consumed through the Context Manager" remains structurally true only because there is nothing to consume — `kernel/src/ai_os_kernel/context_manager/resolvers.py` has no Memory Resolver yet. Note that §3.1's "Workflow Memory" partly overlaps something that *is* real but is **not** this component: the Workflow Engine persists step outputs in `workflow.workflow_steps.outputs`, and `WorkflowStepOutputResolver` gives a later step awareness of an earlier step's output (`context_manager.md` §4). That is workflow *state*, owned by the Workflow Engine — it is not memory, is not promotable, and carries no quality or confidence signals. Roadmap stage: **B**.

Authoritative, always-current status: `../../19_roadmap/feature_inventory.md` (per-module completion table) and `../../19_roadmap/implementation_status.md`. Detailed build history: `../../19_roadmap/history/INDEX.md`.

---

## 2. Design Goals

The Memory Manager must:

- Capture useful engineering experience and outcomes
- Support both short-lived (workflow) and long-lived (engineering) memory
- Enable reuse of proven solutions and patterns
- Remain domain-agnostic at the Kernel level
- Provide clean interfaces to the Context Manager
- Be fully observable and auditable
- Avoid becoming an uncontrolled dumping ground

---

## 3. Types of Memory

### 3.1 Workflow Memory
- Temporary state and intermediate results related to a running workflow
- Exists primarily for the duration of the workflow (or a defined retention period)
- Used to give later steps awareness of earlier decisions and outputs

### 3.2 Engineering Memory
- Longer-term records of what worked well, what failed, and why
- Proven code patterns, module designs, successful prompts, architectural choices
- Lessons learned from previous projects or experiments

### 3.3 Reusable Assets
- Concrete, reusable artifacts (e.g., well-tested modules, templates, configurations)
- Can be retrieved and adapted by agents in future work

---

## 4. Core Responsibilities

- Store memory items with clear metadata (source, timestamp, workflow/experiment ID, quality signals)
- Support efficient retrieval by the Context Manager
- Allow memory items to be promoted from workflow memory to engineering memory
- Support decay or archival of low-value memory
- Maintain provenance and linkage to the originating workflow or decision

---

## 5. High-Level Structure

```text
Memory Manager
│
├── Workflow Memory Store
├── Engineering Memory Store
├── Asset Registry
├── Memory Writer
├── Memory Retriever
├── Promotion / Demotion Logic
└── Observability & Provenance
```

---

## 6. Key Design Rules

- **Memory never overrides authoritative documentation.** Knowledge (the Knowledge Manager and repository docs) ranks higher; where they conflict, Knowledge wins. The authority hierarchy is defined in `../../20_glossary/glossary.md` §3, which is the single authority for the Knowledge / Memory / Context / Context Pack distinction.
- Memory items carry quality and confidence signals where available.
- Agents do not write arbitrary memory; writing is mediated and structured through `MemoryService.write()`.
- **Memory is consumed through the Context Manager**, not queried directly by an agent — the same rule that applies to Knowledge.
- Retrieval must be explainable: why a particular item surfaced.

### 6.1 Scope for v1

Workflow memory and explicit engineering-memory writes are **in scope for v1**. **Automatic promotion from workflow memory to engineering memory, decay scoring, and archival are deferred** until there is real usage data to calibrate them — a promotion heuristic invented before any workflows have run would be a guess encoded as architecture. Promotion in v1 is an explicit, audited operation.

*Correction (2026-07-28): earlier revisions of this paragraph read "Workflow memory and explicit engineering-memory writes are implemented." They are not — nothing in this component is implemented (see Implementation Status above). The sentence stated v1 scope, not built state, and now says so.*

---

## 7. Relationship with Other Components

- **Context Manager** is the primary consumer of memory.
- **Knowledge Manager** holds stable, documented knowledge; Memory Manager holds more experiential knowledge.
- **Workflow Engine** can signal important outcomes that should be written to memory.
- **Evaluation / Experiment Engine** can use memory of previous runs to improve future experiments.
- **Capability Packs** may contribute reusable assets through controlled interfaces.

---

## 8. Observability Requirements

Every significant memory operation should record:

- What was written or retrieved
- Source workflow / agent / experiment
- Reason for retrieval (when applicable)
- Timestamp and identifiers

---

## 9. Current Status

This document defines the design baseline for the Memory Manager. The four items v1.0 of this section deferred are settled as follows — none is left open as "to be refined."

| Item | Status |
|---|---|
| **Storage models** | **Decided.** PostgreSQL, SQLAlchemy Core, Alembic ([ADR-0011](../../18_decision_log/adr/ADR-0011-persistence-and-workflow-state.md)), in the `knowledge.memory_items` table — which already exists in `kernel/src/ai_os_kernel/persistence/knowledge_schema.py` and is specified in `../../08_database/data_model.md` §7, including its `source_workflow_id` provenance link. Retrieval mechanics are fixed by [ADR-0013](../../18_decision_log/adr/ADR-0013-search-and-vector-store.md), the same keyword + `pgvector` + RRF path Knowledge uses; memory is not to get its own search stack. |
| **Retention policies** | **Decided at the platform level.** Retention is configurable per environment and governed by `../../08_database/data_model.md` §11, not by a memory-specific policy. §6.1 above deliberately defers decay scoring and archival, so retention for v1 means "kept" — there is no expiry job to design. |
| **Promotion criteria** | **Decided by §6.1, and the decision is to keep it manual.** Promotion in v1 is an explicit, audited operation; automatic promotion is deferred until real usage data exists to calibrate it. This is a settled position, not an open question — the *reason* for deferral is itself the decision. **Named remaining gap:** who is authorized to promote. [ADR-0023](../../18_decision_log/adr/ADR-0023-identity-roles-and-permissions.md)'s closed permission vocabulary has no memory-promotion permission, and §6 forbids agents from writing arbitrary memory, so "explicit and audited" currently has no principal, no permission, and no audit destination (`governance.audit_log` has no writer). That triple is what a first increment must settle. |
| **APIs** | **Decided in specification, unbuilt.** The pack-facing surface is `MemoryService` in `../platform/platform_sdk.md` §5.5, with `write()` as the sole mediated write path (§6); reads reach agents only through the Context Manager, never directly (§7, `context_manager.md` §7). **Named remaining gap:** neither the SDK Protocol nor a Kernel implementation exists, and there is no Memory Resolver in the Context Manager to read through — so both ends of the documented path are missing. Note the ordering constraint: building a writer before a resolver would produce §2's "uncontrolled dumping ground" with no consumer to justify any of it. |

---

## 10. Final Authority

Order of precedence:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Kernel Architecture  
5. Memory Manager Design  
6. Source Code

---

## 11. Related Documents

**Governing decisions (ADRs):**
- [ADR-0011 — Persistence and Workflow State](../../18_decision_log/adr/ADR-0011-persistence-and-workflow-state.md) — the storage substrate
- [ADR-0013 — Search and Vector Store](../../18_decision_log/adr/ADR-0013-search-and-vector-store.md) — how memory will be retrieved
- [ADR-0023 — Identity, Roles and Permissions](../../18_decision_log/adr/ADR-0023-identity-roles-and-permissions.md) — who may write or promote
- [ADR-0022 — Reproducibility over Determinism](../../18_decision_log/adr/ADR-0022-reproducibility-over-determinism.md) — why memory reads must be pinnable for experiments
- [ADR-0005 — Agents Never Communicate Directly](../../18_decision_log/adr/ADR-0005-agents-never-communicate-directly.md) — memory is not a side channel between agents

**Superior documents:**
- `../platform/system_architecture.md`
- `kernel_architecture.md`
- `context_manager.md` — the **only** legitimate consumer
- `knowledge_manager.md` — the higher-authority counterpart; §3 there defines the boundary by authority and lifetime

**Interacting subsystems:**
- `workflow_engine.md` — signals outcomes worth remembering; also owns `workflow.workflow_steps.outputs`, which is state, not memory
- `../services/search_vector_search.md` — the Retrieval component that will query memory
- `evaluation_engine.md` — may use memory of prior runs; must be able to pin it for fair comparison
- `../platform/platform_sdk.md` §5.5 `MemoryService` — the pack-facing Protocol (specified, not built)
- `../../knowledge/knowledge_base_structure.md` — `engineering_memory/`, `lessons_learned/`, `reusable_patterns/` directories
- `security_manager.md` — the permission and audit requirements for promotion
- `observability.md` — §8's memory-operation records

**Owned tables:**
- `../../08_database/data_model.md` §7 — `knowledge.memory_items` (real writer + structural reader as of `P02-S04-M10-T01`, `ai_os_kernel.persistence.memory_writer.SqlMemoryStore`), §11 for retention

**Reference:**
- `../../20_glossary/glossary.md` §3 — the single authority for the Knowledge / Memory / Context / Context Pack distinction
- `../../19_roadmap/feature_inventory.md`, `../../19_roadmap/implementation_status.md`, `../../19_roadmap/history/INDEX.md`
