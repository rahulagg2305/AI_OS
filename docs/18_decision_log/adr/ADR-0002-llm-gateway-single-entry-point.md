# ADR-0002: LLM Gateway as the Single Entry Point for All Model Calls

**Status:** Accepted
**Date:** 2026-07-25
**Decision Makers:** Chief Architect, Project Owner
**Related Documents:** `docs/03_architecture/kernel/llm_gateway.md`, `docs/03_architecture/platform/platform_sdk.md`

---

## Context

AI_OS must remain LLM-agnostic, must be able to run the same work against different models for objective comparison, and must account for every token and every unit of cost. Providers differ in request shape, tool-calling semantics, structured-output support, streaming format, thinking/effort controls, sampling parameters, context limits, and error taxonomies. If those differences leak into agents or Capability Packs, provider substitution becomes a rewrite and fair benchmarking becomes impossible.

## Decision

Every model interaction — text generation, tool-using generation, structured output, streaming, **and embeddings** — passes through the Kernel's **LLM Gateway**. Provider SDKs are imported only inside Provider Adapters behind the Gateway. No agent, tool, Capability Pack, service, or Kernel component other than the Gateway may import a provider SDK or open a connection to a provider endpoint.

The Gateway exposes a provider-neutral request/response contract that includes tool definitions, tool calls, structured-output schemas, streaming, and a declared **provider capability matrix** with explicit degradation rules. Model selection is by **alias** (for example `coding-strong`, `reasoning`, `fast-cheap`), never by literal model ID, in any pack or agent.

Embeddings are included deliberately: they are provider calls with cost and dimensionality implications, and excluding them would create a second, ungoverned egress path.

## Alternatives Considered

- **A thin shared client library imported by each pack** — Less indirection; rejected because it cannot enforce budget, policy, or accounting, and nothing prevents a pack from bypassing it.
- **A third-party abstraction layer (LangChain-style)** — Faster to start; rejected because it dictates prompt, memory, and agent abstractions that conflict with the Prompt Engine, Context Manager, and Workflow Engine already specified here, and it puts a dependency we do not control on the platform's most critical path.
- **Per-provider adapters chosen by each agent** — Rejected: duplicates routing, retry, and accounting logic per agent and makes cost attribution unreliable.

## Consequences

### Positive
- Providers are replaceable through configuration; no pack or agent changes.
- Token, cost, latency, and cache accounting exist in exactly one place, which is what makes benchmarking credible.
- Budgets, rate limits, allowed-model policy, and fallback behaviour are enforceable.

### Negative
- The Gateway is on the critical path of every workflow, so it must be fast, well-tested, and carefully evolved.
- Provider-specific features are available only after being modelled in the neutral contract, so the platform lags a provider's newest capability by design.

### Neutral
- Capability negotiation means a request may be served with reduced features (for example no parallel tool calls) on a provider that lacks them; this is recorded in telemetry rather than hidden.

## Compliance

Complies with the Project Constitution (LLM Agnosticism) and the AI Governance Framework (no agent may communicate directly with an LLM provider).

## References

- `docs/03_architecture/kernel/llm_gateway.md`
- `docs/06_capability_packs/benchmarking/overview.md`

---

## Implementation Status (appended 2026-07-28 — not part of the Accepted decision)

**Status in code:** Partially implemented

The Gateway is the only provider egress path in the codebase: `AnthropicAdapter` and `LocalAdapter` sit behind `Router`/`DispatchingLLMGateway` with alias-based selection, a capability negotiator matrix, circuit breaker, backoff, a typed error taxonomy, two independent budget ceilings, and an `llm_calls` recorder for token/cost accounting. Only `anthropic` is registered by default, and three parts of the decided contract are absent: `embed()` (so there is no embedding path at all — see ADR-0013), `stream()`, and `count_tokens()`.

Live status: [`feature_inventory.md`](../../19_roadmap/feature_inventory.md) · Build history: [`history/INDEX.md`](../../19_roadmap/history/INDEX.md)
