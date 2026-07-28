# Search & Vector Search Design – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Search & Vector Search Design  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## Implementation Status (2026-07-28)

**Partially built — the keyword half only; there is no vector search.**

**Built:** the four `knowledge.*` tables (migration `0029`, with the `pgvector` extension enabled and a generated `content_tsv` column + GIN index); a real writer (`kernel/src/ai_os_kernel/persistence/knowledge_writer.py`) persisting a document and its already-chunked content in one transaction; and a real keyword searcher (`knowledge_keyword_search.py`) ranking chunks via `plainto_tsquery`/`ts_rank`.

**Not built:** **vector search, the Hybrid Ranker, and Reciprocal Rank Fusion** — none exists, so the central claim of this document is unimplemented. Also absent: any embeddings writer (nothing ever populates `knowledge.embeddings`), the Indexing Pipeline and chunking engine (the writer requires input already chunked and hashed precisely because nothing produces it), metadata/`trust`/`project_id` filtering, SQL-predicate access control, `index_generation` pinning, and a Retrieval Service (`kernel/src/ai_os_kernel/retrieval/` is a docstring-only stub). **Neither the writer nor the reader has any consumer** — no Context Manager resolver, no Knowledge Manager, and no API route calls either.

Two deliberate deferrals pending a real embedding-model decision this codebase has not made: `embeddings.embedding` has **no fixed dimension**, and its documented HNSW cosine index **does not exist**. Any step that starts generating embeddings must choose a model and dimension, then add that index in an additive migration. Outstanding Stage B deliverable.

Authoritative, always-current status: `../../19_roadmap/feature_inventory.md` and `../../19_roadmap/implementation_status.md`. Build history: `../../19_roadmap/history/INDEX.md`.

## 1. Purpose

This document defines the design of the **Search & Vector Search** capabilities of AI_OS.

These capabilities allow the platform to retrieve relevant documents, code, knowledge items, and memory items using both traditional (keyword / structured) search and semantic (vector) search. They are primarily consumed by the Context Manager, Knowledge Manager, and Memory Manager.

This document is subordinate to:

1. Project Constitution  
2. System Architecture  
3. Kernel Architecture  
4. Knowledge Manager Design  
5. Memory Manager Design  
6. Context Manager Design  

---

## 2. Design Goals

Search & Vector Search must:

- Provide relevant results with low latency
- Support both keyword/structured and semantic retrieval
- Be backend-agnostic (different vector stores or search engines can be plugged in)
- Integrate cleanly with Knowledge and Memory systems
- Support filtering by metadata (project, pack, type, time, etc.)
- Be observable and controllable

---

## 3. Core Responsibilities

- Index content from Knowledge Manager, Memory Manager, documentation, and other approved sources
- Provide keyword / full-text search
- Provide vector (semantic) search
- Support hybrid search (combination of keyword + vector)
- Apply metadata filters and access controls
- Return ranked results with provenance
- Support incremental indexing and updates

---

## 4. High-Level Structure

```text
Search & Vector Search           (PostgreSQL 16 + pgvector — ADR-0013)
│
├── Indexing Pipeline            deterministic, versioned chunk_strategy_version
├── Keyword Search               Postgres FTS: tsvector + GIN
├── Vector Search                pgvector HNSW, cosine distance
├── Hybrid Ranker                Reciprocal Rank Fusion (no score normalisation
│                                 needed between two incomparable scorers)
├── Metadata Filter              SQL predicates
├── Access Control               applied AS SQL PREDICATES, not post-filtering
└── Observability Hook
```

Decided in [ADR-0013](../../18_decision_log/adr/ADR-0013-search-and-vector-store.md): one stateful system, transactional consistency between chunk metadata and vectors, and permission trimming that cannot leak through ranking.

**Embeddings are generated only through the LLM Gateway** ([ADR-0002](../../18_decision_log/adr/ADR-0002-llm-gateway-single-entry-point.md)) — never by direct provider calls from this service, which would create a second unaccounted egress path.

**Reproducibility requirements.** Every vector records `embedding_model_id`, `embedding_model_version`, and `dimensions`; queries compare only vectors from the same model and version. `index_generation` is pinnable in a request so an experiment retrieves against a fixed index while ingestion continues. Chunking is deterministic and its strategy version is stored per chunk.

**Scale trigger for a dedicated vector store (Qdrant behind the same `VectorIndex` Protocol):** > ~20 M chunks, or p95 vector latency > 200 ms at target concurrency, or measurable contention with transactional load.

---

## 5. Key Design Rules

- Indexing must preserve provenance (source document / ID / version).
- Search results must be usable by the Context Manager (i.e., return identifiable, permission-aware items).
- Vector embeddings and models used for embedding must be configuration-driven.
- Different content types may use different indexing strategies.
- Capability Packs should not embed their own independent search stacks when the platform service can be used.

---

## 6. Relationship with Other Components

- **Knowledge Manager** and **Memory Manager** are the primary sources of content to index.
- **Context Manager** is the primary consumer of search results when assembling context for agents.
- **Configuration Manager** controls embedding models, index settings, and backend selection.
- **Security Manager** enforces access control on searchable content.
- **Observability** records search queries and performance metrics.
- **Evaluation Engine** may use search quality as an indirect signal in some experiments.

---

## 7. Observability Requirements

Search operations should record:

- Query type (keyword / vector / hybrid)
- Latency
- Number of results
- Filters applied
- Correlation with Workflow ID / Trace ID when applicable

---

## 8. Current Status

This document defines the design baseline for Search & Vector Search.

Concrete technology choices (vector database, embedding models, full-text engine), indexing pipelines, and ranking strategies will be refined during implementation.

---

## 9. Final Authority

Order of precedence:

1. Project Constitution  
2. System Architecture  
3. Kernel Architecture  
4. Search & Vector Search Design  
5. Source Code
