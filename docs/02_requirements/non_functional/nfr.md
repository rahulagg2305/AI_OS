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

| Category | Verified by |
|---|---|
| Latency, throughput | `tests/performance/` load suite in CI nightly; production SLO dashboards |
| Availability, recovery | `tests/integration/` chaos cases: kill worker mid-step, kill Redis, drop provider |
| Cost | Cost assertions in `tests/benchmarks/`; production cost dashboard |
| Quality thresholds | CI quality gates ([ADR-0015](../../18_decision_log/adr/ADR-0015-testing-and-ci.md)) |
| Reproducibility | Run-manifest schema validation; repeat-run variance report |
| Security | `tests/security/` organised by threat ID |
| Observability | Assertions that required correlation IDs are present on emitted telemetry |

A target without a verification path is not a requirement. Any NFR added here must name how it is measured.

---

## 14. Final Authority

Order of precedence:

1. Project Constitution
2. AI Governance Framework
3. Architecture Decision Records
4. Non-Functional Requirements (this document)
5. Quality Gate configuration
6. Source Code
