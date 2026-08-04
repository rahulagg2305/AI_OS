# Implementation Roadmap – AI_OS

**Project:** AI_OS (AI Operating System)
**Document:** Implementation Roadmap
**Version:** 2.1
**Status:** Approved
**Last Updated:** 2026-07-28 (per-deliverable delivery markers and an explicit exit status added to **every** stage, A–H; §5 given a verified status column; §6 Current Status rewritten — it still said "Implementation begins at Stage A". Stage structure, deliverable wording, and every exit criterion are unchanged.)

**Delivery marker legend:** ✅ built · ◐ partially built (the qualifier states what is missing) · ⬜ not built. Markers reflect verified source inspection on the date above, not intent. The authoritative per-module view is [`feature_inventory.md`](feature_inventory.md).

---

## 1. Purpose

The implementation sequence for AI_OS. Version 2.0 adds concrete deliverables, exit criteria, and the technology decisions each stage depends on.

**One sequence only.** The lettered Stages A–H below are the single delivery sequence. The numbered "Phases 0–6" used in earlier documents were documentation-authoring phases and are retired (see `documentation_freeze.md` §7).

---

## 2. Guiding Principles

- Documentation-first remains in force ([ADR-0003](../18_decision_log/adr/ADR-0003-documentation-first-development.md)); prototypes in `workspace/prototypes/` are exempt until promoted.
- **Prove the architecture with a thin vertical slice before broadening.** Stage C exercises every layer end to end with three agents rather than building fifteen shallowly.
- Build only the Kernel components the current stage needs.
- Observability and traceability from the first working workflow, not retrofitted.
- Never skip a Quality Gate or a Human Approval Point.
- Re-baseline the NFR values marked **(baseline)** against measurement as stages complete.

---

## 3. Stages

**How to read the stage lists.** Every deliverable in every stage below carries a delivery marker (✅ built · ◐ partially built, with a qualifier naming what is missing · ⬜ not built), and every stage ends with an explicit **Exit status** line, so a fresh reader can see the real boundary between what exists and what does not without cross-referencing another document.

Markers are *annotations, not changes*: no deliverable wording, no exit criterion, and no stage boundary below has been altered. They are a snapshot verified against the source tree on 2026-07-28 and will drift — [`feature_inventory.md`](feature_inventory.md) remains the authority on "how much of X is built", and [`implementation_status.md`](implementation_status.md) on the current stage. **Stages do not complete in order** (see §6), so a ✅ in a later stage is not evidence an earlier stage is finished.

### Stage A — Platform Skeleton

**Goal:** a running, observable, configurable process that can discover a pack.

Deliverables (delivery markers verified 2026-07-28):
- ✅ `uv` workspace with all distributions and a committed `uv.lock` ([ADR-0009](../18_decision_log/adr/ADR-0009-packaging-and-dependency-management.md))
- ✅ Composition root `kernel/bootstrap.py` with lifecycle ordering ([ADR-0010](../18_decision_log/adr/ADR-0010-composition-and-dependency-injection.md))
- ◐ Configuration Manager with the canonical precedence order and schema validation — **3 of 7 precedence layers built**; no pack defaults, runtime overrides, experiment overrides, or secrets layer
- ◐ Secrets resolution: env and file backends ([ADR-0024](../18_decision_log/adr/ADR-0024-secrets-management-backend.md)) — **`env` backend only; the file backend is not built**
- ◐ OpenTelemetry instrumentation + `structlog`; Compose observability profile ([ADR-0017](../18_decision_log/adr/ADR-0017-observability-stack.md)) — **real spans + one metric, console exporters only. No OTLP export, no Collector, no Compose observability profile.**
- ◐ Health & Lifecycle with liveness/readiness endpoints — endpoints real; no graceful-shutdown coordinator, pack health not aggregated
- ◐ Manifest Loader validating against the JSON Schema — schema validation real; **filesystem-scan discovery only, no entry-point discovery** (ADR-0009)
- ✅ Alembic baseline migration; Postgres and Redis via Compose — 29 migrations (`0001_workflow_state_baseline` through `0029_knowledge_schema`); note **no Kernel code uses Redis yet**
- ◐ CI pipeline green: lint, types, unit, contract, integration, security, build — lint/types/unit/integration run for real and pass; **contract, security, image-build, and frontend stages are deliberately gated to no-ops** pending their prerequisites

**Exit criteria:** the process starts, reports ready in ≤ 15 s (NFR-107), discovers and validates a trivial pack, rejects an invalid manifest with a specific error, and emits correlated telemetry. CI is green.

**Exit status: not met.** Telemetry is emitted but not *exported* (console only), and the file secrets backend is absent. Everything else above is satisfied.

### Stage B — Minimum Viable Kernel

**Goal:** load a pack and execute a real workflow that calls a model.

Deliverables (delivery markers verified 2026-07-28):
- ✅ Workflow Engine: definition loading and validation, instance management, sequential execution, event-sourced state, lease-based work distribution ([ADR-0011](../18_decision_log/adr/ADR-0011-persistence-and-workflow-state.md)) — note only `agent` and `tool` step types genuinely execute; `decision`, `parallel`, `sub_workflow`, `quality_gate`, and `human_approval` complete as no-ops
- ◐ Capability Manager with the canonical lifecycle state machine — register/activate/deactivate + `pack_state_transitions` real; **no pack discovery, no upgrade path, no health monitoring**
- ◐ LLM Gateway: one provider adapter, alias routing, retries, fallback, capability matrix, token/cost accounting, prompt-cache planning ([ADR-0002](../18_decision_log/adr/ADR-0002-llm-gateway-single-entry-point.md)) — **two** adapters, routing, retry/fallback, circuit breaker, backoff, capability matrix, cost accounting, a real per-provider rate limiter, real `count_tokens()`/`stream()` (Anthropic), and real `embed()` (`local` only — Anthropic's API has none) are all real; **no prompt-cache planner, no per-principal rate limiting, `complete()` does not yet internally stream for large outputs**
- ◐ Prompt Engine with versioned prompts and variable validation — in-memory + SQL catalog real; **no Prompt Resolver, no composition/inheritance, no cache-boundary support**
- ◐ Context Manager with deterministic assembly, budget enforcement, and trust tagging — all three met; **breadth is 2 of 6 documented sources**, and there is no first-class Filter/Ranker or persisted Context Audit Logger
- ◐ Retrieval: keyword + pgvector hybrid with RRF ([ADR-0013](../18_decision_log/adr/ADR-0013-search-and-vector-store.md)) — **keyword FTS only**. No vector search, no RRF fusion, no embeddings writer, no Retrieval Service.
- ⬜ Tool Invoker; Event Bus with transactional outbox ([ADR-0012](../18_decision_log/adr/ADR-0012-event-bus.md)) — **neither built.** No `ToolInvoker` exists in any form; the Event Bus is a stub package and only the `platform.event_outbox` table exists (no writer, no relay).
- ⬜ Quality Gate Engine with two Kernel gates — **not built.** Nothing enforces any quality gate anywhere in code.
- ⬜ Platform SDK v1.0.0 published, with the pack contract suite — **not built.** `platform_sdk/` holds one JSON schema; there is no `ai-os-sdk` package and no `pack_contract_suite`. This is why packs import Kernel internals directly.

**Exit criteria (FR-001…FR-011, FR-014…FR-017):** a pack loads from a manifest; a sequential workflow completes; an agent calls the Gateway and a tool; **killing the worker mid-step loses no committed state and the workflow resumes on another worker** (NFR-032, NFR-033); tokens and cost are recorded; a full trace is correlated end to end.

**Exit status: not met.** A pack loads, a sequential four-step workflow completes, an agent calls the Gateway, and tokens/cost are recorded. Outstanding: an agent calling a **Tool** through a real Tool Invoker (none exists), and the four ⬜ deliverables above. Lease-based crash recovery is implemented and tested but has not been exercised as a deliberate kill-the-worker drill.

### Stage C — First Real Capability Pack (thin slice)

**Goal:** one meaningful software-engineering workflow, end to end, with sandboxing and human approval.

Deliverables (delivery markers verified 2026-07-28):
- ◐ Software Engineering pack: manifest, three agents (`requirements-analyst`, `backend-developer`, `code-reviewer`), and the reduced `se.product_creation` plus `se.implement_task` (`../06_capability_packs/software_engineering/workflows.md` §13) — **a real pack exists with five agents, but a deliberately different set and workflow than planned here.** Built: `requirements-analyst`, `architecture`, `build`, `qa-test`, `documentation`, chained (four of the five) into a new workflow `se.delivery_pipeline`. `backend-developer` and `code-reviewer` are **not** built; neither `se.product_creation` nor `se.implement_task` exists. This divergence is deliberate and recorded — see the 2026-07-27 reprioritization in `implementation_status.md` and `../06_capability_packs/software_engineering/agents.md`'s "Currently Implemented Subset".
- ✅ **Tier 1 sandbox: ephemeral containers, no network, no secrets, resource limits** ([ADR-0016](../18_decision_log/adr/ADR-0016-tool-execution-sandboxing.md)) — `DockerSandbox` is real, is the config-driven default, and has been **verified live against a real daemon**, including network isolation and filesystem containment proven against code the pipeline itself generated
- ⬜ Tools: file read/write/patch, build, test — correctly tiered — **no manifest-declared Tool exists.** `SandboxedCommandTool` is used internally by three agents but is not a declared, registry-resolvable Tool.
- ⬜ Quality gates: build, unit tests, lint, type check — **not built** (blocked on the Quality Gate Engine, Stage B)
- ⬜ Human Approval Manager with durable pause and resume — **not built.** The `approvals` table exists (schema only, no writer/reader); `human_approval` steps complete as no-ops.
- ◐ Security Manager enforcing monotonic permission narrowing ([ADR-0023](../18_decision_log/adr/ADR-0023-identity-roles-and-permissions.md)) — bearer-token auth and 4 permissions across 9 routes are real; **narrowing is not enforced end to end** (agent/tool permission subsets are unchecked), and auth is a pre-shared-secret JWT, not OIDC
- ⬜ Hash-chained audit log with the daily verification job — **not built.** `governance.audit_log` exists as a table with no writer, no hash computed, and no verification job.
- ⬜ `tests/security/` organised by threat ID — **the directory is empty**

**Exit criteria (FR-021, FR-030…FR-034, FR-038, FR-039, FR-045, FR-110, FR-111):** a specification produces building, tested code; a blocking gate halts progression; an approval point pauses and resumes only on an authorized decision and **never on timeout**; a Tier 1 step demonstrably has no network, no secrets, and no host access; the audit chain verifies.

**Exit status: not met.** Two criteria are genuinely met: a specification produces building, tested code (the four-step pipeline does exactly this), and a Tier 1 step demonstrably has no network, no secrets, and no host access (live-verified). The other three — blocking gate, approval pause/resume, audit chain — depend on subsystems that are 0% built.

### Stage D — Evaluation and Multi-LLM Experimentation

**Goal:** the benchmarking product claim, made honestly.

Deliverables (delivery markers verified 2026-07-28):
- ⬜ Evaluation Engine: metrics collection, run manifest recording, comparison statistics with variance — **not built.** `ai_os_kernel.evaluation_engine` is a docstring-only stub; the six `evaluation.*` tables exist with no writer and no reader.
- ⬜ Benchmarking pack: experiment definition, replicate management, cost ceiling enforcement — **not built.** No such pack directory exists.
- ◐ Second provider adapter (proving [ADR-0002](../18_decision_log/adr/ADR-0002-llm-gateway-single-entry-point.md) and NFR-101) — `LocalAdapter` is a real second adapter behind the same contract, and cross-provider fallback exists, but **only `anthropic` is registered in checked-in config**, so provider substitution has not actually been demonstrated
- ⬜ Experiment configuration overrides, isolated per run — **not built.** No experiment concept exists in code.
- ⬜ Response caching disabled for experiments, enforced in the Gateway — **vacuously true, not built.** There is no response cache and no cache of any kind (ADR-0025 is 0% implemented), so there is nothing to disable.
- ⬜ Traceability Engine with impact and coverage queries — **not built.** `ai_os_kernel.traceability_engine` is a docstring-only stub; the `trace.*` tables exist with no writer.
- ⬜ Minimal comparison API and view — **not built.**

**Exit criteria (FR-019, FR-020, FR-070…FR-077, FR-114):** the same workflow runs against two models with ≥ 3 replicates each; the report shows **mean and variance**, excludes any cache-served run, and links to each run's manifest; a completed workflow replays from its event log; **provider substitution required no change to any agent or pack**.

**Exit status: not started.** No criterion is met, and none is close: replicates, variance reporting, run manifests, and replay-from-event-log all require the Evaluation Engine, which is 0% built. The event log itself is complete and correct, so replay is the criterion with the shortest path.

### Stage E — Project Intelligence

**Goal:** analyse an existing codebase safely.

Deliverables: ⬜ Project Intelligence pack; ⬜ `existing-project-analyzer`; ⬜ ingestion and structural analysis; ⬜ language/framework detection; ⬜ dependency graph; ⬜ architecture recovery; ⬜ documentation generation; ⬜ knowledge write-back with provenance; ◐ **all ingested content tagged `untrusted` end to end** *(the tagging mechanism exists — every `ContextItem` carries `trust` and a `SourceRef` — but there is no ingestion path to apply it to)*.

**Exit criteria (FR-050…FR-059):** a real repository within NFR-006 limits is analysed and documented; every derived context item carries `untrusted`; ingestion respects resource limits.

**Exit status: not started.** No Project Intelligence pack exists.

### Stage F — Dashboard, Voice, Notifications

**Goal:** usable by humans day to day.

Deliverables: ◐ API v1 complete with OpenAPI snapshot tests *(12 real `/api/v1` handlers across health, packs, and workflows; **no OpenAPI snapshot test**, no RFC 9457 error shape, no `Idempotency-Key`, no rate limiting)*; ⬜ WebSocket stream *(the `/api/v1/stream` endpoint does not exist)*; ⬜ Dashboard (Overview, Workflows, Approvals, Experiments, Quality, Cost, Health, Logs & Traces) ([ADR-0018](../18_decision_log/adr/ADR-0018-dashboard-technology-stack.md)) *(`dashboard/` is an empty directory — no TypeScript or React anywhere)*; ⬜ Notification Service; ⬜ Speech Gateway and Voice pack MVP ([ADR-0019](../18_decision_log/adr/ADR-0019-speech-gateway.md)) *(`platform_services/` contains no files at all)*.

**Exit criteria (FR-090…FR-100, FR-116):** an approval is decided from the Dashboard and the workflow resumes; live updates arrive over WebSocket; a `viewer` sees no mutating controls and the API refuses them regardless of channel; a voice status query works end to end.

**Exit status: not started.** Note two prerequisites outside this stage: the approval criterion needs the Human Approval Manager (Stage C, ⬜) and the `viewer` criterion needs the role model (Stage G, ⬜).

### Stage G — Hardening and Production Readiness

**Goal:** safe to run on real work.

Deliverables: ⬜ OIDC authentication and full role model *(auth is a pre-shared-secret JWT; none of the five ADR-0023 roles exist)*; ⬜ Vault backend *(`env` backend only)*; ⬜ NetworkPolicy egress allowlist; ⬜ Kubernetes manifests and Helm chart with the supported sandbox patterns ([ADR-0020](../18_decision_log/adr/ADR-0020-deployment-topology-and-scaling.md)) *(`infra/kubernetes/`, `infra/terraform/`, and `infra/docker/` are all empty, and **there is no Dockerfile anywhere**, so no image exists to deploy)*; ⬜ performance suite against NFR targets *(`tests/performance/` is an empty directory)*; ⬜ **backup and restore rehearsal**; ⬜ chaos tests (kill worker, kill Redis, drop provider); ⬜ cost anomaly alerting; ⬜ coverage thresholds met *(`pytest-cov` with branch coverage is configured, but no threshold is enforced in CI)*.

**Exit criteria:** NFR §3, §4, §5 targets met and re-baselined; a restore rehearsal succeeds including audit-chain verification and workflow resumption; every T1–T12 threat control has a passing test.

**Exit status: not started.** `tests/security/` — where the T1–T12 controls would be tested — is empty, and the audit chain the restore rehearsal must verify does not exist yet.

### Stage H — Expansion

◐ Remaining agents (`architecture`, `frontend-developer`, `database`, `api-designer`, `devops`, `release`, `refactoring`, `performance`) with specifications written first; ⬜ remaining workflows; ⬜ richer Project Intelligence; ⬜ CLI polish *(`tools/` is empty — there is no `aios` package, so there is no CLI to polish)*; ⬜ additional packs as needed.

> **`architecture` landed early**, out of sequence: it is one of the Software Engineering pack's five real agents and the first step of `se.delivery_pipeline`. So did `build`, `qa-test`, and `documentation` — none of which appear in any stage list, because they are a deliberately different, narrower agent set than the roadmap planned (see Stage C). The seven remaining agents named above are genuinely unbuilt.

---

## 4. Dependencies

```text
A ──▶ B ──▶ C ──▶ D ──▶ F ──▶ G ──▶ H
                 └──▶ E ──┘
```

- B requires A. C requires B. D requires C (there must be real workflows to benchmark).
- E may start after C and run in parallel with D.
- F requires C for useful content and D for experiment views.
- G intensifies after F, but security fundamentals — sandboxing, authorization, audit — land in Stage C. They are not deferred to a hardening stage.

---

## 5. What Must Not Be Deferred

Recorded explicitly, because these are the items most commonly postponed and most costly to retrofit:

| Concern | Required by | Status (verified 2026-07-28) |
|---|---|---|
| Tier 1 sandboxing | Stage C — the first stage that executes generated code | ✅ `DockerSandbox`, all five controls, the config-driven default, verified live |
| Monotonic permission narrowing | Stage C | ⬜ 4 permissions are checked at the HTTP boundary; the principal ∩ workflow ∩ agent ∩ tool intersection is not computed anywhere |
| Hash-chained audit log | Stage C | ⬜ `governance.audit_log` exists as a table with no writer, no hash, no verification job |
| Trust tagging of context | Stage B | ✅ every `ContextItem` carries `trust: "trusted" \| "untrusted"` plus a `SourceRef`; workflow inputs default to `untrusted`. Delimited framing of untrusted content at render time is still outstanding |
| Event-sourced workflow state | Stage B — retrofitting replay onto snapshot-only state is a rewrite | ✅ append-only `workflow_events` committed in the same transaction as the `workflow_instances` snapshot |
| Correlated telemetry | Stage A | ◐ real spans and correlation IDs, **console exporters only** — nothing receives the telemetry |
| Run manifests | Stage D, but the fields are captured from Stage B | ◐ the `llm_calls` recorder captures resolved model, tokens, and cost per call; there is no run-manifest record assembling the full condition set |
| Per-workflow workspace isolation | Stage C, before any parallel step exists | ◐ each Tier 1 step gets an isolated container with a single writable mount; there is no per-*workflow* workspace allocation concept, and no parallel step type executes yet |

**This is the most important table in the document to keep honest**, because every ⬜ and ◐ above is something the roadmap itself flags as costly to retrofit. Three of the eight are not yet where this table requires them.

---

## 6. Current Status

**Last verified: 2026-07-28.** Documentation baseline approved (`documentation_freeze.md`). Technology decisions recorded as 25 Accepted ADRs.

**Stage A — process-complete, not exit-criteria-complete.** Built: the `uv` workspace with committed `uv.lock`, the composition root, Configuration Manager (3 of its 7 precedence layers), Health & Lifecycle, Manifest Loader (filesystem-scan discovery only — entry-point discovery per ADR-0009 is not implemented), the Alembic baseline plus 28 further migrations (29 in total), Postgres and Redis via Compose, and a green CI pipeline. Outstanding: **secrets resolution has only the `env` backend** (no file backend, contrary to this stage's deliverable list), and **OpenTelemetry has real spans plus one metric but console exporters only** — no OTLP export and no Compose observability profile.

**Stage B — underway.** Built: Workflow Engine (definition loading/validation, instance lifecycle, event-sourced state, lease-based distribution with reaper, run-to-completion), LLM Gateway (two provider adapters, router, dispatcher, retry/fallback, circuit breaker, backoff, error taxonomy, two budget scopes, capability negotiator, token/cost accounting), Prompt Engine (in-memory + SQL catalog), Context Manager (2 of 6 documented sources, with real budget enforcement and trust tagging), Capability Manager lifecycle. **Outstanding and blocking Stage B exit: Tool Invoker, Event Bus, Quality Gate Engine, Retrieval's vector/hybrid half, and Platform SDK v1.0.0 — all 0% built.**

**Stage C — partially landed early.** A product-owner reprioritization (2026-07-27) pulled pack work ahead of Stage B completion. Built: a real Software Engineering pack (5 agents; 4 chained into `se.delivery_pipeline`) and a real ADR-0016 **Tier 1 sandbox** (`DockerSandbox` — ephemeral container, no network, read-only root, non-root, resource-limited), now the config-driven default and verified live against a real daemon. Outstanding: quality gates, the Human Approval Manager (the `approvals` table exists with no writer), the hash-chained audit log (table exists, no writer, no verification job), monotonic permission narrowing end-to-end, and `tests/security/` organised by threat ID (that directory is empty).

**Stages D–H — not started**, with two exceptions that landed early: a second provider adapter (`LocalAdapter`, Stage D) and `evaluation.*`/`trace.*` table schemas (no engine code behind either).

> **Stages do not complete strictly in order.** The reprioritization above is deliberate and recorded. Treat the stage lists in §3 as *deliverable inventories*, not as a completion sequence you can infer progress from.

**The live, authoritative views** — read these rather than this section for anything decision-relevant:

- `implementation_status.md` — short: current stage, what exists, blockers, next step
- `feature_inventory.md` — per-module completion percentages and status categories
- `history/INDEX.md` — full chronological build history

---

## 7. Final Authority

Order of precedence:

1. Project Constitution
2. AI Governance Framework
3. System Architecture
4. Architecture Decision Records
5. Implementation Roadmap (this document)
6. Source Code
