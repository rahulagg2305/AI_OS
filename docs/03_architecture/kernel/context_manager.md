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

## Implementation Status (2026-07-28; Knowledge Resolver added 2026-08-04; Filter/Ranker added 2026-08-04; Audit Logger added 2026-08-04; Memory Resolver added 2026-08-04; Runtime Config Resolver added 2026-08-05; AI Context Pack Resolver added 2026-08-05; Runtime Config Resolver wired into production 2026-08-05)

**Built:** `kernel/src/ai_os_kernel/context_manager/` (6 modules, +`schema.py`/`audit_logger.py` as of `P02-S03-M08-T10`). `ContextManager` (Protocol) and `DefaultContextManager` in `manager.py`; `ContextSourceResolver` (Protocol) plus **four** real resolvers in `resolvers.py` — `WorkflowStateResolver` (a workflow instance's own top-level `inputs`) and `WorkflowStepOutputResolver` (a named prior step's persisted output from `workflow.workflow_steps.outputs`), both sitting behind §4's single "Workflow State Resolver" category; `KnowledgeResolver` (`P02-S03-M08-T05`) — the first real **Knowledge Manager** source (`SourceType.KNOWLEDGE`), calling the real `ai_os_kernel.knowledge_manager.query_engine.QueryEngine` (`P02-S04-M09-T04`) unchanged, with the real, caller-supplied query text carried on a new `ContextRequest.knowledge_query` field, and the LLM Gateway's real `Embedder`'s second real caller (after `embed_chunk`), computing a real query vector via a caller-supplied `embedding_model_alias` (ADR-0002); and, as of `P02-S03-M08-T06`, `MemoryResolver` — the first real **Memory Manager** source (`SourceType.MEMORY`), calling the real `ai_os_kernel.persistence.memory_writer.MemoryStore` (`P02-S04-M10-T01`) unchanged. Two real, stopped-and-resolved forks: `MemoryResolver` deliberately does **not** filter by `source_workflow_id` — genuinely cross-run, matching the Memory Store's own "durable store for cross-run memory" Goal, confirmed via product-owner sign-off rather than assumed; and its `memory_type` is a real constructor parameter, never hardcoded. `relevance_score` reuses a real `quality_signal` when set, or a principled `0.0` otherwise (nothing computes `quality_signal` yet) — proven, not asserted, to genuinely calibrate the "Ranking / filtering strategy" open question below: a real three-source assembly (Workflow State `1.0`, Knowledge's real fused RRF score, Memory's `0.0`) now shows Knowledge genuinely outranking Memory with real, differing, non-fabricated scores. `models.py` carries the §6 response contract for real: `SourceType`, `SourceRef`, `ContextItem` (including the mandatory `trust` field), `ContextRequest` (now including `knowledge_query`), `AssembledContext` with `items_excluded_count` and `assembly_id`. The Size & Token Budget Enforcer is real — `_apply_token_budget` in `manager.py` truncates by rank and reports the excluded count, with `estimate_tokens` in `models.py`. **`relevance_score` now has real variance for the first time**: `KnowledgeResolver` passes through the real fused RRF score (`FusedResult.fused_score`) rather than a constant. **The Context Filter / Ranker is now real too (`P02-S03-M08-T09`)**: `manager.py`'s new `_rank_by_relevance` sorts every candidate item descending by `relevance_score` (stable tie-break on resolver-arrival order, ADR-0022) *before* the Size & Token Budget Enforcer runs, matching §4's own diagram sequencing — a deliberate, product-owner-confirmed reversal of this module's own prior guarantee that survivors kept their original resolver order (the renamed `test_surviving_items_are_returned_in_rank_order_not_resolver_order`, formerly asserting the opposite). Proven against real Postgres/a real local embeddings server: two real sources (`WorkflowStateResolver`'s constant `1.0`, `KnowledgeResolver`'s real fused `~0.0164`) genuinely reorder in the output regardless of which resolver ran first, and a tight real budget genuinely retains the higher-ranked real item. First real production use of the pre-existing two Workflow State resolvers: the five-step `se.delivery_pipeline` chain, composed in `ai_os_kernel.workflow_engine.delivery_pipeline` (relocated out of the pack's own shipped wheel, `platform_sdk_v1_scope.md` step 7, then promoted from test-harness code into real Kernel code 2026-07-30 once a real HTTP route needed the identical composition); `KnowledgeResolver` has no production composition wiring it in yet — proven directly against real Postgres/a real local embeddings server, not through a real HTTP route. **As of step 7, `ai_os_sdk.models.context`/`ai_os_sdk.contracts.context_service` also carry this Protocol's real boundary models (`ContextRequest`/`AssembledContext`/`ContextItem`/`SourceRef`/`SourceType`) and a declared `ContextService` Protocol, narrowed to match this real Kernel shape exactly — see `platform_sdk.md` §5.3's own dated reconciliation decision block; that SDK-facing `ContextRequest` has not yet been updated to add `knowledge_query`, a disclosed follow-up.** **The Context Audit Logger is now real too (`P02-S03-M08-T10`)**: `audit_logger.py`'s `SqlContextAuditLogger`, writing to a new `context.context_assemblies` table (data_model.md §9b, migration `0033`) — the first real schema/persistence this package has ever had. Wired as an optional collaborator on `DefaultContextManager` (`audit_logger=None` by default, zero behaviour change for every existing caller); when configured, every `assemble()` call durably records `assembly_id`, `workflow_id`/`step_id`/`agent_id`, `sources_queried`, every included item at full fidelity (enabling exact replay), `items_excluded_count`, `total_tokens`, and a real timestamp. Two of §9's five named fields are real, disclosed gaps, not fabricated: no `trace_id` (nothing threads a `TraceContext` into context assembly anywhere in this codebase), and no per-excluded-item identity (`AssembledContext` itself only ever carries a count). Proven against real Postgres: a full-fidelity round trip, a real budget-trimmed exclusion genuinely persisted, and a genuine `None` for an unknown id.

**`RuntimeConfigResolver` is real too (`P02-S03-M08-T08`)**: `SourceType.CONFIGURATION`, calling the real `ai_os_kernel.configuration_manager.loader.ConfigurationManager` unchanged — its first Context Manager consumer. Re-resolves fresh on every `resolve()` call, including the live `RuntimeOverrideStore` snapshot (Layer 5, `P01-S02-M01-T04`) — never a value cached once at composition time, since Layer 5's whole documented purpose is a live override with no process restart. `config_keys` is a real constructor parameter, validated against `PlatformConfig`'s own real declared fields at construction time (an unknown key is rejected immediately, not deferred to first use). `trust` is `"trusted"` here — the *opposite* of `WorkflowStateResolver`'s own classification, for a real, reasoned cause: runtime configuration is operator-authored and schema-validated, genuinely on the other side of ADR-0016's own "authored by the Kernel's own trusted subsystems" line, not an inconsistency. Proven with real YAML files, a real `ConfigurationManager`, and a real `RuntimeOverrideStore` (no database — `ConfigChangeWriter` faked, the identical precedent `test_runtime_overrides.py` already established for testing this exact seam): real config values become real context items, a live override is genuinely reflected without reconstructing the resolver, an unknown key is rejected at construction, and a real `DefaultContextManager.assemble()` call carries a real config value through end to end.

**`AIContextPackResolver` is real too (`P02-S03-M08-T07`)**: `SourceType.AI_CONTEXT_PACK`, the last of §3's six documented sources to go real. Investigation found the real gap was never missing documentation — `../../ai_context/context_pack_structure.md` §3/§4 fully specifies the directory layout (`<category>/<pack_name>/manifest.yaml` plus numbered content files) and manifest fields (`id`/`name`/`version`/`type`/`description`/`applies_to`/`priority`) — but that the real `ai_context/` directory itself is absent from a fresh clone (that document's own words: "Built: nothing"), and CLAUDE.md's own standing rule forbids creating a planned folder speculatively. Resolved by constructor-injecting `base_dir: Path` (mirroring `ConfigurationManager`'s own `platform_config_path` injection) rather than assuming a fixed repo path, so the resolver never creates or requires that directory to exist. `pack_references` is a real constructor parameter (mirroring `RuntimeConfigResolver`'s own `config_keys`): automatic, `applies_to`-based pack selection is out of scope — a caller names exactly which packs it wants. A missing pack directory, missing `manifest.yaml`, or missing individual content file all resolve to "no such pack/section," never an error — the identical "an unresolvable source contributing nothing is not a failure" shape every other resolver here establishes; a manifest that exists but is malformed (invalid YAML, non-mapping, or missing the required `id`/`version` fields — §7: "every context pack must have a version") is rejected as a real error, not silently skipped. `relevance_score` reads the manifest's own declared `priority` (`0.0` when absent, the identical default `MemoryResolver` uses for an unset `quality_signal`). `trust` is `"trusted"` — operator-authored and schema-validated, the same side of ADR-0016's line as `RuntimeConfigResolver`. Proven with real file I/O against a real `tmp_path` directory (the identical precedent `test_loader.py` already established for `ConfigurationManager`'s own not-yet-populated YAML files), never the actual repository `ai_context/` directory: a real pack's real content files flow into a real `AssembledContext`, an undeclared/missing pack resolves to no items, and a manifest missing `version` is rejected.

**Not built:** **all 6 of the 6 sources in §3 are now real** (Workflow State, Knowledge, Memory, Runtime Configuration, AI Context Packs) plus User-provided inputs folded into `WorkflowStateResolver` — every documented source now has a real resolver. `memory_manager/` itself remains a docstring-only `__init__.py` — `MemoryResolver` calls a real store one layer down (`persistence/memory_writer.py`), the identical relationship `KnowledgeResolver` has to `knowledge_manager/query_engine.py`. No automatic, `applies_to`-based AI Context Pack selection exists — `pack_references` must be caller-supplied. `KnowledgeResolver`/`MemoryResolver`/`AIContextPackResolver` are still not wired into any production composition (`RuntimeConfigResolver` is, as of `P02-S03-M08-T11` — see above). The Filter/Ranker does not filter by anything beyond relevance/budget — no minimum-score threshold, no `required_context_types` selection (that field still does not exist on `ContextRequest`), since nothing documents a real criterion to filter by yet. `index_generation` is specified in §6 but `KnowledgeResolver` does not pin one (`RetrievalRequest.index_generation` defaults to unpinned) — no producer creates a second real generation yet either. §6's `trust` field is enforced as a required field; `KnowledgeResolver` is the first source to emit a genuinely variable (not fixed-constant) `trust` per item, reflecting the queried document's own real classification. Token counting is a character-length estimate (`_CHARS_PER_TOKEN_ESTIMATE = 4`), not a provider token count — the LLM Gateway has no `count_tokens()` wired in here yet (it exists, `P02-S02-M06-T10`, but this package does not call it).

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

**The "Memory Resolver" bullet above is now real too (2026-08-04, `P02-S03-M08-T06`).** `ai_os_kernel.context_manager.resolvers.MemoryResolver` calls the real Memory Store (§7's own related component, `memory_manager.md`) — its first genuine consumer. Genuinely cross-run: proven against real Postgres that a memory item written under one workflow instance surfaces in a context assembly for a *different* one, never filtered by `source_workflow_id`. Also not yet wired into any production composition.

**The "AI Context Pack Resolver" bullet above is now real too (2026-08-05, `P02-S03-M08-T07`).** `ai_os_kernel.context_manager.resolvers.AIContextPackResolver` reads real files against `../../ai_context/context_pack_structure.md`'s documented layout via a constructor-injected `base_dir`, never the (still-absent) actual repo `ai_context/` directory. Not yet wired into any production composition.

**`RuntimeConfigResolver` is the first of these to close the "not yet wired into any production composition" gap (2026-08-05, `P02-S03-M08-T11`).** No roadmap ticket named this wiring before this step — found by regenerating `STATUS.md` fresh and sweeping every `todo` ticket tree-wide, then authored as a new, minimal ticket rather than guessed. `ai_os_kernel.bootstrap._lifespan` (the `api` role) and `ai_os_kernel.bootstrap.build_workflow_worker_loop` (the `worker` role) now both construct a real `RuntimeConfigResolver` alongside the pre-existing `WorkflowStateResolver`, backed by a real, persistent `ConfigurationManager`/`RuntimeOverrideStore` pair — the first production composition to keep a live Layer 5 `RuntimeOverrideStore` running at all. Proven end to end against real Postgres with a real, Echo-backed agent (`tests/integration/test_bootstrap_workflow_trigger.py`): the real `_build_workflow_trigger` production path, given the identical resolver composition `_lifespan` now builds, genuinely renders real `env`/`role` configuration values into a real agent's completed step output, alongside the workflow's own real `inputs`. `KnowledgeResolver`/`MemoryResolver`/`AIContextPackResolver` remain unwired — this step closes the gap for one resolver, not all four, a disclosed, deliberate scope limit (`bootstrap.py`'s own module docstring has the full account). Degrades gracefully, never crashes Kernel startup, when the process's own `AIOS_ENV` is not one of `ConfigurationManager`'s four real, documented environments (`deployment_architecture.md` §4) — this repository's own CI workflow sets `AIOS_ENV=ci`, an identity that was never meant to satisfy that closed vocabulary; `WorkflowStateResolver` alone still runs in that case, the same "one broken source must not prevent the others" resilience `ManifestLoader.scan()` already establishes for pack discovery.

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

**Real as of `P02-S03-M08-T10`** — `ai_os_kernel.context_manager.audit_logger.SqlContextAuditLogger`, `context.context_assemblies` (data_model.md §9b). "Trace ID" and "what items were... excluded" (specific identities, not only a count) are real, disclosed gaps — see that section for why — every other bullet here is genuinely recorded.

---

## 10. Current Status

This document defines the design baseline for the Context Manager. The three items v1.0 of this section deferred are settled as follows — none is left open as "to be refined."

| Item | Status |
|---|---|
| **Detailed interfaces** | **Decided and built.** `ContextManager` and `ContextSourceResolver` are Protocols in `kernel/src/ai_os_kernel/context_manager/` (`manager.py`, `resolvers.py`), per [ADR-0004](../../18_decision_log/adr/ADR-0004-interface-driven-and-configuration-over-code.md) (interface-driven) and [ADR-0010](../../18_decision_log/adr/ADR-0010-composition-and-dependency-injection.md) (constructed in `bootstrap.py`, no container). The pack-facing name for the same capability is `ContextService` in `../platform/platform_sdk.md` §5.3. **Named remaining gap:** that SDK-facing Protocol does not exist as code — `platform_sdk/` contains only `schemas/manifest.schema.json` — so packs currently depend on the Kernel Protocol directly, under the dated temporary exception in `../capability_framework/capability_pack_contract.md`. |
| **Data models** | **Decided and built.** §5 and §6 above *are* the data models, and they are implemented field-for-field in `kernel/src/ai_os_kernel/context_manager/models.py`, plus the real, additive `knowledge_query` field (§5's own note). `trust` is mandatory, as [ADR-0016](../../18_decision_log/adr/ADR-0016-tool-execution-sandboxing.md) requires. **Named remaining gap:** `index_generation` has no producer until a vector index exists ([ADR-0013](../../18_decision_log/adr/ADR-0013-search-and-vector-store.md)); `relevance_score` now has both a real producer (`KnowledgeResolver`'s fused RRF score) and a real consumer (`_rank_by_relevance`), closing this row's own prior gap. |
| **Ranking / filtering strategy** | **Cross-source ranking is real (`P02-S03-M08-T09`) and now calibrated against a real third source (`P02-S03-M08-T06`) — raw score comparison holds, at least for today's real score scales, but whether it stays right forever remains genuinely open.** [ADR-0013](../../18_decision_log/adr/ADR-0013-search-and-vector-store.md) already decides how *retrieval* ranks — keyword (Postgres FTS) plus vector (pgvector) combined by Reciprocal Rank Fusion — so ranking *within one retrieval source* was never open. `manager.py`'s `_rank_by_relevance` genuinely sorts every candidate, from every source, by `relevance_score` directly, with no per-source weighting. What was open: whether raw comparison, with **no explicit authority weighting**, would actually honor the documented hard constraint — Knowledge outranks Memory in *authority* (`../../20_glossary/glossary.md` §3, `memory_manager.md` §6) — once a real Memory source existed to test it against, rather than being true only by coincidence. **Now answered, empirically, not assumed:** `MemoryResolver`'s principled `0.0` default (no `quality_signal` computed yet) genuinely sits below both `WorkflowStateResolver`'s constant `1.0` and every real, positive Knowledge RRF score — proven in one real three-source assembly. This holds only because nothing has ever set a high `quality_signal` yet; whether raw comparison remains correct once promotion/scoring logic is real (and a highly-scored memory could plausibly out-rank a weak Knowledge hit) is the part still genuinely open, deliberately left for whenever that logic exists — the same reasoning `memory_manager.md` §6.1 applies to promotion heuristics generally. §7's determinism rule is satisfied either way: `_rank_by_relevance` is a stable sort, so ties never break arbitrarily. |

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
