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

## Implementation Status (2026-07-28; Memory store added 2026-08-04; `MemoryService` and computed provenance added 2026-08-14)

**Updated 2026-08-14 (`P02-S04-M10-T04`) — this package has real code of its own for the first time.** `ai_os_kernel.memory_manager.service.MemoryService` implements §6's `MemoryService.write()`, the **only mediated write path**, over the unchanged `SqlMemoryStore`. Three things it genuinely adds beyond the store beneath it: (1) **structure** — `MemoryWrite` is a frozen, `extra="forbid"` boundary model with no `promoted_at` and no `memory_id` field, so §5.5's "promotion is a platform decision, not a pack decision" is enforced by the type rather than by a runtime check, and an attempted `promoted_at=…` is a loud error rather than a silently ignored one; (2) **§8's observability requirements, which had no producer at all** — a real `memory.written` structured event carrying identity, source workflow and provenance presence, plus a real `aios.memory.writes` counter, both guarded so a telemetry outage can never fail a write that already committed, and deliberately **never logging the memory body** (it can be arbitrarily large and arbitrarily sensitive; §8 asks for identity, not payload); (3) **a narrower return** — §5.5's `MemoryRef`, not the full persistence row. Proven by 14 unit tests against a real fake store (ADR-0004) and 4 real-Postgres tests that run the actually-produced path end to end, including one asserting the committed `promoted_at` column is genuinely `NULL` and one proving a written item is genuinely visible to the real `MemoryResolver`.

**Updated 2026-08-14 (`P02-S04-M10-T05`) — `provenance` is now computed, not asserted.** The column was write-through: a caller could supply any value it liked, including none, so it was decorative. `MemoryWrite` no longer has a `provenance` field at all; `MemoryService` composes the record itself, and the module states plainly which parts are trustworthy rather than presenting them uniformly. **Verified:** `workflowId` — `source_workflow_id` is a real FK, so Postgres refuses a workflow that does not exist. **Computed, caller cannot influence:** `recordedAt` (platform clock), `recordedBy` (this module's identity), `trust` (a constant `"untrusted"` — ADR-0016 control 1, and exactly what `MemoryResolver` already asserts for every memory item; a parameter would let a caller misrepresent provenance, the identical reasoning the Project Intelligence pack's `DERIVED_CONTENT_TRUST` states), and `schemaVersion` (present from the first row, so a later shape change is a migration rather than archaeology — `OUTBOX_SCHEMA_VERSION`'s own reasoning). **Declared, and the weakest field in the record:** `stepId`/`agentId` are stated by the writer and nothing cross-checks them today; they are recorded because they are §4's own "provenance and linkage to the originating workflow or decision" and dropping them would lose real information, but a future step with a real `SecurityContext` at this call site could verify them. Proven by 5 unit tests and a real-Postgres test asserting the composed record survives the `jsonb` round trip intact.

**Three deliberate absences, each with a reason on the record.** `recall()` (§5.5 specifies it) is **not** built: §6 and §7 both state memory is consumed through the Context Manager, and `MemoryResolver` already does that for real — a second read path would have no consumer. The **SDK Protocol** is not built: `../platform/platform_sdk_v1_scope.md` §7 lists `MemoryService` among ten Protocols explicitly deferred past v1.0.0, so Kernel-local is the decided answer, not an open choice. And there is still **no production caller** — nothing writes memory in production, because no document decides the trigger, the content, or the `memory_type`; §7 says only that the Workflow Engine "*can* signal important outcomes". Inventing that trigger would be §6.1's own named error. Product-owner decision, 2026-08-14: build the service, wire nothing. **This means `MemoryResolver`, wired unconditionally in `bootstrap.py` over `memory_type="engineering"`, still reads a table that production never populates** — a real, disclosed gap, now on the write side alone rather than both sides.

**Built:** `kernel/src/ai_os_kernel/memory_manager/` itself is still a docstring-only `__init__.py`, but one layer down, **as of `P02-S04-M10-T01`**, a real Memory Writer/Retriever slice now exists: `ai_os_kernel.persistence.memory_writer.SqlMemoryStore` — `write_memory()` (real insert into the already-real `knowledge.memory_items` table, `dat­a_model.md` §7) and `query_memories()` (real, structural filtering by `memory_type`/`source_workflow_id`, deterministic order). No schema-authority gap here, unlike two Kernel steps ago (`P02-S03-M08-T10`): the table, its `memory_type` check constraint, and its real FK to `workflow.workflow_instances.workflow_id` already existed, already documented, already migrated (`0029_knowledge_schema`) — this closes the "not even a persistence-layer writer" gap this section used to name. Proven against real Postgres: a real memory item written and read back with its real optional fields (`quality_signal`/`provenance`), filtered correctly by type, and correctly isolated per `source_workflow_id`.

**Not built:** every other element of §5 — no dedicated Workflow Memory Store/Engineering Memory Store/Asset Registry as distinct components (one shared table + store covers all three `memory_type` values today, matching data_model.md §7's own single-table design), no Promotion/Demotion Logic (`promoted_at` is real but write-only-as-``NULL`` from this store — nothing ever sets it), **(both of these closed 2026-08-14 — see the two update paragraphs above: `MemoryService` gave §8 its first real producer, and `provenance` is now composed by the platform rather than supplied by the caller)** ~~no observability or provenance-*computation*~~. `MemoryService.write()`, named in §6 as the only mediated write path, does not exist in the Kernel or in the Platform SDK (`../platform/platform_sdk.md` §5.5 specifies the Protocol; `platform_sdk/` contains only `schemas/manifest.schema.json`) — `SqlMemoryStore` is a lower-level persistence boundary beneath where that Protocol would sit, the identical relationship `SqlKnowledgeWriter` has to a not-yet-real Knowledge Manager Protocol. **Updated 2026-08-04 (`P02-S03-M08-T06`):** §6's "Memory is consumed through the Context Manager" is now genuinely real for reads — `kernel/src/ai_os_kernel/context_manager/resolvers.py`'s `MemoryResolver` calls `SqlMemoryStore` directly, cross-run (deliberately not filtered by `source_workflow_id`, matching this store's own "durable... cross-run" Goal), with a caller-configured `memory_type`. Proven end to end against real Postgres: a real memory item written under one workflow surfaces in a real context assembly for a different one, and a real three-source assembly (Workflow State, Knowledge, Memory) genuinely confirms Knowledge outranks Memory with real, differing scores — still only because `quality_signal` is never yet computed above `0.0`, not because authority is explicitly enforced as a rule (see `context_manager.md`'s own "Ranking / filtering strategy" row for the full nuance). This still bypasses `MemoryService` entirely, the same disclosed gap as the write side. Note that §3.1's "Workflow Memory" partly overlaps something that *is* real but is **not** this component: the Workflow Engine persists step outputs in `workflow.workflow_steps.outputs`, and `WorkflowStepOutputResolver` gives a later step awareness of an earlier step's output (`context_manager.md` §4). That is workflow *state*, owned by the Workflow Engine — it is not memory, is not promotable, and carries no quality or confidence signals. Roadmap stage: **B**.

Authoritative, always-current status: `../../19_roadmap/feature_inventory.md` (per-module completion table). Detailed build history: `../../19_roadmap/history/INDEX.md`.

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
| **Promotion criteria** | **Decided by §6.1, and the decision is to keep it manual.** Promotion in v1 is an explicit, audited operation; automatic promotion is deferred until real usage data exists to calibrate it. This is a settled position, not an open question — the *reason* for deferral is itself the decision. **Named remaining gap:** who is authorized to promote. [ADR-0023](../../18_decision_log/adr/ADR-0023-identity-roles-and-permissions.md)'s closed permission vocabulary has no memory-promotion permission, and §6 forbids agents from writing arbitrary memory. **Re-verified 2026-08-12 (roadmap reconciliation): the named triple is now a pair.** Still true — no memory permission exists in ADR-0023 or in `security_manager/permissions.py` (the manifest schema declares `memory:read`/`memory:write` for packs, but neither is enforceable Kernel-side and no `memory:promote` exists anywhere), and no principal reaches the call site (`SqlMemoryStore.write_memory` takes no `principal_id`). **No longer true:** this row previously ended "and no audit destination (`governance.audit_log` has no writer)" — that writer shipped in `P01-S05-M04-T05`/`T06` as `SqlAuditLogWriter`, is constructed in `bootstrap.py`, and already has real production callers (Git Integration, role administration, the secrets access broker). A separate, undocumented gap remains on the schema side: `knowledge.memory_items` has `promoted_at` and `provenance` but no `promoted_by`/`reason` column, so *who promoted and why* has nowhere to live. That pair, plus the columns, is what a first increment must settle. |
| **APIs** | **Decided in specification; the Kernel half is now built.** The pack-facing surface is `MemoryService` in `../platform/platform_sdk.md` §5.5, with `write()` as the sole mediated write path (§6); reads reach agents only through the Context Manager, never directly (§7, `context_manager.md` §7). **Updated 2026-08-14 (`P02-S04-M10-T04`):** the ordering constraint this row named — "building a writer before a resolver would produce §2's 'uncontrolled dumping ground' with no consumer to justify any of it" — is **satisfied**: `MemoryResolver` shipped first (`P02-S03-M08-T06`, 2026-08-04) and is wired for real, so the consumer existed before the writer. `ai_os_kernel.memory_manager.service.MemoryService.write()` is now real. **Named remaining gaps, all three narrower than before:** the SDK Protocol is still deliberately deferred (`platform_sdk_v1_scope.md` §7), so no pack can reach this yet; `recall()` is deliberately absent because the Context Manager already owns reads; and **no production caller writes memory**, because no document decides the trigger — see the Implementation Status above for the full, dated reasoning. |

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
- `../../19_roadmap/feature_inventory.md`, `../../19_roadmap/history/INDEX.md`
