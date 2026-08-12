# Non-Functional Requirements – AI_OS

**Project:** AI_OS (AI Operating System)
**Document:** Non-Functional Requirements
**Version:** 1.0
**Status:** Approved
**Last Updated:** 2026-07-25

---

## 1. Purpose

This document states the measurable non-functional targets for AI_OS v1. Every value here is a **verifiable target**, not an aspiration: each has a measurement method, and each is the basis for a Quality Gate threshold, a capacity decision, or an alert.

Where a target is provisional it is marked **(baseline)** — meaning it is set from first-principles estimates and must be re-baselined against measured data by the end of Stage D. Marking it explicitly is deliberate: an unmarked guess presented as a requirement is worse than a stated estimate.

Requirement IDs are `NFR-###` and are traceable from tests and architecture elements.

---

## Implementation Status (updated 2026-08-03, `P01-S06-M42-T05`)

**Updated: `tests/performance/` is now real — closing the "no measurement path exists yet" gap this section used to disclose for every §3-5 target it could honestly measure.** 10 real, repeatable tests (real Postgres via testcontainers, a real Docker daemon for NFR-015 when reachable) genuinely measure and pass/fail against the documented number: NFR-010, NFR-011, NFR-012, NFR-013, NFR-015, NFR-018 (latency, §3); NFR-020, NFR-021 (throughput, §4); NFR-033, NFR-036 (availability/recovery, §5) — plus one real, disclosed extra measurement with no numbered target of its own (the Scheduler's own real poll-to-start latency). Deliberately runs nightly/on-demand (`.github/workflows/performance.yml`), never on every push — several tests use real, production interval/duration constants (never a test-shortened override) specifically so their own timing reflects the real target, which makes them genuinely slow. Still not measurable, disclosed rather than faked: NFR-014 (no hybrid retrieval component exists), NFR-016 (no deterministic stand-in wired through the *real* Gateway pipeline itself), NFR-017/NFR-019 (no Event Bus, no WebSocket route, no dashboard), NFR-022/NFR-023/NFR-024 (no event bus, no outbox relay, no document ingestion pipeline), NFR-025 (needs *N* genuinely separate worker processes measured together, a heavier multi-container setup this suite does not attempt), NFR-030/NFR-031/NFR-034/NFR-035 (production-monitoring/backup-recovery windows no single test run can assert), NFR-032 (structural support exists, but no test yet genuinely kills an OS process mid-write), NFR-037 (a correctness property, already covered elsewhere, not a timing target), NFR-038 (a real Redis client exists, `P02-S07-M23-T01`, but nothing in this suite exercises it under load — no real Kernel consumer of Redis exists anywhere yet to measure). Full detail and the exact real numbers from the last real run: `tests/performance/README.md`.

**Built (2026-07-28), unchanged by this step:** the quality thresholds that CI can already enforce — NFR-064 (`mypy --strict` clean across 283 source files) and NFR-065 (`ruff` clean) are enforced on every CI run; NFR-066 (dependency vulnerabilities) and NFR-067 (secret detection) run as real supply-chain scanning stages. NFR-080/NFR-081 (zero egress and zero secrets in untrusted execution) hold in practice for `DockerSandbox`, which is the config-driven default and has been verified live against a real daemon. NFR-032 (zero committed workflow state lost) is structurally supported by the event-log-plus-snapshot-in-one-transaction design and is covered by integration tests, though not yet by a process-kill chaos test. NFR-050/NFR-051 (per-step context budget, hard enforcement recording exclusions) are implemented in the Context Manager's Size & Token Budget Enforcer.

**Not built — no measurement path exists yet (outside §3-5, unchanged by this step):** NFR-030–NFR-038's own deployment-level subset still has no Helm chart or Kubernetes manifests (a real `Dockerfile` does now exist, `P01-S01-M40-T04`). NFR-034/NFR-035 (RPO/RTO) have no backup or restore tooling. NFR-040–NFR-046 are partially structural only: two budget ceilings (alias, workflow) are real, NFR-043 has no prompt-cache implementation to measure. **NFR-045 is now real** (`P07-S03-M42-T02`, 2026-08-09): `evaluation_engine.cost_anomaly` fires a real alert (through the Notification Service) within its own 120-second check interval — well under the documented 5-minute SLA — when real hourly spend genuinely exceeds 3x the real trailing-7-day hourly mean; proven by 3 real Postgres-backed tests plus 4 unit tests for the loop's own scheduling. Not yet measured by `tests/performance/` itself (that suite asserts §3-5 latency/throughput/availability targets, not this alerting pipeline) — a real, disclosed, separate follow-up if this section's own scope ever widens to include it. NFR-060–NFR-063 (coverage thresholds) are **not** currently gated in CI. NFR-070–NFR-074 (reproducibility) depend on run manifests and replay, neither of which exists. NFR-082–NFR-086: no authorization-latency measurement, no audit chain (the `governance.audit_log` table now has a real writer, `P01-S05-M04-T05`, but no coverage in this section yet), no secret rotation (`env` backend only). NFR-090–NFR-094: correlation IDs are emitted on real spans, but there is no telemetry backend to assert visibility windows against. NFR-107 (≤ 15 s cold start) is believed met but not asserted by a test.

Section 13's verification paths reference `tests/performance/` (now real, see above), `tests/benchmarks/` and `tests/security/` (the latter is real too, `P01-S06-M42-T04`-era — this line was stale; `tests/benchmarks/` remains an empty directory). `tests/unit/` and `tests/integration/` are real and substantial.

Authoritative, always-current status: `../../19_roadmap/feature_inventory.md` (per-module completion table). Build history: `../../19_roadmap/history/INDEX.md`.

---

## 2. Scale Assumptions (v1)

These bound every other number in this document.

| ID | Assumption | Value |
|---|---|---|
| NFR-001 | Deployment model | Single tenant, single organisation |
| NFR-002 | Concurrent human users | ≤ 25 |
| NFR-003 | Concurrent workflow instances | ≤ 50 |
| NFR-004 | Concurrent Tier 1 sandboxes | ≤ 20 |
| NFR-005 | Workflow instances per day | ≤ 2,000 |
| NFR-006 | Largest analysed repository | ≤ 2 GB working copy, ≤ 200,000 files |
| NFR-007 | Knowledge corpus | ≤ 5 M chunks (design headroom 20 M) |
| NFR-008 | Retained workflow events | ≤ 500 M rows before archival |
| NFR-009 | Installed Capability Packs | ≤ 20 active |

Exceeding NFR-003, NFR-004, or NFR-007 by a sustained 2× is a trigger to revisit the topology and store decisions ([ADR-0013](../../18_decision_log/adr/ADR-0013-search-and-vector-store.md), [ADR-0020](../../18_decision_log/adr/ADR-0020-deployment-topology-and-scaling.md)).

---

## 3. Latency

Model call latency is excluded from platform targets — it is provider-controlled and separately measured. **The platform is measured on its own overhead**, which is the only part it can be held to.

| ID | Operation | Target (p95) | Target (p99) | Measurement |
|---|---|---|---|---|
| NFR-010 | API read endpoint | 200 ms | 500 ms | Server-side span, excluding client network |
| NFR-011 | Workflow submission (`POST /workflows` → 202) | 300 ms | 800 ms | Span |
| NFR-012 | Platform overhead per workflow step (context assembly + validation + state write, excluding agent and model time) | 500 ms | 1.5 s | Span arithmetic |
| NFR-013 | Context assembly | 400 ms | 1 s | Span |
| NFR-014 | Retrieval, hybrid, 5 M chunks | 200 ms | 500 ms | Span (**baseline**) |
| NFR-015 | Tier 1 sandbox cold start | 2 s | 5 s | Span (**baseline**, warm pool assumed) |
| NFR-016 | LLM Gateway overhead (excluding provider time) | 50 ms | 150 ms | Span |
| NFR-017 | WebSocket event delivery, publish → client | 500 ms | 2 s | Instrumented round trip |
| NFR-018 | Workflow state write (event + snapshot, one transaction) | 50 ms | 150 ms | Span |
| NFR-019 | Dashboard first contentful paint | 1.5 s | 3 s | Lighthouse / RUM |

---

## 4. Throughput and Capacity

| ID | Requirement | Target |
|---|---|---|
| NFR-020 | Workflow step completions | ≥ 20 per second sustained, per worker replica (**baseline**) |
| NFR-021 | API requests | ≥ 200 rps per API replica for reads |
| NFR-022 | Event bus | ≥ 1,000 events per second in-process |
| NFR-023 | Outbox relay lag | ≤ 5 s p95 — **exceeding this is the ADR-0012 trigger to adopt Redis Streams** |
| NFR-024 | Document ingestion | ≥ 50 documents per minute per worker (**baseline**) |
| NFR-025 | Worker scaling | Adding a worker replica increases step throughput ≥ 80 % linearly up to 8 replicas |

---

## 5. Availability and Recovery

| ID | Requirement | Target |
|---|---|---|
| NFR-030 | Platform availability (API read path) | 99.5 % monthly |
| NFR-031 | Planned-maintenance downtime | Zero for API reads; rolling deploy |
| NFR-032 | Workflow durability | **Zero committed workflow state lost on any single process crash** |
| NFR-033 | Workflow resumption after worker crash | ≤ 60 s (lease expiry + reclaim) |
| NFR-034 | RPO (recovery point objective) | ≤ 5 minutes (Postgres PITR) |
| NFR-035 | RTO (recovery time objective) | ≤ 1 hour |
| NFR-036 | Graceful shutdown drain | Up to 300 s for in-flight steps before forced termination |
| NFR-037 | Provider outage tolerance | Automatic fallback to the next provider in the alias chain within 3 attempts |
| NFR-038 | Redis loss | Degraded performance only — **no data loss and no workflow failure**; Redis is a cache, never a system of record |

NFR-032 and NFR-038 are the two properties that justify the persistence design; both are directly testable by killing a process mid-workflow.

---

## 6. Cost Controls

Cost is a first-class NFR for this platform, not an operational afterthought.

| ID | Requirement | Target |
|---|---|---|
| NFR-040 | Per-step token ceiling | Enforced by `StepBudget`; exceeding raises `BudgetExceededError` |
| NFR-041 | Per-workflow cost ceiling | Configurable; default $25 for a full product-creation workflow (**baseline**) |
| NFR-042 | Per-experiment cost ceiling | Declared per experiment; the run refuses to start if the projected cost exceeds it |
| NFR-043 | Prompt-cache hit rate on repeated-prefix workloads | ≥ 60 % of input tokens served from cache (**baseline**) |
| NFR-044 | Cost attribution completeness | 100 % of model spend attributable to a workflow, agent, and pack |
| NFR-045 | Cost anomaly alert | Fires within 5 minutes when hourly spend exceeds 3× the trailing 7-day hourly mean |
| NFR-046 | Review-revise loop bound | Maximum iterations **and** a token ceiling, both declared; no unbounded loop may exist |

---

## 7. Context and Token Budgets

| ID | Requirement | Target |
|---|---|---|
| NFR-050 | Default per-step context budget | 60,000 tokens, configurable per agent |
| NFR-051 | Context budget enforcement | Hard — assembly truncates by rank and **records what was excluded**, rather than silently overflowing |
| NFR-052 | Context assembly determinism | Identical request + index generation + embedding version → byte-identical context |
| NFR-053 | Maximum single artifact inlined into context | 100 KB; larger artifacts are passed by reference |

---

## 8. Quality Thresholds

These become Quality Gate configuration values.

| ID | Requirement | Threshold |
|---|---|---|
| NFR-060 | Kernel test coverage (branch) | ≥ 90 % |
| NFR-061 | SDK and services coverage | ≥ 85 % |
| NFR-062 | Capability Pack coverage | ≥ 80 % |
| NFR-063 | Generated-code coverage (default gate for produced software) | ≥ 80 %, configurable per project |
| NFR-064 | Type checking | `mypy --strict` clean; zero errors |
| NFR-065 | Lint | `ruff` clean; zero errors |
| NFR-066 | Dependency vulnerabilities | Zero high or critical |
| NFR-067 | Secret detection | Zero findings |
| NFR-068 | Build gate | Build must succeed |
| NFR-069 | Documented public API | 100 % of public interfaces documented |

---

## 9. Reproducibility

| ID | Requirement | Target |
|---|---|---|
| NFR-070 | Run manifest completeness | 100 % of the fields required by [ADR-0022](../../18_decision_log/adr/ADR-0022-reproducibility-over-determinism.md), schema-validated |
| NFR-071 | Platform determinism | Context assembly, retrieval ranking, chunking, prompt rendering, gate evaluation, and cost computation are deterministic given identical inputs |
| NFR-072 | Experiment replicates | ≥ 3 runs per variant by default; comparisons report mean and variance |
| NFR-073 | Cached-response exclusion | 100 % of runs with `served_from_cache = true` excluded from comparison aggregates |
| NFR-074 | Replay fidelity | Any completed workflow reconstructable from its event log with no gaps |

---

## 10. Security

| ID | Requirement | Target |
|---|---|---|
| NFR-080 | Untrusted code network egress | Zero by default; only via a declared step through an allowlisted proxy |
| NFR-081 | Secrets in sandboxes | Zero, always |
| NFR-082 | Authorization decision latency | ≤ 10 ms p95 (in-process, no network call) |
| NFR-083 | Audit completeness | 100 % of the auditable event list in the Security Architecture |
| NFR-084 | Audit chain verification | Runs at least daily; a break alerts within 15 minutes |
| NFR-085 | Secret rotation | Effective without restart, within the configured cache TTL (default 300 s) |
| NFR-086 | Sandbox escape | Zero tolerated; each is a Sev-1 incident requiring an ADR |

---

## 11. Observability

| ID | Requirement | Target |
|---|---|---|
| NFR-090 | Trace correlation | 100 % of workflow, agent, tool, gate, and LLM operations carry `trace_id` + `workflow_id` |
| NFR-091 | Workflow trace sampling | 100 % — workflow traces are **never** sampled; they are the replay substrate |
| NFR-092 | Instrumentation overhead | ≤ 5 % of step wall time |
| NFR-093 | Telemetry availability | Metrics visible within 30 s; logs within 60 s |
| NFR-094 | Secrets in telemetry | Zero |

---

## 12. Maintainability and Extensibility

| ID | Requirement | Target |
|---|---|---|
| NFR-100 | New Capability Pack with no Kernel change | Mandatory — a pack requiring a Kernel change is an architecture defect |
| NFR-101 | New LLM provider | Adapter + configuration only; zero changes to agents or packs |
| NFR-102 | New quality gate | Registered by a pack; zero Kernel change |
| NFR-103 | Pack activation and deactivation | No restart required; deactivation leaves no dangling registration |
| NFR-104 | Circular dependencies | Zero, enforced in CI |
| NFR-105 | Cyclomatic complexity | ≤ 10 per function, warn at 8 |
| NFR-106 | Module size | ≤ 500 lines guideline; > 800 requires justification in review |
| NFR-107 | Cold start (Kernel ready) | ≤ 15 s |

---

## 13. Verification

| Category | Verified by | Exists (2026-07-28)? |
|---|---|---|
| Latency, throughput | `tests/performance/` load suite in CI nightly; production SLO dashboards | No — `tests/performance/` is an empty directory; no SLO dashboards |
| Availability, recovery | `tests/chaos/` (`P07-S03-M42-T01`): kill worker mid-step, kill Redis, drop provider | 2 of 3 real (`test_worker_crash_recovery.py`, `test_provider_outage_recovery.py`); kill-Redis genuinely blocked, not merely deferred — no real Kernel consumer of Redis exists anywhere to chaos-test (product-owner decision, 2026-08-08) |
| Cost | Cost assertions in `tests/benchmarks/`; production cost dashboard | No — `tests/benchmarks/` is an empty directory |
| Quality thresholds | CI quality gates ([ADR-0015](../../18_decision_log/adr/ADR-0015-testing-and-ci.md)) | Partly — lint/types/unit/integration real and green; coverage thresholds (NFR-060–NFR-063) not gated |
| Reproducibility | Run-manifest schema validation; repeat-run variance report | No — no run manifest is written anywhere |
| Security | `tests/security/` organised by threat ID | No — `tests/security/` is an empty directory. Sandbox guarantees are currently asserted from `tests/integration/` instead |
| Observability | Assertions that required correlation IDs are present on emitted telemetry | Partly — spans and one metric (`aios.http.requests`) are asserted; no backend-visibility assertions |

A target without a verification path is not a requirement. Any NFR added here must name how it is measured. The "Exists" column above is the honest current answer and must be updated whenever a suite becomes real — see `../../10_testing/test_strategy.md`.

**Re-baselining commitment.** Every target marked **(baseline)** above must be re-measured against real data by the end of Stage D. Because no performance or benchmark suite exists yet, **none has been re-baselined**; they all still carry their original first-principles estimate. The concrete prerequisite is a populated `tests/performance/` suite plus an OTLP export path to a metrics backend (`feature_inventory.md` §5 rows 4 and 42).

---

## 14. Final Authority

Order of precedence:

1. Project Constitution
2. AI Governance Framework
3. Architecture Decision Records
4. Non-Functional Requirements (this document)
5. Quality Gate configuration
6. Source Code

---

## 15. Related Documents

**Companion requirements documents**
- `../functional/functional_requirements.md` — the capabilities these targets qualify
- `../constraints/constraints.md` — CON-030–CON-038 explain why several targets are shaped as they are

**Live build status**
- `../../19_roadmap/feature_inventory.md` — per-module completion table
- `../../19_roadmap/feature_inventory.md` — the authority on per-module completeness
- `../../19_roadmap/history/INDEX.md` — build history

**Architecture documents that own these targets**
- Latency/throughput/scaling (NFR-010–NFR-025, NFR-107) → `../../03_architecture/platform/system_architecture.md`, `../../11_deployment/deployment_architecture.md`, `../../18_decision_log/adr/ADR-0020-deployment-topology-and-scaling.md`
- Availability/recovery (NFR-030–NFR-038) → `../../03_architecture/kernel/health_lifecycle.md`, `../../03_architecture/workflow/state_management.md`, `../../12_operations/operations_runbook.md`
- Cost controls (NFR-040–NFR-046) → `../../03_architecture/kernel/llm_gateway.md`, `../../03_architecture/workflow/workflow_patterns.md`
- Context/token budgets (NFR-050–NFR-053) → `../../03_architecture/kernel/context_manager.md`
- Quality thresholds (NFR-060–NFR-069) → `../../03_architecture/quality/quality_gates_framework.md`, `../../10_testing/test_strategy.md`, `../../21_templates/CODING_STANDARDS_AND_BEST_PRACTICES.md`
- Reproducibility (NFR-070–NFR-074) → `../../03_architecture/kernel/evaluation_engine.md`, `../../18_decision_log/adr/ADR-0022-reproducibility-over-determinism.md`
- Security (NFR-080–NFR-086) → `../../09_security/security_architecture.md`, `../../09_security/secrets_management.md`, `../../09_security/authentication_authorization.md`
- Observability (NFR-090–NFR-094) → `../../16_observability/observability_stack.md`, `../../03_architecture/kernel/observability.md`
- Retrieval latency (NFR-014) → `../../03_architecture/services/search_vector_search.md`
- Maintainability/extensibility (NFR-100–NFR-106) → `../../03_architecture/platform/platform_sdk.md`, `../../03_architecture/capability_framework/capability_pack_contract.md`
