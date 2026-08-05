# ADR-0025: Caching — Redis for Platform Caches, Provider Prompt Caching for Model Calls

**Status:** Accepted
**Date:** 2026-07-25
**Decision Makers:** Chief Architect
**Related Documents:** `docs/03_architecture/services/caching_strategy.md`, `docs/03_architecture/kernel/llm_gateway.md`

---

## Context

The Caching Strategy identified where caching would help but named no technology and, more importantly, did not resolve the tension between caching and the platform's evaluation goals: a cached model response served during an experiment would silently corrupt the comparison it is meant to measure.

## Decision

**Two distinct mechanisms, with an explicit rule about experiments.**

**1. Redis 7 for platform caches.** Behind a `Cache` Protocol, with an in-memory adapter for tests. Used for: resolved configuration, resolved secrets (TTL-bounded, in-memory only — see [ADR-0024](ADR-0024-secrets-management-backend.md)), parsed and chunked documents keyed by content hash, retrieval results, pack registry metadata, and API rate-limit counters. Redis is also the transport Part 3 of [ADR-0012](ADR-0012-event-bus.md) adopts, so it is one dependency serving several needs rather than a new one.

Every cache entry declares a TTL and an invalidation trigger. Cache keys include every input that affects the result — for document processing, the content hash and the chunk-strategy version; for retrieval, the query, filters, index generation, and embedding model version. A key that omits an input is a correctness bug, not a tuning issue.

**2. Provider prompt caching for model calls, via the Gateway.** Rather than caching whole responses, the Gateway exploits provider-side prompt caching: stable prefix content (system prompt, tool definitions, invariant context) is marked cacheable, and volatile content (the specific task, the current step's data) is placed after the last cache breakpoint. This is materially cheaper than uncached input and, critically, **does not change model behaviour** — the model still runs, so output remains a genuine model output.

Because provider prompt caching is prefix-matched, the Gateway must keep prefix bytes stable: tool definitions are serialised deterministically, no timestamps or run IDs are interpolated into the system prompt, and per-request identifiers go after the breakpoint. Cache-read and cache-write token counts are recorded as first-class metrics so caching effectiveness is measurable rather than assumed.

**3. Response caching is off by default and prohibited in experiments.** A full response cache (identical request → stored response, no model call) is available for local development and for retrying an interrupted run, but:
- it is **disabled by default**;
- it is **unconditionally disabled for any run belonging to an experiment**, enforced in the Gateway rather than left to configuration discipline;
- when a response is served from cache, the run record is flagged `served_from_cache=true`, and the Evaluation Engine excludes such runs from comparison results.

This is stated as a hard rule because a silently cached response is the single easiest way to produce benchmarking numbers that look excellent and mean nothing.

## Alternatives Considered

- **Memcached** — Simpler; rejected: no streams, no sorted sets for rate limiting, no persistence option, and Redis is needed anyway.
- **In-process caching only** — Rejected: does not survive restarts and cannot be shared across API and worker replicas ([ADR-0020](ADR-0020-deployment-topology-and-scaling.md)).
- **Aggressive response caching on by default** — Rejected for the experiment-contamination reason above; the cost saving is not worth invalidating the platform's core measurement claim.
- **No caching at all** — Rejected: prompt caching is a large, safe cost reduction on the repeated-prefix workloads that dominate agent execution, and document re-parsing is pure waste.

## Consequences

### Positive
- Meaningful cost reduction on model calls without altering model behaviour.
- Cache effectiveness is measured, not assumed.
- Experiment integrity is protected by an enforced rule rather than by a convention.
- One additional dependency serving caching, rate limiting, and the future event transport.

### Negative
- Redis becomes a required production dependency (though not a system of record — it can be lost without data loss).
- Prefix stability is a real constraint on prompt construction and must be tested, or caching silently stops working.

### Neutral
- Cache hit/miss rates and cache-token counts are exposed on the Dashboard alongside cost.

## Compliance

Complies with the Caching Strategy (configurable, observable, explicit invalidation, no cross-model mixing) and [ADR-0022](ADR-0022-reproducibility-over-determinism.md).

## References

- `docs/03_architecture/services/caching_strategy.md`

---

## Implementation Status (appended 2026-07-28 — not part of the Accepted decision; updated 2026-08-05)

**Status in code:** §3 (response cache) partially real; §1 (platform caches) not yet implemented; §2 (provider prompt caching) now real end to end for `system` content.

`kernel/src/ai_os_kernel/caching/` now has a real Redis client (`P02-S07-M23-T01`) and a real `ResponseCache` (`P02-S07-M23-T02`): identical-request → stored-response caching over real `LLMRequest`/`LLMResponse`, with §3's "unconditionally disabled for experiments" rule enforced structurally — `LLMRequest.metadata.experiment_id` (a real, disclosed addition this same step) gates every cache read and write, proven against a real Redis container, not merely satisfied by the feature's prior absence. `LLMResponse.served_from_cache` is real too, defaulting `False`. `P02-S03-M07-T06`: §2's own "stable prefix... volatile suffix" split has a real computation on the Prompt Engine side — `kernel/src/ai_os_kernel/prompt_engine/cache_boundary.py`'s `render_with_cache_boundary()`, a real `{{cache_boundary}}` marker the template author places explicitly (no automatic heuristic exists or was invented), with the reported index computed on real rendered text, not the raw template. **Updated 2026-08-05 (`P02-S02-M06-T12`):** the Gateway side is real too — `llm_gateway/prompt_cache_planner.py`'s `plan_prompt_cache_segments()` consumes that real index, and `AnthropicAdapter` (its one real consumer) places a genuine `cache_control: {"type": "ephemeral"}` breakpoint on the stable `system` segment, verified against the installed `anthropic` SDK's real types and proven end to end against a real local server capturing the actual outgoing wire-format request body. Scope: `system` only, `AnthropicAdapter` only — `messages`-level breakpoints and other providers are not built. Not yet done: no `Cache` Protocol; no cached configuration, secrets, documents, retrieval results, or rate-limit counters (§1); the capability negotiator still only models `supports_prompt_caching`/`prompt_cache_min_tokens` as provider metadata, not yet cross-checked against a request that sets a real boundary; `ResponseCache` itself is not wired into `llm_gateway.gateway`'s real call path yet, so no real Gateway call is served from *response* cache today (distinct from the *prompt* cache breakpoint now real above).

Live status: [`feature_inventory.md`](../../19_roadmap/feature_inventory.md) · Build history: [`history/INDEX.md`](../../19_roadmap/history/INDEX.md)
