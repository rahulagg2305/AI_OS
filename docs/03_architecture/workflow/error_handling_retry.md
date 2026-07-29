# Error Handling & Retry Strategies – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Error Handling & Retry Strategies  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## 1. Purpose

This document defines the standard error handling and retry strategies for AI_OS.

Consistent error handling is essential for reliability, observability, and predictable behaviour across Agents, Tools, Workflows, and Kernel components.

This document is subordinate to:

1. Project Constitution  
2. AI Governance Framework  
3. Workflow Architecture  
4. Agent Architecture & Agent Contract  
5. Kernel Architecture  

---

## Implementation Status (2026-07-28)

**Partially built — real inside the LLM Gateway; absent everywhere else.**

**Built:** the LLM Gateway's own `ai_os_kernel.llm_gateway.error_taxonomy.ErrorCategory` implements **4 of this document's 6 categories** — `transient`, `permanent`, `infrastructure`, `budget`. Its own docstring states plainly why `quality` and `security` are excluded: a provider call failure can never actually be either. `classify_http_status()` and `parse_retry_after_seconds()` (numeric-seconds form only, not the HTTP-date form) are real and drive the Gateway's retry/circuit-breaker/backoff logic exactly as §4's "LLM Gateway owns retry/fallback" describes.

**Not built:**
- **The `AiOsError` exception hierarchy (§8) does not exist anywhere in the codebase.** `LLMProviderError`/`LLMRefusalError` (`kernel/src/ai_os_kernel/llm_gateway/errors.py`) inherit from plain `Exception`, not from any shared base — confirmed by the Gateway's own `error_taxonomy.py` docstring, which states outright that it does not build the hierarchy this section describes. The `StructuredError` contract (§8) and the `error_code` catalogue (§3, supposedly at `platform_sdk/errors/`) have no code shape; that path does not exist because no `ai-os-sdk` package exists.
- **The Workflow Engine's own retry ownership (§4, §9) is unimplemented.** `RetryPolicy` is declared on `WorkflowStep`/`WorkflowDefinition` and validated at load time (bounded attempts + duration, per §5's own rule), but is **never read** by `service.py`, `advance_runner.py`, or `step_executor.py` — a failing step propagates as a raised exception, not a governed retry. Compensation/rollback (§6) and human escalation (§7) do not exist; `quality` and `security` errors have no producer, since the Quality Gate Engine and the Security Manager's own audit path are both largely unbuilt.

Consequence: this document's "single platform error taxonomy" is, in practice, two things — a real, narrower taxonomy inside the Gateway, and a specification for a platform-wide hierarchy nothing implements yet.

Authoritative, always-current status: `../../19_roadmap/feature_inventory.md` (module 6, LLM Gateway; module 44, `AiOsError` hierarchy) and `../../19_roadmap/implementation_status.md`. Build history: `../../19_roadmap/history/006_llm_gateway_and_prompt_engine_foundation.md`, `history/011_llm_gateway_advanced_router_retry_budget.md`.

---

## 2. Design Goals

Error handling must:

- Fail clearly and explicitly
- Distinguish between transient and permanent failures
- Support controlled retries
- Protect against infinite loops
- Preserve auditability
- Allow escalation to humans when appropriate
- Remain consistent across the platform

---

## 3. Error Categories

**This is the single platform error taxonomy.** Every component maps into it, including the LLM Gateway — there is no second, provider-specific taxonomy. v1.0 of this document defined four categories while the Gateway defined six unrelated ones with no mapping between them; the unified set is:

| Category | Meaning | Retriable | Examples |
|---|---|---|---|
| `transient` | May succeed on retry | Yes | Network timeout, rate limit, provider overload, lock contention, chain exhausted |
| `permanent` | Will not succeed with the same input | No | Invalid input, schema validation failure, context window exceeded, unsupported capability, model refusal |
| `quality` | Raised by a Quality Gate or review | No — requires corrective work | Failed build, failed tests, coverage below threshold, blocking review findings |
| `infrastructure` | Platform-side failure | Sometimes | Database unavailable, configuration missing, secret backend unreachable, provider auth failure |
| `budget` | A declared ceiling was reached | No | Step token budget, workflow cost ceiling, experiment ceiling |
| `security` | An authorization or policy denial | No | Permission denied, disallowed model, sandbox policy violation |

`budget` and `security` are separate categories rather than sub-cases of `permanent` because they require different handling: a budget failure may be resolvable by an operator raising a ceiling, and a security failure must be audited and must never be retried automatically.

Every error carries `error_code`, `category`, `retriable`, `retry_after_seconds` where applicable, and correlation identifiers. The `error_code` catalogue lives in `platform_sdk/errors/` and is the stable identifier used by dashboards and alerts.

---

## 4. Core Principles

- Prefer **fail-fast** for permanent errors.
- Use **retries with backoff** only for transient errors.
- Retries must be bounded (maximum attempts + maximum duration).
- Every retry and final failure must be observable.
- Agents should return structured errors; they should not implement complex retry logic themselves.
- The **Workflow Engine** owns retry policy for agent and step failures.
- The **LLM Gateway** owns retry/fallback logic for LLM provider calls.

---

## 5. Retry Strategy Guidelines

Recommended default pattern:

- Exponential backoff with jitter
- Clear maximum number of attempts
- Clear maximum total time
- Different policies for different error categories
- Circuit breaking when a dependency is consistently failing

Retry policies should be configurable rather than hard-coded.

---

## 6. Compensation and Rollback

When side effects have occurred and a later step fails, workflows may need compensation (Saga-style behaviour).

Rules:

- Compensation must be explicit in the workflow definition when required.
- Compensation actions must themselves be observable and auditable.
- Not every workflow requires compensation; pure functional steps may simply fail.

---

## 7. Escalation to Humans

Escalation is required when:

- Retries are exhausted on a critical path
- A mandatory Quality Gate keeps failing
- A Human Approval Point is rejected repeatedly
- The system detects an unrecoverable or ambiguous state

Escalation must create a clear Human Approval Point or notification.

---

## 8. Structured Error Contract (Conceptual)

Errors returned by Agents, Tools, and Kernel components contain:

```text
StructuredError
    error_code: str                   # stable, catalogued
    category: transient | permanent | quality | infrastructure | budget | security
    message: str                      # human-readable; never contains a secret
    retriable: bool
    retry_after_seconds: float | None
    details: dict | None
    trace: TraceContext
```

The Python exception hierarchy mirrors this exactly: `AiOsError` → `TransientError`, `PermanentError`, `QualityError`, `InfrastructureError`, `BudgetExceededError`, `SecurityError`. Each maps 1:1 onto a `StructuredError`, so there is no translation layer and no possibility of an exception whose category disagrees with its serialised form.

**Retry ownership is split at exactly one boundary:** the **LLM Gateway** owns provider-level retry and fallback; the **Workflow Engine** owns step-level retry and compensation. Nothing else retries. This prevents the multiplication that occurs when two layers each retry three times and produce nine provider calls.

---

## 9. Relationship with Other Components

- **Workflow Engine** applies retry and compensation policies at the step/workflow level.
- **LLM Gateway** handles provider-level retries and fallbacks.
- **Quality Gate Engine** surfaces quality failures.
- **Human Approval Points Framework** is used for escalation.
- **Observability** records every error, retry, and final outcome.
- **Evaluation Engine** tracks error and retry metrics for multi-LLM comparison.

---

## 10. Current Status

This document establishes the baseline error handling and retry strategy. See the Implementation Status section near the top for exactly what exists: a real, narrower 4-category taxonomy inside the LLM Gateway, and no platform-wide `AiOsError` hierarchy, error-code catalogue, or Workflow-Engine-level retry enforcement anywhere yet. Concrete policy values for whichever retry mechanism is eventually built (backoff base/max, attempt ceilings) remain a genuinely open implementation decision — the Gateway's own hardcoded constants (`kernel/bootstrap.py`) are a documented, temporary carve-out, not a settled policy.

---

## 11. Final Authority

Order of precedence:

1. Project Constitution  
2. AI Governance Framework  
3. Workflow Architecture  
4. Error Handling & Retry Strategies  
5. Source Code

---

## 12. Related Documents

- [`../kernel/llm_gateway.md`](../kernel/llm_gateway.md) — owns the one real implementation of this taxonomy today
- [`workflow_architecture.md`](workflow_architecture.md) · [`../kernel/workflow_engine.md`](../kernel/workflow_engine.md) — the intended (not yet built) step-level retry owner
- [`../platform/platform_sdk.md`](../platform/platform_sdk.md) §4.4 — the `AiOsError` hierarchy specification, and confirmation no `ai-os-sdk` package exists to hold it
- [`../quality/quality_gates_framework.md`](../quality/quality_gates_framework.md) — the `quality` category's intended (unbuilt) producer
- [`../../09_security/security_architecture.md`](../../09_security/security_architecture.md) — the `security` category's intended producer
- [`../../19_roadmap/feature_inventory.md`](../../19_roadmap/feature_inventory.md) · [`../../19_roadmap/implementation_status.md`](../../19_roadmap/implementation_status.md) — live build status
