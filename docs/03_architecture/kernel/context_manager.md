# Context Manager Design – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Context Manager Design  
**Version:** 1.1  
**Status:** Approved  
**Last Updated:** 2026-08-04 (§4: recorded the real Knowledge Resolver, the second real *source*)

---

## 1. Purpose

This document defines the design of the **Context Manager**, a core component of the AI_OS Platform Kernel.

The Context Manager is responsible for assembling the precise, minimal, and relevant context that an Agent needs to perform its task. It prevents agents from independently pulling large amounts of information and ensures that context is consistent, traceable, and appropriate for the current workflow step.

This document is subordinate to:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Kernel Architecture  
5. Agent Architecture & Agent Contract  
6. Workflow Architecture  
7. Knowledge Manager & Memory Manager (related components)

---

## Implementation Status (2026-07-28; Knowledge Resolver added 2026-08-04)

**Built:** `kernel/src/ai_os_kernel/context_manager/` (4 modules). `ContextManager` (Protocol) and `DefaultContextManager` in `manager.py`; `ContextSourceResolver` (Protocol) plus **three** real resolvers in `resolvers.py` — `WorkflowStateResolver` (a workflow instance's own top-level `inputs`) and `WorkflowStepOutputResolver` (a named prior step's persisted output from `workflow.workflow_steps.outputs`), both sitting behind §4's single "Workflow State Resolver" category; and, as of `P02-S03-M08-T05`, `KnowledgeResolver` — the first real **Knowledge Manager** source (`SourceType.KNOWLEDGE`), calling the real `ai_os_kernel.knowledge_manager.query_engine.QueryEngine` (`P02-S04-M09-T04`) unchanged, with the real, caller-supplied query text carried on a new `ContextRequest.knowledge_query` field. It is the LLM Gateway's real `Embedder`'s second real caller (after `embed_chunk`), computing a real query vector via a caller-supplied `embedding_model_alias` (ADR-0002). `models.py` carries the §6 response contract for real: `SourceType`, `SourceRef`, `ContextItem` (including the mandatory `trust` field), `ContextRequest` (now including `knowledge_query`), `AssembledContext` with `items_excluded_count` and `assembly_id`. The Size & Token Budget Enforcer is real — `_apply_token_budget` in `manager.py` truncates by rank and reports the excluded count, with `estimate_tokens` in `models.py`. **`relevance_score` now has real variance for the first time**: `KnowledgeResolver` passes through the real fused RRF score (`FusedResult.fused_score`) rather than a constant — the precondition §"Ranking / filtering strategy" below and `manager.py`'s own docstring both named as blocking a real Filter/Ranker is now real, though building that component remains out of this step's scope. First real production use of the pre-existing two Workflow State resolvers: the five-step `se.delivery_pipeline` chain, composed in `ai_os_kernel.workflow_engine.delivery_pipeline` (relocated out of the pack's own shipped wheel, `platform_sdk_v1_scope.md` step 7, then promoted from test-harness code into real Kernel code 2026-07-30 once a real HTTP route needed the identical composition); `KnowledgeResolver` has no production composition wiring it in yet — proven directly against real Postgres/a real local embeddings server, not through a real HTTP route. **As of step 7, `ai_os_sdk.models.context`/`ai_os_sdk.contracts.context_service` also carry this Protocol's real boundary models (`ContextRequest`/`AssembledContext`/`ContextItem`/`SourceRef`/`SourceType`) and a declared `ContextService` Protocol, narrowed to match this real Kernel shape exactly — see `platform_sdk.md` §5.3's own dated reconciliation decision block; that SDK-facing `ContextRequest` has not yet been updated to add `knowledge_query`, a disclosed follow-up.**

**Not built:** **2 of the 6 sources in §3 are now real** (Workflow State, Knowledge). There is still no Memory Resolver, no AI Context Pack Resolver, no Configuration Resolver, and no distinct user-input source — blocked on components that are themselves still empty stubs (`memory_manager/` remains a docstring-only `__init__.py`; Configuration Manager is real but deliberately still deferred here, per `resolvers.py`'s own docstring). No **Context Filter / Ranker** exists as a component: `relevance_score` now has genuine variance to rank by (see above), but nothing yet computes a cross-source ranking — §6's "truncates by rank" still ranks by resolver order among items of equal score. No persisted **Context Audit Logger** — §9's per-assembly record is not written to any table, and `assembly_id` is generated but never stored, so **exact replay of a past assembly is not currently possible**. `index_generation` is specified in §6 but `KnowledgeResolver` does not pin one (`RetrievalRequest.index_generation` defaults to unpinned) — no producer creates a second real generation yet either. §6's `trust` field is enforced as a required field; `KnowledgeResolver` is the first source to emit a genuinely variable (not fixed-constant) `trust` per item, reflecting the queried document's own real classification. Token counting is a character-length estimate (`_CHARS_PER_TOKEN_ESTIMATE = 4`), not a provider token count — the LLM Gateway has no `count_tokens()` wired in here yet (it exists, `P02-S02-M06-T10`, but this package does not call it).

Authoritative, always-current status: `../../19_roadmap/feature_inventory.md` (per-module completion table) and `../../19_roadmap/implementation_status.md`. Detailed build history: `../../19_roadmap/history/INDEX.md` (specifically `012_context_manager.md`).

---

## 2. Design Goals

The Context Manager must:

- Assemble context in a controlled and predictable way
- Supply only the information required for the current step
- Integrate data from multiple sources (Knowledge, Memory, Workflow State, Runtime Configuration, User Inputs)
- Remain domain-agnostic
- Support reproducibility for multi-LLM experiments
- Be fully observable (what context was given to which agent)
- Prevent agents from performing uncontrolled context retrieval

---

## 3. Core Responsibilities

- Accept a context request from the Workflow Engine (or Agent Invoker)
- Determine what information is required for the current agent and step
- Retrieve relevant data from:
  - Workflow State
  - Knowledge Manager
  - Memory Manager
  - AI Context Packs
  - Runtime Configuration
  - User-provided inputs
- Apply filtering, ranking, and size limits
- Return a structured context object
- Record exactly what context was supplied (for audit and replay)

---

## 4. High-Level Structure

```text
Context Manager
│
├── Context Request Handler
├── Source Resolvers
│     ├── Workflow State Resolver
│     ├── Knowledge Resolver
│     ├── Memory Resolver
│     ├── AI Context Pack Resolver
│     └── Configuration Resolver
├── Context Assembler
├── Context Filter / Ranker
├── Size & Token Budget Enforcer
└── Context Audit Logger
```

**Two real "Workflow State" resolvers now exist (2026-07-28), not one.** `ai_os_kernel.context_manager.resolvers.WorkflowStateResolver` reads a workflow instance's own top-level `inputs` (unchanged, matches "Workflow State Resolver" above exactly). A second, sibling resolver, `WorkflowStepOutputResolver`, reads a *named prior step's* own persisted output (`workflow_steps.outputs`) — §5's own `required_context_types` example already named this case (`previous_outputs`) without a resolver to back it; this is that resolver. Both share the same source category — this is not a new bullet in the diagram above, but a second real implementation behind the existing "Workflow State Resolver" one. Both live in `kernel/src/ai_os_kernel/context_manager/resolvers.py`. See `ai_os_kernel.workflow_engine.delivery_pipeline` (relocated from `ai_os_pack_software_engineering.pipeline` in `platform_sdk_v1_scope.md` step 7, then promoted from `tests/integration/_delivery_pipeline.py` into real Kernel code 2026-07-30, once a real HTTP route — `POST /api/v1/workflows/se.delivery_pipeline` — needed the identical composition) for its first real, production use, chaining a real five-step workflow declared in `capability_packs/software-engineering/workflows/delivery_pipeline.yaml`.

**The "Knowledge Resolver" bullet above is now real too (2026-08-04, `P02-S03-M08-T05`).** `ai_os_kernel.context_manager.resolvers.KnowledgeResolver` calls the real Knowledge Manager `QueryEngine` (§7's own related component, `knowledge_manager.md`) — the first genuine consumer any Knowledge Manager/Retrieval component built this session has had. Proven end to end against real Postgres and a real local embeddings server: a real document indexed through `IndexingService`, queried by real text, lands in a real `AssembledContext` alongside a real `WorkflowStateResolver` item, with real provenance and a real, non-constant `relevance_score`. Not yet wired into any production composition (no HTTP route or workflow-engine call site constructs one yet) — the identical "real, proven, not yet wired" precedent `sub_workflow`/`parallel`/`decision` step types established in the Workflow Engine before their own first real callers.

---

## 5. Context Request

A typical context request contains:

- workflow_id
- step_id
- agent_id
- required_context_types (e.g., requirements, architecture, previous_outputs, coding_standards, etc.)
- token_budget or size limit
- experiment / run identifiers (for reproducibility)

**`knowledge_query` (2026-08-04, `P02-S03-M08-T05`) is a real, additive field beyond this list** — plain query text for `KnowledgeResolver` (§4). Not anticipated by the list above (no prior field here named a query concept at all); added the identical way `token_budget` itself was, once a real resolver gave it a real, immediate need. `None` means "no knowledge query declared for this request," the same "an unresolvable source contributing nothing is not a failure" shape every resolver in this package already establishes.

---

## 6. Context Response

```text
AssembledContext
    items: ContextItem[]
    total_tokens: int
    sources_queried: SourceType[]
    items_excluded_count: int          # what did NOT fit, so truncation is visible
    assembly_id: str
    index_generation: str              # pinnable for reproducibility

ContextItem
    content: str
    provenance: SourceRef              # where it came from, and at what version
    relevance_score: float
    token_count: int
    trust: Literal["trusted", "untrusted"]
```

**`trust` is mandatory on every item and is load-bearing.** Repository content, ingested documents, tool output, and web content are always `untrusted`. The Prompt Engine wraps untrusted items in explicit data boundaries, and no untrusted content can confer authority — that structural rule, not prompt wording, is what contains prompt injection ([ADR-0016](../../18_decision_log/adr/ADR-0016-tool-execution-sandboxing.md)).

**Budget enforcement is hard, and truncation is recorded.** When the token budget is reached, assembly truncates by rank and reports `items_excluded_count`. Silent overflow — or silent dropping without a count — would make a degraded run indistinguishable from a healthy one.

---

## 7. Key Design Rules

- Agents must not bypass the Context Manager to pull arbitrary knowledge.
- Context must be minimal yet sufficient.
- The same context request under the same conditions should produce the same context (important for multi-LLM experiments).
- All context assembly decisions must be auditable.

---

## 8. Relationship with Other Components

- **Workflow Engine** asks the Context Manager to prepare context before invoking an Agent.
- **Knowledge Manager** provides long-term documentation, ADRs, specifications, and patterns.
- **Memory Manager** provides short-term and long-term engineering memory.
- **AI Context Packs** provide curated, high-signal context packages.
- **Prompt Engine** may receive parts of the assembled context when rendering prompts.
- **LLM Gateway** ultimately receives the final prompt that was built using this context.

---

## 9. Observability Requirements

Every context assembly must record:

- Workflow ID / Trace ID / Agent ID
- What sources were queried
- What items were included or excluded
- Final context size / token estimate
- Timestamp

This supports debugging and exact replay of experiments.

---

## 10. Current Status

This document defines the design baseline for the Context Manager. The three items v1.0 of this section deferred are settled as follows — none is left open as "to be refined."

| Item | Status |
|---|---|
| **Detailed interfaces** | **Decided and built.** `ContextManager` and `ContextSourceResolver` are Protocols in `kernel/src/ai_os_kernel/context_manager/` (`manager.py`, `resolvers.py`), per [ADR-0004](../../18_decision_log/adr/ADR-0004-interface-driven-and-configuration-over-code.md) (interface-driven) and [ADR-0010](../../18_decision_log/adr/ADR-0010-composition-and-dependency-injection.md) (constructed in `bootstrap.py`, no container). The pack-facing name for the same capability is `ContextService` in `../platform/platform_sdk.md` §5.3. **Named remaining gap:** that SDK-facing Protocol does not exist as code — `platform_sdk/` contains only `schemas/manifest.schema.json` — so packs currently depend on the Kernel Protocol directly, under the dated temporary exception in `../capability_framework/capability_pack_contract.md`. |
| **Data models** | **Decided and built.** §5 and §6 above *are* the data models, and they are implemented field-for-field in `kernel/src/ai_os_kernel/context_manager/models.py`, plus the real, additive `knowledge_query` field (§5's own note). `trust` is mandatory, as [ADR-0016](../../18_decision_log/adr/ADR-0016-tool-execution-sandboxing.md) requires. **Named remaining gap:** `index_generation` has no producer until a vector index exists ([ADR-0013](../../18_decision_log/adr/ADR-0013-search-and-vector-store.md)); `relevance_score` now has a real producer (`KnowledgeResolver`'s fused RRF score), but nothing yet computes a genuine *cross-source* ranking from it. |
| **Ranking / filtering strategy** | **Genuinely open, and correctly so — but its blocking precondition is now met.** [ADR-0013](../../18_decision_log/adr/ADR-0013-search-and-vector-store.md) already decides how *retrieval* ranks — keyword (Postgres FTS) plus vector (pgvector) combined by Reciprocal Rank Fusion — so ranking *within one retrieval source* is not open. What is open is **cross-source ranking**: how a Knowledge item, a Memory item, and an AI Context Pack item are ordered against one another when they compete for the same token budget. The two hard constraints are already fixed and constrain any answer: Knowledge outranks Memory in *authority* (`../../20_glossary/glossary.md` §3, `memory_manager.md` §6), and §7's determinism rule forbids any non-reproducible tiebreak. Settling it needs a real multi-source assembly to calibrate against — as of `P02-S03-M08-T05`, one now exists (Workflow State + Knowledge, both with genuinely differing `relevance_score`s) — but picking a weighting is still deliberately left undecided this step, out of its own scope; a Memory source would sharpen the calibration further once real. |

---

## 11. Final Authority

Order of precedence:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Kernel Architecture  
5. Context Manager Design  
6. Source Code

---

## 12. Related Documents

**Governing decisions (ADRs):**
- [ADR-0013 — Search and Vector Store](../../18_decision_log/adr/ADR-0013-search-and-vector-store.md) — retrieval ranking, `index_generation`
- [ADR-0016 — Tool Execution Sandboxing](../../18_decision_log/adr/ADR-0016-tool-execution-sandboxing.md) — the mandatory `trust` tag and structural injection containment
- [ADR-0022 — Reproducibility over Determinism](../../18_decision_log/adr/ADR-0022-reproducibility-over-determinism.md) — why assembly must be replayable
- [ADR-0004 — Interface-Driven and Configuration over Code](../../18_decision_log/adr/ADR-0004-interface-driven-and-configuration-over-code.md)
- [ADR-0010 — Composition and Dependency Injection](../../18_decision_log/adr/ADR-0010-composition-and-dependency-injection.md)

**Superior documents:**
- `../platform/system_architecture.md`
- `kernel_architecture.md`
- `../agents/agent_architecture.md`
- `../workflow/workflow_architecture.md`

**Source components (§3's six sources):**
- `knowledge_manager.md` — authoritative documented knowledge (stub)
- `memory_manager.md` — experiential memory (stub)
- `../services/search_vector_search.md` — the Retrieval component behind both (stub)
- `../../ai_context/context_pack_structure.md`, `../../ai_context/ai_context_strategy.md` — AI Context Packs
- `configuration_manager.md` — Runtime Configuration source
- `workflow_engine.md` — the one real source: workflow state and prior step outputs

**Consumers:**
- `prompt_engine.md` — receives assembled context, wraps untrusted items in data boundaries
- `llm_gateway.md` — receives the prompt built from this context
- `../platform/platform_sdk.md` §5.3 `ContextService` — the pack-facing Protocol (specified, not built)

**Owned / referenced tables:**
- `../../08_database/data_model.md` §4 (`workflow.workflow_instances`, `workflow.workflow_steps` — the only sources read today), §7 (Knowledge and Retrieval — read once a Knowledge Resolver exists). This component owns no tables of its own; §9's audit record has no table yet.

**Reference:**
- `../../20_glossary/glossary.md` §3 — the single authority for Knowledge / Memory / Context / Context Pack
- `../../19_roadmap/feature_inventory.md`, `../../19_roadmap/implementation_status.md`, `../../19_roadmap/history/INDEX.md`
