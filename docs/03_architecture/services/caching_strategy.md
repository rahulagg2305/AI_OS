# Caching Strategy – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Caching Strategy  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## 1. Purpose

This document defines the caching strategy for AI_OS.

Caching is used to improve performance, reduce cost (especially LLM and expensive search operations), and lower latency while preserving correctness and observability.

This document is subordinate to:

1. Project Constitution  
2. System Architecture  
3. Kernel Architecture  
4. Configuration Manager Design  
5. Coding Standards & Best Practices  

---

## 2. Design Goals

Caching in AI_OS must:

- Improve performance and reduce redundant work
- Be safe (avoid serving incorrect or stale data where correctness matters)
- Be configurable
- Be observable
- Support explicit invalidation
- Avoid hidden complexity and debugging difficulty

---

## 3. Caching Principles

**Technology: Redis 7** behind a `Cache` Protocol, with an in-memory adapter for tests ([ADR-0025](../../18_decision_log/adr/ADR-0025-caching-strategy.md)).

**Two distinct mechanisms, which must not be confused:**

1. **Platform caches (Redis)** — resolved configuration, resolved secrets (TTL-bounded, in-memory), parsed/chunked documents keyed by content hash, retrieval results, pack registry metadata, rate-limit counters.
2. **Provider prompt caching (via the LLM Gateway)** — marks a stable prompt prefix as cacheable. Materially cheaper input tokens and, crucially, **does not change model behaviour**: the model still runs, so output remains a genuine model output.

**The rule that protects the product claim:** a full **response cache** (identical request → stored response, no model call) is **off by default** and **unconditionally disabled for any run belonging to an experiment**, enforced in the Gateway rather than left to configuration discipline. When a response is served from cache the run is flagged `served_from_cache=true` and excluded from comparison aggregates. A silently cached response is the easiest way to produce benchmarking numbers that look excellent and mean nothing.

**Key construction rules:**
- Keys include **every** input affecting the result. For document processing: content hash + `chunk_strategy_version`. For retrieval: query + filters + `index_generation` + embedding model version. A key omitting an input is a correctness bug, not a tuning issue.
- Prompt-cache prefixes must be **byte-stable**: tool definitions serialised deterministically, no timestamps or run IDs in the system prompt. An unsorted serialisation silently destroys hit rate.
- Every entry declares a TTL and an invalidation trigger.
- Hit/miss rates and cache-token counts are recorded, so effectiveness is measured rather than assumed (NFR-043).

---

## 4. Major Caching Opportunities

### 4.1 LLM Gateway
- Cache responses for identical requests when experiments or workflows intentionally allow it (careful with non-determinism).
- Useful for retries and for repeated identical calls during development.

### 4.2 Search & Vector Search
- Cache frequent queries and their results (with appropriate invalidation when indexes change).

### 4.3 Document Processing
- Cache parsed / chunked versions of documents that have not changed.

### 4.4 Context Assembly
- Cache parts of context that are stable within a workflow or experiment when safe.

### 4.5 Configuration
- Cache resolved configuration values with invalidation on change.

### 4.6 Knowledge & Memory Retrieval
- Cache frequent retrievals with proper invalidation.

---

## 5. Key Design Rules

- Cache keys must incorporate all parameters that affect the result.
- For multi-LLM experiments, caching must not accidentally mix results from different models.
- Invalidation must be reliable; stale data is often worse than no cache.
- Caching layers should be transparent to most callers (they call the service, the service decides whether to use cache).
- Capability Packs should not implement their own uncontrolled caching of platform-level concerns.

---

## 6. Relationship with Other Components

- **LLM Gateway**, **Search**, **Document Processing**, **Knowledge Manager**, **Memory Manager**, and **Configuration Manager** are the primary candidates for caching.
- **Configuration Manager** controls cache enablement and parameters.
- **Observability** must report cache hit/miss rates and latency benefits.
- **Evaluation Engine** needs clear visibility when results were served from cache (especially during experiments).

---

## 7. Observability Requirements

Caching layers should emit:

- Hit / miss metrics
- Latency with and without cache
- Invalidation events
- Correlation with Workflow ID / Trace ID when applicable

---

## 8. Current Status

This document establishes the baseline caching strategy.

Concrete cache implementations, key designs, TTLs, and invalidation mechanisms will be refined during implementation of the individual services.

---

## 9. Final Authority

Order of precedence:

1. Project Constitution  
2. System Architecture  
3. Kernel Architecture  
4. Caching Strategy  
5. Source Code
