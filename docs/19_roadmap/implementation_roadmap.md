# Implementation Roadmap – AI_OS

**Project:** AI_OS (AI Operating System)
**Document:** Implementation Roadmap
**Version:** 2.0
**Status:** Approved
**Last Updated:** 2026-07-25

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

### Stage A — Platform Skeleton

**Goal:** a running, observable, configurable process that can discover a pack.

Deliverables:
- `uv` workspace with all distributions and a committed `uv.lock` ([ADR-0009](../18_decision_log/adr/ADR-0009-packaging-and-dependency-management.md))
- Composition root `kernel/bootstrap.py` with lifecycle ordering ([ADR-0010](../18_decision_log/adr/ADR-0010-composition-and-dependency-injection.md))
- Configuration Manager with the canonical precedence order and schema validation
- Secrets resolution: env and file backends ([ADR-0024](../18_decision_log/adr/ADR-0024-secrets-management-backend.md))
- OpenTelemetry instrumentation + `structlog`; Compose observability profile ([ADR-0017](../18_decision_log/adr/ADR-0017-observability-stack.md))
- Health & Lifecycle with liveness/readiness endpoints
- Manifest Loader validating against the JSON Schema
- Alembic baseline migration; Postgres and Redis via Compose
- CI pipeline green: lint, types, unit, contract, integration, security, build

**Exit criteria:** the process starts, reports ready in ≤ 15 s (NFR-107), discovers and validates a trivial pack, rejects an invalid manifest with a specific error, and emits correlated telemetry. CI is green.

### Stage B — Minimum Viable Kernel

**Goal:** load a pack and execute a real workflow that calls a model.

Deliverables:
- Workflow Engine: definition loading and validation, instance management, sequential execution, event-sourced state, lease-based work distribution ([ADR-0011](../18_decision_log/adr/ADR-0011-persistence-and-workflow-state.md))
- Capability Manager with the canonical lifecycle state machine
- LLM Gateway: one provider adapter, alias routing, retries, fallback, capability matrix, token/cost accounting, prompt-cache planning ([ADR-0002](../18_decision_log/adr/ADR-0002-llm-gateway-single-entry-point.md))
- Prompt Engine with versioned prompts and variable validation
- Context Manager with deterministic assembly, budget enforcement, and trust tagging
- Retrieval: keyword + pgvector hybrid with RRF ([ADR-0013](../18_decision_log/adr/ADR-0013-search-and-vector-store.md))
- Tool Invoker; Event Bus with transactional outbox ([ADR-0012](../18_decision_log/adr/ADR-0012-event-bus.md))
- Quality Gate Engine with two Kernel gates
- Platform SDK v1.0.0 published, with the pack contract suite

**Exit criteria (FR-001…FR-011, FR-014…FR-017):** a pack loads from a manifest; a sequential workflow completes; an agent calls the Gateway and a tool; **killing the worker mid-step loses no committed state and the workflow resumes on another worker** (NFR-032, NFR-033); tokens and cost are recorded; a full trace is correlated end to end.

### Stage C — First Real Capability Pack (thin slice)

**Goal:** one meaningful software-engineering workflow, end to end, with sandboxing and human approval.

Deliverables:
- Software Engineering pack: manifest, three agents (`requirements-analyst`, `backend-developer`, `code-reviewer`), and the reduced `se.product_creation` plus `se.implement_task` (`../06_capability_packs/software_engineering/workflows.md` §13)
- **Tier 1 sandbox: ephemeral containers, no network, no secrets, resource limits** ([ADR-0016](../18_decision_log/adr/ADR-0016-tool-execution-sandboxing.md))
- Tools: file read/write/patch, build, test — correctly tiered
- Quality gates: build, unit tests, lint, type check
- Human Approval Manager with durable pause and resume
- Security Manager enforcing monotonic permission narrowing ([ADR-0023](../18_decision_log/adr/ADR-0023-identity-roles-and-permissions.md))
- Hash-chained audit log with the daily verification job
- `tests/security/` organised by threat ID

**Exit criteria (FR-021, FR-030…FR-034, FR-038, FR-039, FR-045, FR-110, FR-111):** a specification produces building, tested code; a blocking gate halts progression; an approval point pauses and resumes only on an authorized decision and **never on timeout**; a Tier 1 step demonstrably has no network, no secrets, and no host access; the audit chain verifies.

### Stage D — Evaluation and Multi-LLM Experimentation

**Goal:** the benchmarking product claim, made honestly.

Deliverables:
- Evaluation Engine: metrics collection, run manifest recording, comparison statistics with variance
- Benchmarking pack: experiment definition, replicate management, cost ceiling enforcement
- Second provider adapter (proving [ADR-0002](../18_decision_log/adr/ADR-0002-llm-gateway-single-entry-point.md) and NFR-101)
- Experiment configuration overrides, isolated per run
- Response caching disabled for experiments, enforced in the Gateway
- Traceability Engine with impact and coverage queries
- Minimal comparison API and view

**Exit criteria (FR-019, FR-020, FR-070…FR-077, FR-114):** the same workflow runs against two models with ≥ 3 replicates each; the report shows **mean and variance**, excludes any cache-served run, and links to each run's manifest; a completed workflow replays from its event log; **provider substitution required no change to any agent or pack**.

### Stage E — Project Intelligence

**Goal:** analyse an existing codebase safely.

Deliverables: Project Intelligence pack; `existing-project-analyzer`; ingestion and structural analysis; language/framework detection; dependency graph; architecture recovery; documentation generation; knowledge write-back with provenance; **all ingested content tagged `untrusted` end to end**.

**Exit criteria (FR-050…FR-059):** a real repository within NFR-006 limits is analysed and documented; every derived context item carries `untrusted`; ingestion respects resource limits.

### Stage F — Dashboard, Voice, Notifications

**Goal:** usable by humans day to day.

Deliverables: API v1 complete with OpenAPI snapshot tests; WebSocket stream; Dashboard (Overview, Workflows, Approvals, Experiments, Quality, Cost, Health, Logs & Traces) ([ADR-0018](../18_decision_log/adr/ADR-0018-dashboard-technology-stack.md)); Notification Service; Speech Gateway and Voice pack MVP ([ADR-0019](../18_decision_log/adr/ADR-0019-speech-gateway.md)).

**Exit criteria (FR-090…FR-100, FR-116):** an approval is decided from the Dashboard and the workflow resumes; live updates arrive over WebSocket; a `viewer` sees no mutating controls and the API refuses them regardless of channel; a voice status query works end to end.

### Stage G — Hardening and Production Readiness

**Goal:** safe to run on real work.

Deliverables: OIDC authentication and full role model; Vault backend; NetworkPolicy egress allowlist; Kubernetes manifests and Helm chart with the supported sandbox patterns ([ADR-0020](../18_decision_log/adr/ADR-0020-deployment-topology-and-scaling.md)); performance suite against NFR targets; **backup and restore rehearsal**; chaos tests (kill worker, kill Redis, drop provider); cost anomaly alerting; coverage thresholds met.

**Exit criteria:** NFR §3, §4, §5 targets met and re-baselined; a restore rehearsal succeeds including audit-chain verification and workflow resumption; every T1–T12 threat control has a passing test.

### Stage H — Expansion

Remaining agents (`architecture`, `frontend-developer`, `database`, `api-designer`, `devops`, `release`, `refactoring`, `performance`) with specifications written first; remaining workflows; richer Project Intelligence; CLI polish; additional packs as needed.

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

| Concern | Required by |
|---|---|
| Tier 1 sandboxing | Stage C — the first stage that executes generated code |
| Monotonic permission narrowing | Stage C |
| Hash-chained audit log | Stage C |
| Trust tagging of context | Stage B |
| Event-sourced workflow state | Stage B — retrofitting replay onto snapshot-only state is a rewrite |
| Correlated telemetry | Stage A |
| Run manifests | Stage D, but the fields are captured from Stage B |
| Per-workflow workspace isolation | Stage C, before any parallel step exists |

---

## 6. Current Status

Documentation baseline approved (`documentation_freeze.md`). Technology decisions recorded as 25 Accepted ADRs. **Implementation begins at Stage A.**

---

## 7. Final Authority

Order of precedence:

1. Project Constitution
2. AI Governance Framework
3. System Architecture
4. Architecture Decision Records
5. Implementation Roadmap (this document)
6. Source Code
