# Knowledge Manager Design – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Knowledge Manager Design  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## 1. Purpose

This document defines the design of the **Knowledge Manager**, a core component of the AI_OS Platform Kernel.

The Knowledge Manager is responsible for storing, organizing, indexing, and retrieving the long-term, authoritative knowledge of the platform and of individual projects. It is one of the primary sources that the Context Manager uses when assembling context for Agents.

Knowledge must survive changes of LLM, changes of team members, and loss of chat history.

This document is subordinate to:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Kernel Architecture  
5. Context Manager Design  

---

## Implementation Status (2026-07-28; embed() row corrected 2026-08-04; RRF fusion added 2026-08-04; retrieval service added 2026-08-04; indexing component added 2026-08-04; query engine added 2026-08-04; provenance/versioning added 2026-08-04)

**Built:** `kernel/src/ai_os_kernel/knowledge_manager/` now has two real components — **updated 2026-08-04 (`P02-S04-M09-T03`/`T04`)**: `indexing.py`'s `IndexingService`, real deterministic chunking (`chunk_content()`, fixed-size character windows with overlap, `chunk_strategy_version="fixed-size-v1"`) plus a real archive-and-replace change policy, both through the real, unchanged `SqlKnowledgeWriter` below; and `query_engine.py`'s `QueryEngine`, composing the real `RetrievalService` (one layer down) with a real provenance join back to `knowledge.chunks`/`knowledge.documents` — genuinely satisfying "ranked results with provenance," since `FusedResult` itself carries only rank provenance, not source provenance. That same join also filters `archived_at`, so a caller of `QueryEngine` never sees a chunk `IndexingService` has since superseded — a real, tested, partial closure of the gap `T03` disclosed (the raw searchers below remain unfiltered for a caller that bypasses `QueryEngine`). Everything else real still sits **one layer down, in the persistence/retrieval packages**, deliberately narrower than this design: `kernel/src/ai_os_kernel/persistence/knowledge_schema.py` (tables `knowledge.documents`, `knowledge.chunks`, `knowledge.embeddings`, `knowledge.memory_items`), `knowledge_writer.py` (`KnowledgeWriter` Protocol + `SqlKnowledgeWriter.write_document()`, with `ChunkInput` / `ChunkRecord` / `DocumentRecord` models), `knowledge_keyword_search.py` (`KeywordSearcher` Protocol + `SqlKeywordSearcher.search()` over the generated `content_tsv` column), and `knowledge_ids.py`.

**Not built:** every other component in §5. **Knowledge Ingestion** is now partially real — `IndexingService` genuinely chunks and writes real content, proven end to end through the real `RetrievalService` (module 11's own row) — but there is still no format detection or parser adapters (`../services/document_processing.md` is 0% built), so nothing yet feeds it real `docs/`/ADR/specification content; §4's "ingest knowledge from approved sources" still does not happen against real project content. No **Indexer (structured + vector)** as a component of *this* package, but both its real prerequisites now exist one layer down: a real embeddings writer (`ai_os_kernel.retrieval.embedding_writer.SqlEmbeddingWriter`/`embed_chunk`, `P02-S04-M11-T03`) calls the LLM Gateway's real `embed()` (`P02-S02-M06-T09`) and persists a genuine vector into `knowledge.embeddings`, and real vector search (`ai_os_kernel.retrieval.vector_search.SqlVectorSearcher`, `P02-S04-M11-T04`) genuinely ranks those real vectors by real cosine distance — both proven against real Postgres/pgvector. `IndexingService` does not call either — it produces no embeddings, so a real caller wanting vector search over freshly-indexed content must still compute and write that separately; nothing does yet. **Query Engine is now real** (`ai_os_kernel.knowledge_manager.query_engine.QueryEngine`, `P02-S04-M09-T04`, see the Built paragraph above) — the first component of *this* package to genuinely answer a query, not just persist or fuse one layer down. It does not itself call `embed()` (the caller still supplies the query vector, the identical scope boundary `RetrievalService` already establishes); it does not filter `archived_at` for a caller reaching `RetrievalService`/either real searcher directly (only its own callers benefit); and no Context Manager resolver calls it yet. **Updated 2026-08-04 (`P02-S04-M09-T05`)**: every `KnowledgeQueryResult` now carries real version provenance too — `chunk_strategy_version` (always present) and `embedding_model_id`/`embedding_model_version`/`index_generation` (present only when a real embedding row exists under the exact model/version the request queried with; a genuine, disclosed `None` for a keyword-only hit, never fabricated). Proven against real Postgres: version always present, embedding provenance genuinely absent when no matching embedding exists, and the highest real `index_generation` wins deterministically on a tie. Still no **Version Manager** as a dedicated component — §4's "versioned access to knowledge items" has a real *reporting* mechanism now (the fields above), but nothing decides or manages what creating a real second generation would mean, or triggers a re-index; that remains a separate, larger, undecided gap. No **Provenance Tracker** as a dedicated component either — `QueryEngine` exposes real source (`document_id`/`source_uri`/`trust`) and version provenance per result, but nothing tracks provenance across a chain of derived/transformed content beyond that direct join. No **Access / Filter Layer** — §2's "permission-aware retrieval" is entirely absent. `kernel/src/ai_os_kernel/context_manager/resolvers.py`'s real `KnowledgeResolver` (`P02-S03-M08-T05`) does now read from this package — closing the prior "no Context Manager resolver reads any of this" gap — but no production composition wires it into a running workflow yet, and §8's observability requirements still have no producer. Roadmap stage: **B** (basic) / **E** (full).

Authoritative, always-current status: `../../19_roadmap/feature_inventory.md` (per-module completion table) and `../../19_roadmap/implementation_status.md`. Detailed build history: `../../19_roadmap/history/INDEX.md` (specifically `013_retrieval.md`).

---

## 2. Design Goals

The Knowledge Manager must:

- Act as a reliable, long-term source of truth
- Support both platform-level knowledge and project-level knowledge
- Provide precise, permission-aware retrieval
- Remain domain-agnostic at the Kernel level
- Support versioning and traceability of knowledge items
- Integrate cleanly with the Context Manager and AI Context Packs
- Be fully observable

---

## 3. Types of Knowledge

The Knowledge Manager handles several categories of knowledge:

### Platform Knowledge
- Project Constitution and Governance documents
- Architecture documents
- Coding standards
- Capability Pack contracts
- ADRs
- Best practices and patterns
- Anti-patterns and known limitations

### Project Knowledge
- Requirements
- Architecture decisions for a specific product
- API specifications
- Database schemas
- Design documents
- Acceptance criteria
- Generated documentation

### Not Knowledge: Engineering Memory

Engineering memory is **not** handled by the Knowledge Manager. v1.0 of this document called it "related but distinct", which left the seam ambiguous. The boundary is now explicit and is by **authority and lifetime**:

| | Knowledge Manager | Memory Manager |
|---|---|---|
| Content | Documented, approved, authoritative | Experiential — what happened, what worked |
| Authority | **Highest** — the source of truth | Lower — **never overrides Knowledge** |
| Origin | `docs/`, specifications, ADRs, project artifacts | Workflow outcomes, promoted lessons |
| Lifetime | Long-lived, versioned | Workflow-scoped, or promoted and long-lived |

Both are **retrieval sources consumed through the Context Manager**; neither is queried directly by an agent. Definitions are in `../../20_glossary/glossary.md` §3, which is the single authority for these four terms (Knowledge, Memory, Context, Context Pack).

---

## 4. Core Responsibilities

- Ingest knowledge from approved sources (docs/, specs/, ADRs, etc.)
- Index knowledge for efficient retrieval
- Support semantic and structured queries
- Provide versioned access to knowledge items
- Enforce access rules where necessary
- Supply relevant knowledge to the Context Manager
- Maintain provenance (where each piece of knowledge came from)

---

## 5. High-Level Structure

```text
Knowledge Manager
│
├── Knowledge Ingestion
├── Knowledge Store
├── Indexer (structured + vector)
├── Query Engine
├── Version Manager
├── Provenance Tracker
└── Access / Filter Layer
```

---

## 6. Key Design Rules

- Documentation in the repository is the primary source of truth.
- The Knowledge Manager must not invent knowledge.
- Retrieved knowledge should carry provenance metadata.
- Knowledge used in any Agent invocation must be auditable.
- The same query under the same conditions should return consistent results (important for experiments).

---

## 7. Relationship with Other Components

- **Context Manager** is the main consumer of the Knowledge Manager.
- **AI Context Packs** can be viewed as curated, high-priority knowledge packages.
- **Memory Manager** handles more dynamic / experiential knowledge; Knowledge Manager handles more stable, documented knowledge.
- **Workflow Engine** and **Agents** never bypass the Context Manager to access knowledge directly in an uncontrolled way.
- **Evaluation / Experiment Engine** benefits from stable knowledge retrieval for fair comparisons.

---

## 8. Observability Requirements

Every knowledge retrieval must be able to record:

- What was requested
- What was returned
- Source documents / IDs
- Version of knowledge items
- Workflow ID / Trace ID correlation

---

## 9. Current Status

This document defines the design baseline for the Knowledge Manager. **Three of the four items v1.0 of this section deferred were already decided by [ADR-0013](../../18_decision_log/adr/ADR-0013-search-and-vector-store.md) and [ADR-0011](../../18_decision_log/adr/ADR-0011-persistence-and-workflow-state.md)** — this section previously described them as open. Corrected:

| Item | Status |
|---|---|
| **Storage technology** | **Not open.** PostgreSQL 16 with SQLAlchemy Core and Alembic ([ADR-0011](../../18_decision_log/adr/ADR-0011-persistence-and-workflow-state.md)); vectors in the same database via `pgvector` ([ADR-0013](../../18_decision_log/adr/ADR-0013-search-and-vector-store.md)). No separate document store or search cluster is to be introduced in v1. A documented scale trigger to a dedicated vector store (Qdrant) exists behind the same `VectorIndex` Protocol — see `../services/search_vector_search.md`. |
| **Indexing strategy** | **Not open.** Keyword via PostgreSQL full-text search with a GIN index, vector via `pgvector` HNSW with cosine distance, and the two combined by **Reciprocal Rank Fusion** ([ADR-0013](../../18_decision_log/adr/ADR-0013-search-and-vector-store.md)). Every stored vector records `embedding_model_id`, version, and `dimensions`; queries compare only vectors from the same model and version, and changing the embedding model is a tracked re-index migration. The keyword half is real (`kernel/src/ai_os_kernel/persistence/knowledge_keyword_search.py`); the vector and fusion halves are not. |
| **Schema for knowledge items** | **Not open.** `knowledge.documents` / `knowledge.chunks` / `knowledge.embeddings`, specified in `../../08_database/data_model.md` §7 and built in `kernel/src/ai_os_kernel/persistence/knowledge_schema.py`. |
| **Concrete APIs** | **Partly decided, and this is the one genuinely open item.** The pack-facing surface is fixed by `../platform/platform_sdk.md` §5.4 `RetrievalService` — packs never get a Knowledge-Manager-shaped API, only a retrieval one, and never query it directly (`context_manager.md` §7). **Named remaining gaps, three of them:** (a) the *ingestion* API has no specified shape at all — who submits a document, whether ingestion is a workflow step or an operator action, and how a re-ingested document supersedes its predecessor; (b) `../services/document_processing.md`'s chunking contract is unwritten, and the existing writer's "already-chunked input" assumption means the seam between chunker and writer is undefined; (c) §2's permission-aware retrieval has no model — [ADR-0023](../../18_decision_log/adr/ADR-0023-identity-roles-and-permissions.md) fixes the permission *vocabulary* but nothing states what a per-document ACL looks like, and `../services/search_vector_search.md` requires access control to be applied as SQL predicates rather than post-filtering, which constrains any answer. (c) is the one to settle first: retrofitting access predicates after an index exists is materially harder than designing them in. |

---

## 10. Final Authority

Order of precedence:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Kernel Architecture  
5. Knowledge Manager Design  
6. Source Code

---

## 11. Related Documents

**Governing decisions (ADRs):**
- [ADR-0013 — Search and Vector Store](../../18_decision_log/adr/ADR-0013-search-and-vector-store.md) — the governing decision for storage, indexing, and hybrid ranking
- [ADR-0011 — Persistence and Workflow State](../../18_decision_log/adr/ADR-0011-persistence-and-workflow-state.md) — PostgreSQL as the single store
- [ADR-0003 — Documentation-First Development](../../18_decision_log/adr/ADR-0003-documentation-first-development.md) — why repository documentation is the primary source of truth (§6)
- [ADR-0022 — Reproducibility over Determinism](../../18_decision_log/adr/ADR-0022-reproducibility-over-determinism.md) — pinnable `index_generation` for fair comparison
- [ADR-0023 — Identity, Roles and Permissions](../../18_decision_log/adr/ADR-0023-identity-roles-and-permissions.md) — the permission vocabulary any access layer must use

**Superior documents:**
- `../platform/system_architecture.md`
- `kernel_architecture.md`
- `context_manager.md` — the **only** legitimate consumer of this component

**Boundary partners:**
- `memory_manager.md` — the other side of the §3 authority/lifetime boundary; Memory never overrides Knowledge
- `../services/search_vector_search.md` — the Retrieval component that actually executes queries against this store
- `../services/document_processing.md` — the ingestion pipeline (chunking, parsers) this component depends on; 0% built
- `../../knowledge/knowledge_base_structure.md` — the on-disk directory taxonomy being ingested
- `../../ai_context/ai_context_strategy.md`, `../../ai_context/context_pack_structure.md` — AI Context Packs as curated, high-priority knowledge
- `llm_gateway.md` §11 — the sole source of embeddings (`embed()`, not yet built)
- `evaluation_engine.md` — depends on stable retrieval for fair multi-LLM comparison
- `traceability_engine.md` — traceability data as long-term project knowledge
- `../platform/platform_sdk.md` §5.4 `RetrievalService` — the pack-facing surface

**Owned tables:**
- `../../08_database/data_model.md` §7 — `knowledge.documents`, `knowledge.chunks`, `knowledge.embeddings` (and `knowledge.memory_items`, owned by the Memory Manager)

**Reference:**
- `../../20_glossary/glossary.md` §3 — the single authority for Knowledge / Memory / Context / Context Pack
- `../../19_roadmap/feature_inventory.md`, `../../19_roadmap/implementation_status.md`, `../../19_roadmap/history/INDEX.md`
