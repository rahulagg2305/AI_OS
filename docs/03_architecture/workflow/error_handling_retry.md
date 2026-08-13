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

## Implementation Status (2026-08-01)

**Partially built — real inside the LLM Gateway, and now real and general (not gate-specific) inside the Workflow Engine too.**

**Built:** the LLM Gateway's own `ai_os_kernel.llm_gateway.error_taxonomy.ErrorCategory` implements **4 of this document's 6 categories** — `transient`, `permanent`, `infrastructure`, `budget`. Its own docstring states plainly why `quality` and `security` are excluded: a provider call failure can never actually be either. `classify_http_status()` and `parse_retry_after_seconds()` (numeric-seconds form only, not the HTTP-date form) are real and drive the Gateway's retry/circuit-breaker/backoff logic exactly as §4's "LLM Gateway owns retry/fallback" describes.

**The Workflow Engine's own retry ownership (§4, §9) now has a real, general implementation (first landed narrowly for quality gates 2026-07-30, widened the same day to any retriable step-executor exception).** `RetryPolicy` — declared on `WorkflowDefinition` (not per-step; a factual correction to this document's own prior framing) and already validated at load time (bounded attempts + duration, per §5's own rule) — is genuinely read now: `WorkflowAdvanceRunner.run_to_completion` catches *any* step-executor exception and retries it only when the exception itself declares `retriable = True` (`getattr(exc, "retriable", None) is True` — an explicit, per-instance self-declaration, never inferred from the exception's class alone) **and** its failing step has a configured retry target (composition-level config, e.g. `se.delivery_pipeline`'s own `_STEP_RETRY_TARGETS`), calling `WorkflowInstanceService.retry_after_step_failure` to reset `current_step_id` backward — genuinely bounded on both axes (`max_attempts` **and** `max_duration_seconds`, never either alone), never an unconditional or unlimited retry. This is genuinely "different policies for different error categories" in miniature: `QualityGateFailedError` (a `quality`-category failure) self-declares `retriable = True` unconditionally, since a gate retry re-runs the artifact-*producing* step (real corrective work, not a blind re-evaluation); `ai_os_kernel.llm_gateway.errors.LLMProviderError` carries this document's own `transient`/`permanent`/`infrastructure`/`budget` classification straight through — a `transient` provider failure propagating unwrapped out of a `PromptedAgent` step is retriable by the identical self-declaration, a `permanent`/`budget` one is not; every other Workflow Engine exception (`AgentOutputValidationError`, `ToolOutputValidationError`, etc.) declares no `retriable` attribute at all and so still fails immediately, exactly as before this feature existed.

**`AgentRegistryError`/`ToolRegistryError`'s own retriable split — left deliberately undecided two steps ago, now investigated and explicitly decided (2026-07-31).** Investigation found a real, structural way to tell this exception type's several real causes apart after all: every raise site in `ai_os_kernel.workflow_engine.registry` already knows exactly which real cause it represents at the moment it raises, so each now sets a `retriable` constructor parameter explicitly there — the identical per-instance self-declaration `LLMProviderError` already uses, defaulted `False` (the opposite default, since three of the four real causes are structural/permanent: a loaded entrypoint failing the `Agent`/`Tool` Protocol check, a tool's own declared `trust_tier` disagreeing with its `catalog.tools` row, or a missing backing object for a declared permission) and overridden to `True` at exactly one site — a genuine persistence-layer failure during the catalog lookup itself. **A real, discovered correction found while proving the transient case, not merely a decision on paper**: the existing `except sa.exc.SQLAlchemyError` clause never actually catches a failure to *establish* the connection at all (refused, unreachable, DNS failure) — that surfaces as the driver's own raw `OSError` subclass (`TimeoutError` included, itself an `OSError` subclass), never wrapped by SQLAlchemy, since no `Connection` object yet exists for it to attach DBAPI-error-wrapping to; both `resolve_agent`/`resolve_tool` now also catch `OSError`, the identical broad catch `ai_os_kernel.bootstrap._build_health_service`'s own `database_check` already uses for the same reason. No exception-*type* split: nothing in this codebase catches either exception any narrower than its own type today, so two new classes would have added real code with no real consumer to justify it.

**Built, 2026-08-01 — the `AiOsError` exception hierarchy (§8) is now real, in `ai-os-sdk` (`platform_sdk/src/ai_os_sdk/errors/taxonomy.py`, `models/error.py`), verified field-by-field against this section: the exact six categories, the exact `AiOsError` → `TransientError`/`PermanentError`/`QualityError`/`InfrastructureError`/`BudgetExceededError`/`SecurityError` hierarchy, the §3 `Retriable` table (including `infrastructure`'s case-by-case override), and a real 1:1 `to_structured_error()` mapping — confirmed by 144 passing tests, `ruff`, and `mypy --strict` (`P02-S07-M44-T01`, risk register R-008 closed).** Not yet real: the `error_code` catalogue (§3, `platform_sdk/errors/`) has no populated entries, and `LLMProviderError`/`LLMRefusalError` (`kernel/src/ai_os_kernel/llm_gateway/errors.py`) still inherit from plain `Exception`, not from `AiOsError` — no Kernel exception anywhere raises through this hierarchy yet. Both are separate, larger undertakings needing real producers across the codebase, not this module's own scope.

**Not built:**
- **§2's own "Protect against infinite loops" goal was genuinely violated for the multi-instance worker loop — FIXED 2026-08-13 (`P02-S01-M05-T17`), see the resolution note at the end of this bullet.** (Found 2026-08-10, `P06-S01-M36-T04`, risk register R-016 — investigating `POST /workflows/{id}/retry`.) `WorkflowAdvanceRunner.run_once` (the method `WorkflowWorkerLoop._advance_one` actually calls, not `run_to_completion`) has no retry/bound logic of its own; a raised step exception propagates straight out, is logged, and the instance — its lease already released, its own `workflow_instances.status` still `running` — is rediscovered by the very next poll and retried again. No persisted attempt count, no bound, no terminal state: a permanently-failing step retries forever, for the life of the Kernel process, on this one real, continuously-running production path. `run_to_completion`'s own bounded `RetryPolicy` exhaustion (used only by the synchronous, one-shot demo/`se.delivery_pipeline` triggers) is real but never persisted — by the time any later caller could inspect it, that exhaustion already happened and vanished with the returned `WorkflowRunResult`. `WorkflowInstanceStatus.FAILED` (the persisted, instance-level terminal state) is declared but never written by any real caller anywhere in this codebase — confirmed by tracing every real writer, not assumed. **Resolution (2026-08-13, `P02-S01-M05-T17`):** the worker loop now evaluates the same attempts-and-duration bound §4 requires, using counters read back from `workflow_steps` (which `record_failed_attempt` already populated — no migration), and writes the terminal `failed` state on exhaustion. A definition declaring no `retryPolicy` gets a platform default of 2 attempts / 60s, a product-owner decision mirroring the one real declared policy; a definition declaring its own overrides it. Because `failed` is terminal and `list_runnable_instances` filters on non-terminal status, the instance stops being rediscovered — the loop genuinely ends. **`failureHandling.onError` (`halt`/`escalate`) remains required on every definition and read by nothing**, a smaller gap disclosed rather than absorbed: exhaustion always writes `failed`, and `escalate` has no defined meaning to honour. See risk register R-016 for the full finding and resolution.
- **A per-exception-type retriable/non-retriable classification exists only where each exception's own author has added it** (`QualityGateFailedError`, `LLMProviderError`/`LLMRefusalError`, and now `AgentRegistryError`/`ToolRegistryError`) — there is no central, enforced taxonomy requiring every new Workflow Engine exception to declare one; every other exception (`AgentOutputValidationError`, `ToolOutputValidationError`, `ToolSandboxRequiredError`, `AgentNotRegisteredError`, `ToolNotRegisteredError`, `EntrypointLoadError`, `PackNotActivatedError`, `PromptedAgentInputError`) still declares nothing and defaults to non-retriable by omission, not a further per-type decision this document tracks one by one. Compensation/rollback (§6) and human escalation (§7) do not exist; `security` errors have no producer, since the Security Manager's own audit path is largely unbuilt.

Consequence: this document's "single platform error taxonomy" is, in practice, three things now — a real, narrower taxonomy inside the Gateway; a real, general, but not-yet-adopted-anywhere `AiOsError` hierarchy in `ai-os-sdk`; and a still-unpopulated `error_code` catalogue. The Workflow Engine's own retry ownership is real for exactly one category and one trigger, not yet the general mechanism §4/§9 describe.

Authoritative, always-current status: `../../19_roadmap/feature_inventory.md` (module 6, LLM Gateway; module 44, `AiOsError` hierarchy). Build history: `../../19_roadmap/history/006_llm_gateway_and_prompt_engine_foundation.md`, `history/011_llm_gateway_advanced_router_retry_budget.md`.

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

This document establishes the baseline error handling and retry strategy. See the Implementation Status section near the top for exactly what exists: a real, narrower 4-category taxonomy inside the LLM Gateway, a first real (narrow, gate-specific) Workflow-Engine-level retry mechanism (2026-07-30), a real but not-yet-adopted-anywhere platform-wide `AiOsError` hierarchy (2026-08-01), and still no error-code catalogue. Concrete policy values for `se.delivery_pipeline`'s own gate retry are decided and declared (`retryPolicy: {maxAttempts: 2, maxDurationSeconds: 60.0}`, `delivery_pipeline.yaml`); values for any *future*, more general retry mechanism remain a genuinely open implementation decision — the Gateway's own hardcoded constants (`kernel/bootstrap.py`) are a documented, temporary carve-out, not a settled policy.

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
- [`../platform/platform_sdk.md`](../platform/platform_sdk.md) §4.4 — the `AiOsError` hierarchy specification, now implemented in `ai-os-sdk` (`P02-S07-M44-T01`)
- [`../quality/quality_gates_framework.md`](../quality/quality_gates_framework.md) — the `quality` category's intended (unbuilt) producer
- [`../../09_security/security_architecture.md`](../../09_security/security_architecture.md) — the `security` category's intended producer
- [`../../19_roadmap/feature_inventory.md`](../../19_roadmap/feature_inventory.md) — live build status
