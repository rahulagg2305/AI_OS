# Health & Lifecycle Management – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Health & Lifecycle Management  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

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

## Implementation Status (2026-07-28)

**Built:** `kernel/src/ai_os_kernel/health/service.py` — a real Health Aggregator. `HealthService` takes a list of `ComponentCheck` callables (each returning a `ComponentStatus` of `ok` / `degraded` / `error`) and aggregates them into one `ReadinessReport`. §7's rule is genuinely enforced: any component not `ok` makes the overall status `degraded`, never `ready`. The Readiness / Liveness Interface is real in `kernel/src/ai_os_kernel/routes/health.py` — `GET /api/v1/health/live` (which by design touches no external service, so a dependency blip cannot cause a container restart), `GET /api/v1/health/ready` (backed by the real checks, not a hardcoded response), and `GET /api/v1/version`. Checks are registered in the composition root, `kernel/src/ai_os_kernel/bootstrap.py`, which is where step 4 of startup builds the service. Adding a component's check is one list entry; `HealthService` itself does not change.

**Not built:** of §6's six elements only the Health Aggregator and the Readiness/Liveness Interface exist. There is **no Kernel Lifecycle Controller**: §4's six states (`Starting`, `Ready`, `Degraded`, `Stopping`, `Stopped`, `Failed`) are documented vocabulary with no state machine and no persistence — only `ready` and `degraded` are ever produced, and `/health/ready` returns HTTP 200 for both, because no hard dependency yet justifies refusing traffic. There is **no Shutdown Coordinator** and no graceful-shutdown path, so §3's "safe startup and graceful shutdown" and §9's shutdown events do not happen. There is **no Pack Health Collector**: `HealthReport` exists as a model in `kernel/src/ai_os_kernel/capability_manager/pack_contract.py` but nothing produces or collects it, so §5's "activated Capability Packs status" and §7's "Capability Pack health is reported through the Capability Manager and aggregated here" are unimplemented. There is **no Observability Hook**: no health metric, no event, and no log line on a state transition — the Event Bus this would publish to is itself an empty stub. §5's "critical dependencies" dimension has no database check; §5's "ability to accept new workflows" is not reported.

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
| **Health check protocols** | **Kernel-internal protocol decided; the pack protocol is open.** Internally, a check is a synchronous callable returning `ComponentStatus`, registered in `bootstrap.py` ([ADR-0010](../../18_decision_log/adr/ADR-0010-composition-and-dependency-injection.md): explicit composition, no container) — that is settled and built. **Named remaining gap, in two parts.** (a) *Hard vs. soft dependency:* nothing has decided which component failures should make `/health/ready` return 503 rather than a 200 `degraded`. This is a real decision, not a detail — a Kernel that reports `degraded` but keeps accepting workflows it cannot execute is worse than one that refuses traffic. The obvious first candidate is the PostgreSQL connection, since no workflow can start without it. (b) *Pack health polling:* the same undecided three-value policy named in `capability_manager.md` §9 — poll interval, timeout, and the consecutive-failure count that moves a pack to `failed`. Both are self-contained decisions that block no other work and are blocked by no other component. |

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
