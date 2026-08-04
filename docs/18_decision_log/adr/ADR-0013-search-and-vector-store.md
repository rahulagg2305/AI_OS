# ADR-0013: Search and Vector Store — PostgreSQL with pgvector and Hybrid Ranking

**Status:** Accepted
**Date:** 2026-07-25
**Decision Makers:** Chief Architect
**Related Documents:** `docs/03_architecture/services/search_vector_search.md`, `docs/03_architecture/kernel/knowledge_manager.md`

---

## Context

The Context Manager needs precise, permission-aware, reproducible retrieval over documentation, specifications, code, recovered legacy-system knowledge, and engineering memory. Reproducibility matters more here than raw recall: multi-LLM comparison is only fair if the same query returns the same context for every model in an experiment.

## Decision

**PostgreSQL 16 with the `pgvector` extension provides both keyword and vector search. No separate vector database.**

| Concern | Decision |
|---|---|
| Keyword / structured search | PostgreSQL full-text search (`tsvector`, GIN index) plus ordinary relational predicates for metadata filters. |
| Vector search | `pgvector` with HNSW indexes. Cosine distance. |
| Hybrid ranking | Reciprocal Rank Fusion (RRF) over the keyword and vector result sets, computed in the Search Service. RRF is chosen because it needs no score normalisation between two incomparable scoring systems and no tuning parameter per corpus. |
| Embeddings | Generated **only** through the LLM Gateway ([ADR-0002](ADR-0002-llm-gateway-single-entry-point.md)). Never by direct provider calls from the Search Service. |
| Embedding provenance | Every stored vector records `embedding_model_id`, `embedding_model_version`, and `dimensions`. Queries only compare vectors produced by the same model and version. Changing the embedding model requires a re-index, tracked as a migration. |
| Chunking | Deterministic and versioned (`chunk_strategy_version` stored per chunk), so retrieval is reproducible for a given index generation. |
| Access control | Applied as SQL predicates during retrieval, not as post-filtering, so permission-trimmed results cannot leak through ranking. |

**Scale trigger.** Move the vector index to a dedicated store (Qdrant, behind the same `VectorIndex` Protocol) when any of: more than ~20 million chunks in a single index; p95 vector search latency exceeds 200 ms at the target concurrency in the NFR document; or vector indexing load measurably degrades transactional workload on the primary database.

## Alternatives Considered

- **Qdrant / Weaviate / Milvus from the start** — Better vector performance at large scale and richer vector-native features. Rejected for now because it adds a second stateful system to operate, back up, and secure; forfeits transactional consistency between chunk metadata and vectors (a real correctness problem during re-indexing); and complicates permission-aware filtering, which is cleanest as a SQL predicate. pgvector with HNSW is comfortably sufficient at the documented scale.
- **Elasticsearch / OpenSearch** — Strong hybrid search in one system; rejected due to operational weight (JVM, cluster management) and because Postgres FTS covers the keyword need at this corpus size.
- **Pure vector search, no keyword** — Rejected: exact identifier lookups (a function name, an error code, a requirement ID) are common in this domain and are precisely where dense retrieval underperforms.
- **Embeddings called directly by the Search Service** — Rejected: creates a second, unaccounted provider egress path and breaks both cost accounting and LLM-agnosticism.

## Consequences

### Positive
- One stateful system for Stages A–E; transactional consistency between content, metadata, and vectors.
- Permission filtering is correct by construction.
- Retrieval is reproducible, which is a precondition for fair benchmarking.
- Backup, PITR, and security posture are inherited from the primary database.

### Negative
- Vector search shares resources with transactional load; requires index tuning and monitoring, and a read replica if contention appears.
- Re-indexing on embedding-model change is a real operational task that must be planned and rehearsed.

### Neutral
- SQLite development mode has no vector search; developers use a Postgres container for retrieval work ([ADR-0011](ADR-0011-persistence-and-workflow-state.md)).

## Compliance

Complies with `docs/03_architecture/services/search_vector_search.md` (backend-agnostic behind an interface) and the reproducibility requirement in [ADR-0022](ADR-0022-reproducibility-over-determinism.md).

## References

- `docs/08_database/data_model.md`

---

## Implementation Status (appended 2026-07-28 — not part of the Accepted decision)

**Status in code:** Partially implemented

`knowledge.documents` and `knowledge.chunks` exist with a real writer and a PostgreSQL full-text keyword-search reader (in `ai_os_kernel/persistence/`), integration-tested against the `pgvector/pgvector:pg16` image. **`embed()` is real (`P02-S02-M06-T09`) and so are a real embeddings writer (`P02-S04-M11-T03`, `ai_os_kernel.retrieval.embedding_writer`), real vector search (`P02-S04-M11-T04`, `ai_os_kernel.retrieval.vector_search.SqlVectorSearcher`), and now real Reciprocal Rank Fusion (`P02-S04-M11-T05`, `ai_os_kernel.retrieval.hybrid_search.fuse_rankings`)**: a genuine vector, produced by calling the real `embed()` for an already-real chunk, is genuinely persisted into `knowledge.embeddings`, and a real cosine-distance query over those real vectors returns a mathematically correct nearest-neighbour ranking — both proven against real Postgres/pgvector. `fuse_rankings()` combines the two real result lists with the standard fixed-`k` RRF formula this row's own "no tuning parameter per corpus" reasoning names — proven with 5 real, hand-computed-score tests showing the fused order genuinely differs from either individual ranking. Still absent: no HNSW index (the fixed-dimension decision it needs still has not been made — the real, unindexed `<=>` query answers the same question exactly, just without the index's own speed advantage at scale), no Search Service wiring both real searchers into `fuse_rankings()` end to end, and no consumer — the Context Manager does not read from any of this yet, and nothing calls either writer from a real ingestion path (no chunking/indexing pipeline exists to feed real chunk text).

Live status: [`feature_inventory.md`](../../19_roadmap/feature_inventory.md) · Build history: [`history/INDEX.md`](../../19_roadmap/history/INDEX.md)
