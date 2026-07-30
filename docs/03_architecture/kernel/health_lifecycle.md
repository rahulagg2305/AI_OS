# Health & Lifecycle Management – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Health & Lifecycle Management  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-30

---

## 1. Purpose

This document defines the design of **Health & Lifecycle Management** for the AI_OS Platform Kernel.

This component is responsible for tracking and reporting the health and lifecycle state of the Kernel itself and of the Capability Packs running on it. It enables the platform to know whether it is ready to accept work, whether individual packs are healthy, and supports safe startup, shutdown, and recovery.

This document is subordinate to:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Kernel Architecture  
5. Capability Manager Design  

---

## Implementation Status (2026-07-30)

**Built:** `kernel/src/ai_os_kernel/health/service.py` — a real Health Aggregator. `HealthService` takes a list of `ComponentCheck` callables (each returning a `ComponentStatus` of `ok` / `degraded` / `error`, **either directly or as an `Awaitable`** — see below) and aggregates them into one `ReadinessReport` via `async def readiness()`. §7's rule is genuinely enforced: any component not `ok` makes the overall status `degraded`, never `ready`. The Readiness / Liveness Interface is real in `kernel/src/ai_os_kernel/routes/health.py` — `GET /api/v1/health/live` (which by design touches no external service, so a dependency blip cannot cause a container restart), `GET /api/v1/health/ready` (backed by the real checks, not a hardcoded response, `await`s the now-async `readiness()`), and `GET /api/v1/version`. Checks are registered in the composition root, `kernel/src/ai_os_kernel/bootstrap.py`, which is where step 4 of startup builds the service. Adding a component's check is one list entry; `HealthService` itself does not change.

**§5's "critical dependencies" dimension now has a real, database-backed check (2026-07-30) — a genuine revision of this document's own prior "no database check" gap and §10's own prior "synchronous callable" decision, both settled below, not left open.** `manifest_loader_check` (`ai_os_kernel.bootstrap._build_health_service`) now reports one of three real states per discovered pack, not just whether its manifest is schema-valid: (a) schema-valid and genuinely `ACTIVATED` in `catalog.packs` — read via the existing `SqlPackLifecycleRepository.get_pack()` accessor; (b) schema-valid but not genuinely activated (stuck in `installed`/`failed`/any other non-`activated` state, or never registered at all) — reported by name and real state, e.g. `"my-pack [state=failed]"`, and makes the overall check `degraded`; (c) not schema-valid at all (`report.failed`, unchanged). Only attempted when a real `pack_lifecycle_repository` exists on `app.state` (a real database is configured and `_lifespan` has already run) — with no database, or under a bare `TestClient(app)` (which never triggers `_lifespan`), this check's behaviour is byte-for-byte what it was before this revision, the identical "must not depend on a Stage B integration being configured" degrade every other Stage A component in `bootstrap.py` already follows. Proven end to end against a real Postgres container in `tests/integration/test_health_pack_activation.py`: a genuinely activated pack reports `"ready"`/`"ok"`; a pack whose real `catalog.packs` row is pre-seeded in `failed` (the only way to reach a state no method this codebase actually calls ever produces) reports `"degraded"` with that exact real reason in the response body, not a generic message.

**Health check protocol is now mixed sync/async, a real, documented evolution of §10's prior "synchronous callable" decision.** `ComponentCheck` accepts a callable returning `ComponentStatus` directly (unchanged, `configuration_manager_check`'s own shape) **or** an `Awaitable[ComponentStatus]` (new, `manifest_loader_check`'s own shape, since only an async call can genuinely read `catalog.packs.state`) — `HealthService.readiness()` awaits whichever it receives via `inspect.isawaitable()`. A check author picks whichever shape it genuinely needs; nothing forces every check to become async just because one does.

**§10's own "hard vs. soft dependency" gap is resolved (2026-07-30) — the database is a real hard dependency, and `/health/ready` now genuinely returns 503, not just 200 `degraded`.** The decision and its evidence: every functional HTTP route in this codebase (`POST /api/v1/workflows`, `POST /api/v1/workflows/se.delivery_pipeline`, `POST`/`GET /api/v1/packs*`) already independently returns `503` the instant its own required `app.state` object is absent because no database is configured — confirmed by reading each route's own source, not assumed. A Kernel reporting `200 degraded` while every one of its functional routes will 503 anyway is exactly the "worse than refusing traffic" case §7 warns against, so the correct decision is hard, not soft. **Built:** a new `database_check` (`ai_os_kernel.bootstrap._build_health_service`) issues a real `SELECT 1` against `app.state.database_engine` (the same real, pooled engine `_lifespan` already builds, exposed there for this reason), bounded by a short, named `_DATABASE_CHECK_TIMEOUT_SECONDS` (2.0s) so a completely unreachable host fails fast rather than hanging on the OS's own default TCP connect timeout — genuinely testing reachability, not merely whether a URL was configured (`create_async_engine` is lazy; the engine object existing on `app.state` proves nothing about whether the real host behind it is reachable *right now*). `ComponentStatus` gained a `critical: bool = False` field (every pre-existing check defaults to `False`, unaffected); `HealthService.readiness()` returns a new third `ReadinessReport.status` value, `"not_ready"`, whenever any `critical` component's own status is not `"ok"`; `routes/health.py` maps `"not_ready"` to HTTP 503. **Proven end to end against real Postgres containers** in `tests/integration/test_health_database_check.py`: a genuinely reachable database leaves `/health/ready` completely unaffected (200, `"ready"`); a genuinely unreachable one (a well-formed URL with nothing listening on the given port) makes it report 503, `"not_ready"`, with the database component's own real error detail — while every other, non-critical component's own report is untouched.

**§10's own last-remaining named gap — the Pack Health Collector — now has a real, smallest-slice implementation (2026-07-30).** `ai_os_kernel.capability_manager.health_poller.poll_pack_health()` genuinely resolves every one of a discovered pack's own `catalog.agents` rows through a real `AgentRegistry` (an Echo/InMemory-backed one for this specific check, deliberately never the real, credential-gated `se.delivery_pipeline` registry — a genuine, discovered design correction: polling with a credential-gated registry would report every `llm:invoke` agent "unhealthy" whenever no live secret happens to be configured, a common, ordinary dev/CI state, not a broken pack, and three such Kernel restarts would have genuinely, permanently failed the pack with no recovery path). Writes a real `catalog.packs.health` snapshot on every poll (`SqlPackLifecycleRepository.record_health()`) and, after `CONSECUTIVE_FAILURE_THRESHOLD` (3) consecutive unhealthy polls, calls the new `mark_failed()` — the real consequence capability_manager.md §9 named. The one real caller, `ai_os_kernel.bootstrap._lifespan`, runs exactly one poll per discovered pack per Kernel startup — `POLL_INTERVAL_SECONDS` (30.0) is decided but not yet enforced by a background scheduler, the identical, already-accepted "no full worker scheduler" gap this codebase carries for the Workflow Engine. **Proven end to end against real Postgres containers** in `tests/integration/capability_manager/test_health_poller.py`: the real Software Engineering pack's own agents genuinely resolve and `catalog.packs.health` is genuinely populated; a synthetic pack with one genuinely unimportable agent entrypoint proves `consecutive_failures` incrementing across three real, separate polls and the pack genuinely transitioning to `PackState.FAILED` only once the threshold is crossed, never before.

**`/health/ready` now genuinely surfaces the Pack Health Collector's own real `catalog.packs.health` snapshot (2026-07-30) — the natural next increment the prior entry above named, now built.** `manifest_loader_check` reads each genuinely-activated, already-polled pack's own real `health` column (via the existing `get_pack()` accessor) and reports its full detail — real status word, real `consecutive_failures` count against the real `CONSECUTIVE_FAILURE_THRESHOLD`, a real `checked_at` timestamp, and which specific agents are failing, if any (`_format_pack_health_summary`, a new small formatter). **The one genuinely new reporting rule this step adds**: an activated pack with real, non-zero `consecutive_failures` — genuinely degrading, but not yet moved to `PackState.FAILED` — now makes the overall check (and therefore `/health/ready`'s own overall status) `"degraded"` too, a real, visible early warning before the pack actually goes down, not silence until it does. **Proven end to end against real Postgres containers** in `tests/integration/test_health_pack_health_detail.py`: a genuinely healthy pack's full health detail (all agents checked, zero consecutive failures) is visible in a real `200 ready` response; a pack polled twice across two real, separate Kernel "restarts" — each incrementing a real, observed consecutive-failure count via a genuinely unresolvable agent entrypoint — is reported `"degraded"` at `consecutive_failures=2/3`, naming the specific failing agent, while its own `catalog.packs.state` is still genuinely `ACTIVATED`, not yet `FAILED`.

**Not built:** of §6's six elements, the Health Aggregator, the Readiness/Liveness Interface, and a real slice of the Pack Health Collector exist. There is **no Kernel Lifecycle Controller**: §4's six states (`Starting`, `Ready`, `Degraded`, `Stopping`, `Stopped`, `Failed`) are documented vocabulary with no state machine and no persistence — `ready`, `degraded`, and `not_ready` are the only three `ReadinessReport.status` values ever produced, and `/health/ready` genuinely returns HTTP 503 for `not_ready` (a real hard dependency, the database, justifies refusing traffic) and HTTP 200 for the other two. There is **no Shutdown Coordinator** and no graceful-shutdown path, so §3's "safe startup and graceful shutdown" and §9's shutdown events do not happen. There is **no Observability Hook**: no health metric, no event, and no log line on a state transition (poll results are logged, but not emitted as a metric/event) — the Event Bus this would publish to is itself an empty stub. §5's "ability to accept new workflows" is not reported.

Authoritative, always-current status: `../../19_roadmap/feature_inventory.md` (per-module completion table) and `../../19_roadmap/implementation_status.md`. Detailed build history: `../../19_roadmap/history/INDEX.md` (specifically `001_project_bootstrap_and_configuration.md` and `004_stage_a_cross_cutting_infrastructure.md`).

---

## 2. Design Goals

Health & Lifecycle Management must:

- Provide clear readiness and liveness signals
- Expose health of the Kernel and of activated Capability Packs
- Support safe startup and graceful shutdown
- Integrate with the Capability Manager and Dashboard
- Be simple, reliable, and observable

---

## 3. Core Responsibilities

- Track Kernel lifecycle state (starting, ready, degraded, stopping, stopped)
- Aggregate health information from core Kernel components
- Aggregate health information from activated Capability Packs
- Expose health/readiness endpoints or interfaces
- Support graceful shutdown and cleanup
- Emit health-related events and metrics

---

## 4. Lifecycle States (Kernel)

Typical Kernel states:

- Starting
- Ready
- Degraded
- Stopping
- Stopped
- Failed

---

## 5. Health Dimensions

Health reporting should cover at least:

- Kernel core components status
- Activated Capability Packs status
- Critical dependencies (configuration, storage, etc.)
- Ability to accept new workflows

---

## 6. High-Level Structure

```text
Health & Lifecycle Management
│
├── Kernel Lifecycle Controller
├── Health Aggregator
├── Readiness / Liveness Interface
├── Pack Health Collector
├── Shutdown Coordinator
└── Observability Hook
```

---

## 7. Key Design Rules

- Health checks should be lightweight and safe to call frequently.
- A degraded state should be reported rather than presenting an unhealthy system as healthy.
- Capability Pack health is reported through the Capability Manager and aggregated here.
- Startup should not advertise “Ready” until critical components are functional.

---

## 8. Relationship with Other Components

- **Capability Manager** provides pack-level health and lifecycle state.
- **Configuration Manager**, **LLM Gateway**, **Workflow Engine**, and other core components expose health signals.
- **Dashboard** and external orchestrators (when applicable) consume readiness/liveness information.
- **Observability** stack records health transitions.

---

## 9. Observability Requirements

Significant lifecycle and health changes must be logged and emitted as metrics/events, including:

- State transitions
- Failed health checks
- Startup and shutdown events

---

## 10. Current Status

This document defines the design baseline for Health & Lifecycle Management. The three items v1.0 of this section deferred are settled as follows — none is left open as "to be refined."

| Item | Status |
|---|---|
| **Endpoint designs** | **Decided and built.** `GET /api/v1/health/live`, `GET /api/v1/health/ready`, `GET /api/v1/version`, specified in `../../07_api/api_architecture.md` §6.7 under [ADR-0014](../../18_decision_log/adr/ADR-0014-api-style-and-realtime-transport.md) and implemented in `kernel/src/ai_os_kernel/routes/health.py`. The response shape is `ReadinessReport` (`kernel/src/ai_os_kernel/health/service.py`). Nothing further to design. |
| **Integration with deployment environments** | **Decided.** Kubernetes `livenessProbe` → `/health/live`, `readinessProbe` → `/health/ready`, per `../../11_deployment/deployment_architecture.md` and [ADR-0020](../../18_decision_log/adr/ADR-0020-deployment-topology-and-scaling.md); the same probes apply to both the `api` and `worker` process roles built from the one image. **Named remaining gap:** neither a `Dockerfile` nor any Kubernetes manifest exists yet, so the probes are specified against nothing. |
| **Health check protocols** | **Fully decided and built (revised 2026-07-30) — both parts of this row's own gap are now closed.** Internally, a check is a callable returning `ComponentStatus` either directly (synchronous) or as an `Awaitable` (asynchronous, added 2026-07-30 so a check can genuinely read real database state), registered in `bootstrap.py` ([ADR-0010](../../18_decision_log/adr/ADR-0010-composition-and-dependency-injection.md): explicit composition, no container). **(a) Hard vs. soft dependency — DECIDED and BUILT (2026-07-30): the database is hard.** Evidence: every functional route in this codebase (`POST /api/v1/workflows`, `.../se.delivery_pipeline`, `POST`/`GET /api/v1/packs*`) already independently returns 503 the moment its own database-backed `app.state` object is absent — a Kernel reporting `200 degraded` while every functional route 503s anyway is the exact "worse than refusing traffic" case this row used to warn about. `ComponentStatus.critical: bool` + `ReadinessReport.status`'s new third value, `"not_ready"`, implement it generically; `database_check` (`ai_os_kernel.bootstrap._build_health_service`) is the one check marked `critical=True` today, backed by a real, timeout-bounded `SELECT 1` — see `tests/integration/test_health_database_check.py` for the real, both-directions proof. **(b) Pack health polling — DECIDED and BUILT (2026-07-30), smallest real slice.** `capability_manager.md` §9's own three-value policy: `POLL_INTERVAL_SECONDS`=30.0, `POLL_TIMEOUT_SECONDS`=5.0, `CONSECUTIVE_FAILURE_THRESHOLD`=3 (all named constants, `ai_os_kernel.capability_manager.health_poller`). `poll_pack_health()` genuinely resolves a pack's own agents, writes `catalog.packs.health`, and calls the new `mark_failed()` once the threshold is crossed — see `capability_manager.md` §9's own row and `tests/integration/capability_manager/test_health_poller.py` for the real, both-directions proof. **Named remaining gap, deliberately deferred, not silently missing:** `POLL_INTERVAL_SECONDS` is decided but not yet enforced by a real background scheduler — the one real caller runs exactly one poll per pack per Kernel startup, the identical "no full worker scheduler" gap already accepted for the Workflow Engine. |

---

## 11. Final Authority

Order of precedence:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Kernel Architecture  
5. Health & Lifecycle Management  
6. Source Code

---

## 12. Related Documents

**Governing decisions (ADRs):**
- [ADR-0020 — Deployment Topology and Scaling](../../18_decision_log/adr/ADR-0020-deployment-topology-and-scaling.md) — the two process roles these probes serve
- [ADR-0014 — API Style and Realtime Transport](../../18_decision_log/adr/ADR-0014-api-style-and-realtime-transport.md) — the endpoint conventions
- [ADR-0010 — Composition and Dependency Injection](../../18_decision_log/adr/ADR-0010-composition-and-dependency-injection.md) — checks registered in the composition root
- [ADR-0017 — Observability Stack](../../18_decision_log/adr/ADR-0017-observability-stack.md) — health transitions as telemetry

**Superior documents:**
- `../platform/system_architecture.md`
- `kernel_architecture.md`
- `capability_manager.md` — the source of pack-level health and lifecycle state

**Interacting subsystems:**
- `configuration_manager.md`, `llm_gateway.md`, `workflow_engine.md` — components that expose health signals
- `observability.md` — records health transitions; see its "Health Monitoring" list for the components to be covered
- `event_bus.md` — the intended transport for health events (stub)
- `../platform/platform_sdk.md` — a pack's `HealthReport` crosses this boundary
- `../../13_dashboard/dashboard_architecture.md` — the System Health view
- `../../11_deployment/deployment_architecture.md` — probe wiring, graceful-shutdown expectations
- `../../12_operations/operations_runbook.md` — operator response to a degraded report
- `../../16_observability/observability_stack.md`

**Tables:** this component owns none — readiness is computed live and never persisted. See `../../08_database/data_model.md` for the platform's table inventory.

**Reference:**
- `../../02_requirements/non_functional/nfr.md` — startup-time and readiness targets
- `../../20_glossary/glossary.md`
- `../../19_roadmap/feature_inventory.md`, `../../19_roadmap/implementation_status.md`, `../../19_roadmap/history/INDEX.md`
