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

## 2. Scope — what passes through the Gateway

**All of it.** Generation, tool-using generation, structured output, streaming, token counting, **and embeddings**. Embeddings are included deliberately: they are provider calls with cost and dimensionality consequences, and excluding them would create a second, unaccounted egress path ([ADR-0013](../../18_decision_log/adr/ADR-0013-search-and-vector-store.md)).

Provider SDKs may be imported **only** inside `kernel/llm_gateway/adapters/`. This is enforced by an import-boundary check in CI, not by convention.

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

Routing inputs: the alias chain, provider health (circuit-breaker state), rate-limit headroom, budget policy, and — decisively — **experiment pinning**. When a request carries an `experiment_id`, the Experiment Manager's pinned model overrides ordinary routing, and fallback is disabled unless the experiment declares it, because a silent fallback mid-experiment would substitute a different model than the one being measured.

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

1. Implement the adapter Protocol in `kernel/llm_gateway/adapters/`.
2. Declare its `ProviderCapabilities`.
3. Add pricing to configuration.
4. Pass the shared adapter conformance suite (the same suite every adapter passes).
5. Add the alias mapping.

No change to any agent, pack, or workflow. That property is the point of the whole component (NFR-101).

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
