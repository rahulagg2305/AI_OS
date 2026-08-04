# LLM Gateway Architecture – AI_OS

**Project:** AI_OS (AI Operating System)
**Document:** LLM Gateway Architecture
**Version:** 2.1
**Status:** Approved
**Last Updated:** 2026-07-28 (§15: corrected a dead reference to a non-existent `platform_sdk/contracts/llm.py` — no other content changed)

---

## 1. Purpose

The LLM Gateway is the **only** component in AI_OS permitted to communicate with a model provider. It keeps the platform LLM-agnostic, centralises cost and reliability control, and produces the measurements that make multi-LLM comparison credible.

Governing decision: [ADR-0002](../../18_decision_log/adr/ADR-0002-llm-gateway-single-entry-point.md).

This document is subordinate to:

1. Project Constitution
2. AI Governance Framework
3. System Architecture
4. Kernel Architecture
5. Capability Pack Contract

Version 2.0 adds the tool-calling, structured-output, streaming, capability-negotiation, and embedding contracts that were previously unspecified.

---

## Implementation Status (2026-07-28; models.py contract updated 2026-08-04; Rate Limiter added 2026-08-04; count_tokens()/embed()/stream() added 2026-08-04)

**Built:** `kernel/src/ai_os_kernel/llm_gateway/` (12 modules) plus `adapters/` (`anthropic_adapter.py`, `local_adapter.py`, `model_config.py`). Real: the `LLMGateway` Protocol and `DispatchingLLMGateway` (`gateway.py`); `complete()`; the `StaticRouter` with per-alias `RoutingDecision` and real multi-candidate fallback chains via `build_routing_chain` (`router.py`), driven by `config/llm.yaml`; the Capability Negotiator matrix and its degradation rules (`capability_negotiator.py`); the Retry & Fallback Manager as three cooperating modules — `error_taxonomy.py` (mapping provider errors into the platform's single taxonomy, §10), `backoff.py` (exponential with jitter), `circuit_breaker.py` (per-provider open/half-open); the request/response contracts of §4 and §5 (`models.py`); `budget_enforcer.py`; `call_recorder.py`; `ids.py`; `errors.py`. `AnthropicAdapter` and `LocalAdapter` are both real and network-calling. Composition happens in `kernel/src/ai_os_kernel/bootstrap.py`, which builds the router from `config/llm.yaml` and merges adapters into one `DispatchingLLMGateway`. `models.py`'s contract gained real, additive fields/types across several steps: `TraceContext.experiment_id`/`LLMResponse.served_from_cache` (`P02-S07-M23-T02`); `EmbeddingRequest`/`EmbeddingResponse` (`P02-S02-M06-T09`); `LLMStreamEvent`/`StreamEventType` (`P02-S02-M06-T08`) — every existing caller is unaffected. **A real, proactive, per-provider Rate Limiter** (`P02-S02-M06-T11`, `rate_limiter.py`): `RateLimiter` Protocol + `RedisRateLimiter` (fixed-window `INCR`/`EXPIRE`, reusing the real Redis client `P02-S07-M23-T01` built), wired into `DispatchingLLMGateway` as an optional collaborator, checked right after the budget gates and before the Circuit Breaker; a rejection classifies `RATE_LIMIT_EXCEEDED` with a real `retry_after_seconds`, honoured by backoff and fallback traversal like any provider-scoped failure. **`count_tokens()` is real** (`P02-S02-M06-T10`): `AnthropicAdapter.count_tokens()` calls the real `POST /v1/messages/count_tokens` endpoint (§12). **`embed()` is real** (`P02-S02-M06-T09`): `LocalAdapter.embed()` calls the real, standard OpenAI-compatible `POST /v1/embeddings` endpoint — Anthropic's own real API has none. **`stream()` is real** (`P02-S02-M06-T08`): `AnthropicAdapter.stream()` calls the real Anthropic streaming endpoint (`messages.create(..., stream=True)`), yielding §4.3's own normalised `LLMStreamEvent` set (Anthropic's real `content_block_*` event names mapped to §4.3's shorter `content_*` names; a real keep-alive `ping` silently skipped; `usage` genuinely populated only on `message_delta`, matching what the real API actually sends). `count_tokens()`/`embed()`/`stream()` are each kept off the bare `LLMGateway` Protocol via their own new `@runtime_checkable` Protocol (`TokenCounter`/`Embedder`/`Streamer`) — not every real adapter can honestly answer any of the three — and `DispatchingLLMGateway` dispatches to each via `isinstance`, resolving the alias once and **never walking the fallback chain**: a token count/embedding/stream is specific to the one real, primary resolved model (a fallback's tokenizer, vector space, or already-partially-delivered stream content would be a real, wrong substitute, not a valid alternative).

**Not built:** `count_tokens()`/`embed()`/`stream()` are each real for exactly one provider (`AnthropicAdapter`, `LocalAdapter`, `AnthropicAdapter` respectively) — no adapter implements all three, and neither `LocalAdapter` nor `EchoLLMGateway` streams or counts tokens. §12's own "cached by content hash and model" clause is not built for `count_tokens()` (every call is a real, uncached round trip). `complete()` does **not** internally stream for large `max_output_tokens` as §4.3 also describes — that remains real, disclosed follow-up work, a deliberate, narrower scope than §4.3's own full stated behavior (a product-owner decision, not an oversight). **The per-provider Rate Limiter is real; the per-principal rate-limit row in §9 is a genuinely different, still-open axis** — nothing keys a rate ceiling by principal today, only by provider. `RedisRateLimiter`'s real per-provider numeric limits are not decided or wired into the real composition root (`kernel/bootstrap.py`) yet — that would mean adding real Redis construction to Kernel startup and deciding real, operator-verifiable per-provider request-volume ceilings in `config/llm.yaml`. **2 of §9's 5 pre-call checks are real** (per-alias and per-workflow budget ceilings); the per-experiment ceiling, the allowed-model policy check, and the context-window-fit pre-check are not. **No Prompt Cache Planner** — §8's breakpoint placement is unimplemented, and `cache_boundary_index` is not produced by the Prompt Engine either. **A real Response Cache now exists (`ai_os_kernel.caching.response_cache.ResponseCache`, `P02-S07-M23-T02`) but is not wired into `gateway.py`'s real call path** — no real Gateway call is served from cache today. No **Request Validator** as a distinct component; no **Response Normalizer** beyond what each adapter returns directly. Tool-calling (§4.1) and structured-output emulation (§4.2) exist as models but are not exercised end to end. §13's `evaluation.llm_calls` row: the table and `call_recorder.py` exist, but the Evaluation Engine that consumes them does not. Only `anthropic` is registered by default — `LocalAdapter` and cross-provider fallback are real but commented out in checked-in configuration. §14's shared adapter conformance suite does not exist (`tests/contract/` does not exist at all).

**One enforcement claim in §2 is currently false and is flagged there:** the import-boundary check is present in `.github/workflows/ci.yml` but **gated off** — it runs only `if hashFiles('scripts/check_import_boundaries.py') != ''`, and that script does not exist. The adapter-only import rule is therefore convention today, not enforcement.

Authoritative, always-current status: `../../19_roadmap/feature_inventory.md` (per-module completion table) and `../../19_roadmap/implementation_status.md`. Detailed build history: `../../19_roadmap/history/INDEX.md` (specifically `006_llm_gateway_and_prompt_engine_foundation.md`, `008_first_real_llm_integration_and_prompted_agent.md`, `011_llm_gateway_advanced_router_retry_budget.md`).

---

## 2. Scope — what passes through the Gateway

**All of it.** Generation, tool-using generation, structured output, streaming, token counting, **and embeddings**. Embeddings are included deliberately: they are provider calls with cost and dimensionality consequences, and excluding them would create a second, unaccounted egress path ([ADR-0013](../../18_decision_log/adr/ADR-0013-search-and-vector-store.md)).

Provider SDKs may be imported **only** inside `kernel/src/ai_os_kernel/llm_gateway/adapters/` (this document previously gave the path as `kernel/llm_gateway/adapters/`, which does not exist — the package root is `kernel/src/ai_os_kernel/`). The rule is intended to be enforced by an import-boundary check in CI rather than by convention. **Accuracy note (2026-07-28): that enforcement is not yet live.** `.github/workflows/ci.yml` declares an "Import boundary check" step, but it is conditioned on `hashFiles('scripts/check_import_boundaries.py')` and that script does not exist, so the step never runs. Today the boundary holds by convention only; building the checker is the named gap that makes this paragraph true.

---

## 3. Internal Structure

```text
Agent / Workflow Engine / Context Manager / Search Service
                    │
                    ▼
        LLMGateway (SDK Protocol)
                    │
    ├── Request Validator          schema, budget, allowed-model policy
    ├── Capability Negotiator      matrix lookup, emulate or fail
    ├── Policy & Budget Enforcer   per-step, per-workflow, per-experiment
    ├── Router                     alias → provider/model, fallback chain
    ├── Prompt Cache Planner       prefix/suffix split, breakpoint placement
    ├── Provider Adapters          the ONLY place a provider SDK is imported
    │      ├── anthropic_adapter
    │      ├── <other provider adapters>
    │      └── local_adapter
    ├── Retry & Fallback Manager   backoff, circuit breaker, chain traversal
    ├── Rate Limiter               per provider, per principal
    ├── Response Normalizer        → neutral ContentBlock[]
    ├── Token & Cost Accountant    the single source of spend truth
    └── Observability              span, metrics, evaluation.llm_calls row
```

---

## 4. Request Contract

```text
LLMRequest
    model_alias: str                       # REQUIRED. Never a literal model id.
    messages: Message[]
    system: SystemBlock[] | None
    tools: ToolDefinition[] | None
    tool_choice: auto | any | none | {tool: name} | None
    response_format: JsonSchemaFormat | None
    thinking: adaptive | disabled | None
    effort: low | medium | high | xhigh | max | None
    max_output_tokens: int
    stream: bool = False
    cache_hints: CacheHint[] | None
    metadata: TraceContext                 # trace, workflow, step, agent, experiment
    budget: StepBudget | None
    timeout_seconds: float | None
    require_capabilities: str[] | None     # fail rather than degrade
```

**Sampling parameters are deliberately absent.** `temperature`, `top_p`, and `top_k` are not fields on this contract: current frontier models reject them, and behaviour is steered by prompt content and `effort` instead. An adapter for an older model that still accepts them may set provider defaults internally, but they are never part of the platform-neutral request — which prevents a per-provider parameter from silently becoming an uncontrolled experiment variable.

**Assistant-turn prefill is not supported.** Current models reject it. Output shaping uses `response_format` or an explicit system instruction.

### 4.1 Tool definitions and tool calls

The contract that makes tool-using agents portable:

```text
ToolDefinition        name; description; input_schema (JSON Schema);
                      strict: bool = True

ToolCall              call_id; name; arguments (parsed object)
ToolResultBlock       call_id; content; is_error: bool
```

Rules:
- `arguments` is always **parsed**, never a raw string. Adapters differ in escaping; the platform never string-matches serialised tool input.
- Parallel tool calls are supported where the provider supports them. When multiple calls are returned, **all** results are returned together in one turn — splitting them degrades the provider's future parallel-call behaviour.
- A failed tool returns a `ToolResultBlock` with `is_error=True`, never a dropped result. A missing result for an issued call is a protocol violation the Gateway rejects.
- `strict: True` requests provider-side schema enforcement where available; where unavailable, the Gateway validates the returned arguments and retries once with a corrective message before failing.

### 4.2 Structured output

```text
JsonSchemaFormat      schema (JSON Schema draft 2020-12); name
```

Where the provider supports native structured output, it is used. Where it does not, the Gateway emulates it with a single forced tool call whose input schema is the requested schema — a faithful emulation. If neither is possible, the request fails with `llm.capability_unsupported` rather than silently returning unvalidated text.

### 4.3 Streaming

```text
LLMStreamEvent        type: message_start | content_start | content_delta |
                            content_stop | message_delta | message_stop | error
                      index; delta; content_block?; usage?
```

Streaming is normalised across providers into this event set. Usage totals arrive on `message_delta`/`message_stop`. Consumers that do not need incremental output call `complete()`, which internally streams for large `max_output_tokens` to avoid request timeouts and returns the assembled response.

---

## 5. Response Contract

```text
LLMResponse
    content: ContentBlock[]                # text | tool_call | thinking
    stop_reason: end_turn | max_tokens | tool_use | refusal | pause_turn
    stop_details: {category, explanation} | None
    usage: UsageRecord
    provider: str
    model_id: str
    model_version: str
    served_from_cache: bool
    degradations: Degradation[]             # capabilities emulated or unavailable
    raw: object | None                      # debug only, never logged

UsageRecord
    input_tokens; output_tokens
    cache_read_tokens; cache_write_tokens
    cost_usd; latency_ms
    provider; model_id
    retries; fallback_used: bool
```

**`stop_reason` must be checked before reading `content`.** A `refusal` returns a successful HTTP response with empty or partial content; code that indexes `content[0]` unconditionally breaks. The Gateway surfaces a refusal as a distinct outcome with its category, not as a generic error, because a refusal and a failure require different handling — a refusal is a policy decision about the request, not a fault.

---

## 6. Capability Negotiation

Providers differ materially. The Gateway maintains a per-alias capability matrix:

```text
ProviderCapabilities
    supports_tools; supports_parallel_tool_calls; supports_strict_tools
    supports_structured_output
    supports_streaming
    supports_thinking; supports_effort
    supports_prompt_caching; prompt_cache_min_tokens
    supports_vision
    max_input_tokens; max_output_tokens
    accepts_sampling_params
```

**Degradation rules, in order:**

1. If the capability is supported → use it.
2. If it can be **faithfully emulated** → emulate, and record a `Degradation` on the response and in telemetry.
3. If it cannot → fail with `PermanentError(error_code="llm.capability_unsupported")`.
4. If the caller listed the capability in `require_capabilities` → never emulate; fail immediately.

A capability is **never silently dropped.** This matters beyond correctness: a silent downgrade would make two models in an experiment run under different conditions while appearing identical, invalidating the comparison.

---

## 7. Routing and Aliases

Model selection is **always** by alias. Callers never name a provider or model.

```yaml
# config/llm.yaml
aliases:
  reasoning:
    chain:
      - {provider: anthropic, model: claude-opus-5, effort: high}
      - {provider: anthropic, model: claude-opus-4-8}
  coding-strong:
    chain:
      - {provider: anthropic, model: claude-opus-5, effort: xhigh}
  coding-balanced:
    chain:
      - {provider: anthropic, model: claude-sonnet-5}
  fast-cheap:
    chain:
      - {provider: anthropic, model: claude-haiku-4-5}
  embedding-default:
    chain:
      - {provider: <configured>, model: <configured>, dimensions: 1536}
```

Routing inputs: the alias chain, provider health (circuit-breaker state), rate-limit headroom, budget policy, and — decisively — **experiment pinning**. When a request carries an `experiment_id`, the experiment's pinned model overrides ordinary routing, and fallback is disabled unless the experiment declares it, because a silent fallback mid-experiment would substitute a different model than the one being measured.

*Naming correction (2026-07-28): earlier revisions attributed the pin to an "Experiment Manager." No such component exists or is to be built — `evaluation_engine.md` §5.1 explicitly decides against one. The pin's real owners are the Benchmarking Pack (which defines the experiment), the Configuration Manager's isolated experiment-override layer (`configuration_manager.md` §4, layer 6), and this component (which applies it). None of the three is built: there is no experiment mechanism anywhere in the codebase, so experiment pinning is specified and unimplemented.*

---

## 8. Prompt Caching

Provider prompt caching is prefix-matched, which imposes a real constraint the Gateway must honour ([ADR-0025](../../18_decision_log/adr/ADR-0025-caching-strategy.md)):

- Stable content (system prompt, tool definitions, invariant context) is placed **before** the cache breakpoint; volatile content (the current task, per-request identifiers) after it.
- Tool definitions are serialised **deterministically** (sorted keys, stable ordering). An unsorted serialisation silently destroys cache hits.
- No timestamp, UUID, or run identifier is interpolated into the system prompt.
- `cache_read_tokens` and `cache_write_tokens` are recorded per call, so cache effectiveness is measured rather than assumed. A collapse in hit rate is an alertable condition (NFR-043).
- Response caching (returning a stored response without calling the model) is **off by default and unconditionally disabled for experiment runs**, enforced here rather than left to configuration discipline.

---

## 9. Budgets and Policy

Enforced before the provider call:

| Check | Failure |
|---|---|
| Step budget (tokens, cost, tool calls) | `BudgetExceededError` |
| Workflow cost ceiling | `BudgetExceededError` |
| Experiment cost ceiling | Refuses to start the run |
| Allowed-model policy | `SecurityError` |
| Per-principal rate limit | `TransientError` with `retry_after_seconds` |
| Context window fit | `PermanentError` — before spending anything |

Cost is computed from recorded per-model pricing in configuration, and the Gateway is the **only** producer of cost data. One producer means cost is reconcilable; several would mean it is not.

---

## 10. Error Taxonomy

The Gateway maps every provider error into the platform's single taxonomy (`../workflow/error_handling_retry.md`). There is no second, Gateway-specific taxonomy:

| Provider condition | Category | `error_code` | Retriable |
|---|---|---|---|
| Network failure, timeout | `transient` | `llm.network` | Yes |
| Rate limited (429) | `transient` | `llm.rate_limited` | Yes, after `retry_after` |
| Overloaded (529) | `transient` | `llm.overloaded` | Yes |
| Server error (5xx) | `transient` | `llm.provider_error` | Yes |
| Authentication (401/403) | `infrastructure` | `llm.auth_failed` | No |
| Invalid request (400) | `permanent` | `llm.invalid_request` | No |
| Context window exceeded | `permanent` | `llm.context_exceeded` | No |
| Capability unsupported | `permanent` | `llm.capability_unsupported` | No |
| Model refused the request | `permanent` | `llm.refusal` | No — surfaced with category |
| Budget exceeded | `budget` | `llm.budget_exceeded` | No |
| All providers in chain failed | `transient` | `llm.chain_exhausted` | Yes, with backoff |

Retry policy: exponential backoff with jitter, bounded attempts and total time, honouring `retry_after` when provided. A circuit breaker opens per provider after a configured consecutive-failure count and half-opens on a timer. The Gateway owns provider-level retry; the Workflow Engine owns step-level retry — a single boundary, so retries cannot multiply.

---

## 11. Embeddings

```text
EmbeddingRequest      model_alias; inputs: str[]; metadata: TraceContext
EmbeddingResponse     vectors: float[][]; model_id; model_version;
                      dimensions; usage: UsageRecord
```

Every stored vector records `embedding_model_id`, `embedding_model_version`, and `dimensions`; queries only compare vectors from the same model and version. Changing the embedding model requires a re-index and is a tracked migration ([ADR-0013](../../18_decision_log/adr/ADR-0013-search-and-vector-store.md)).

---

## 12. Token Counting

Token counts come **only** from provider token-counting endpoints, via `count_tokens()`. A third-party or foreign-provider tokenizer is never used: counts are model-specific, and an approximation would corrupt both budget enforcement and cost reporting. Counts are cached by content hash and model.

---

## 13. Observability

Every call emits a span and writes one `evaluation.llm_calls` row containing: workflow, step, agent, prompt ID and version, alias, resolved provider and model, input/output/cache tokens, cost, latency, stop reason, retries, `fallback_used`, and any degradations.

Metrics: `aios.llm.requests`, `.tokens`, `.cost_usd`, `.latency_ms`, `.retries`, `.fallbacks`, `.cache_hit_ratio`, `.refusals`, `.degradations`.

**Never emitted:** API keys, full prompt bodies containing customer source code (prompt *identity and version* are recorded, content is not), or raw provider responses.

---

## 14. Adding a Provider

1. Implement the adapter Protocol in `kernel/src/ai_os_kernel/llm_gateway/adapters/`.
2. Declare its `ProviderCapabilities`.
3. Add pricing to configuration.
4. Pass the shared adapter conformance suite (the same suite every adapter passes).
5. Add the alias mapping (`config/llm.yaml`, read by `kernel/src/ai_os_kernel/bootstrap.py`).

No change to any agent, pack, or workflow. That property is the point of the whole component (`../../02_requirements/non_functional/nfr.md`, NFR-101) and it has been exercised for real once: `LocalAdapter` was added as a second provider without touching any agent, pack, or workflow.

**Step 4 is currently unsatisfiable and is the named gap in this procedure:** no shared adapter conformance suite exists. `tests/contract/` does not exist at all, and CI's contract stage is gated off (`if hashFiles('tests/contract/**') != ''`). Both existing adapters have their own hand-written unit tests (`tests/unit/kernel/llm_gateway/adapters/`) rather than a shared suite, so "the same suite every adapter passes" is aspirational until that suite is written.

---

## 15. Current Status

This document specifies the Gateway contract for v1.

**Corrected reference (2026-07-28):** this section previously said concrete signatures "live in `platform_sdk/contracts/llm.py`" — that file does not exist; `platform_sdk/` currently contains only `schemas/manifest.schema.json` (confirmed by direct inspection during a documentation-reconciliation pass). The real, concrete signatures for everything this document specifies live in `kernel/src/ai_os_kernel/llm_gateway/` (`models.py`, `gateway.py`, `router.py`, `capability_negotiator.py`, `error_taxonomy.py`, `circuit_breaker.py`, `backoff.py`, `budget_enforcer.py`) — this document governs those, until a real `platform_sdk` contracts package is built to hold a Platform-SDK-facing copy of them (tracked in `docs/19_roadmap/implementation_status.md`, alongside the pack-facing `ai-os-sdk` package this same document's own capability-pack-facing gap refers to).

---

## 16. Final Authority

Order of precedence:

1. Project Constitution
2. AI Governance Framework
3. System Architecture
4. Kernel Architecture
5. Architecture Decision Records
6. LLM Gateway Architecture (this document)
7. Source Code

---

## 17. Related Documents

**Governing decisions (ADRs):**
- [ADR-0002 — LLM Gateway Single Entry Point](../../18_decision_log/adr/ADR-0002-llm-gateway-single-entry-point.md) — the governing decision for this component
- [ADR-0013 — Search and Vector Store](../../18_decision_log/adr/ADR-0013-search-and-vector-store.md) — why embeddings pass through this Gateway (§2, §11)
- [ADR-0025 — Caching Strategy](../../18_decision_log/adr/ADR-0025-caching-strategy.md) — prompt-cache breakpoints (§8), response caching off for experiments
- [ADR-0022 — Reproducibility over Determinism](../../18_decision_log/adr/ADR-0022-reproducibility-over-determinism.md) — experiment pinning, no silent fallback (§7)
- [ADR-0024 — Secrets Management Backend](../../18_decision_log/adr/ADR-0024-secrets-management-backend.md) — provider credentials as `secret://` references
- [ADR-0017 — Observability Stack](../../18_decision_log/adr/ADR-0017-observability-stack.md) — the span and metric conventions in §13
- [ADR-0015 — Testing and CI](../../18_decision_log/adr/ADR-0015-testing-and-ci.md) — the adapter conformance suite and the import-boundary check
- [ADR-0008 — Primary Language and Runtime](../../18_decision_log/adr/ADR-0008-primary-language-and-runtime.md)

**Superior documents:**
- `../platform/system_architecture.md`
- `kernel_architecture.md`
- `../capability_framework/capability_pack_contract.md` — provider SDK imports are prohibited in pack code
- `../platform/technology_stack.md`

**Interacting subsystems:**
- `prompt_engine.md` — produces the rendered prompt and the `cache_boundary_index` this Gateway consumes (§8, §12 there)
- `context_manager.md` — assembles what goes into that prompt; its `trust` tags decide what may be placed after the cache boundary
- `workflow_engine.md` — owns step-level retry; this Gateway owns provider-level retry, and §10 is the single boundary that keeps retries from multiplying
- `configuration_manager.md` — supplies `config/llm.yaml` aliases, pricing, budgets, and routing rules
- `security_manager.md` — provider credentials, allowed-model policy, per-principal rate limiting
- `evaluation_engine.md` — the sole consumer of this Gateway's cost and usage data
- `observability.md` — the telemetry conventions §13 follows
- `knowledge_manager.md` / `../services/search_vector_search.md` — consumers of `embed()` (§11), unbuilt
- `../workflow/error_handling_retry.md` — the platform's **single** error taxonomy that §10 maps into; there is no Gateway-specific taxonomy
- `../platform/platform_sdk.md` §5.1 `LLMGateway` — the pack-facing Protocol (specified, not built)

**Owned tables:**
- `../../08_database/data_model.md` §6 — `evaluation.llm_calls` is written by this component and by nothing else

**Reference:**
- `../../02_requirements/non_functional/nfr.md` — NFR-043 (cache hit-rate alerting), NFR-101 (provider substitution without pack changes)
- `../../20_glossary/glossary.md`
- `../../19_roadmap/feature_inventory.md`, `../../19_roadmap/implementation_status.md`, `../../19_roadmap/history/INDEX.md`
