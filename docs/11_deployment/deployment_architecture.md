# Deployment Architecture – AI_OS

**Project:** AI_OS (AI Operating System)
**Document:** Deployment Architecture
**Version:** 1.0
**Status:** Approved
**Last Updated:** 2026-07-25

---

## Implementation Status (updated 2026-08-01)

**Barely built — this document is close to pure specification.** Read this before treating any deployment artifact below as existing.

**Built:** `infra/docker-compose.yml`'s `core` profile (Postgres 16 + pgvector, Redis 7) and, as of `P01-S05-M04-T04`, its real `observability` profile (Collector, Prometheus, Tempo, Loki, a provisioned Grafana — §5's own documented profile table, proven end to end against a real `docker compose up`); `infra/environments/{local,dev,staging,production}.yaml`. Alembic migrations run as a separate command, consistent with the migration-as-Job principle here.

**Not built:**
- **There is no Dockerfile anywhere in the repository.** Neither documented process role (`api`, `worker`) has an image, so the multi-stage build, digest-pinned bases, non-root uid 10001, and read-only filesystem described below do not exist. CI's image-build stage is deliberately gated off for this reason. The `core`/`full` Compose profiles are consequently not literally "everything" §5's own table eventually names — only `observability` is genuinely complete today, since it needs no Kernel image at all (the Kernel runs as a local, non-containerised dev process pointing its real OTLP exporter at the Collector).
- **No Kubernetes manifests and no Helm chart.** `infra/kubernetes/` and `infra/terraform/` have no tracked content and are absent from a fresh clone. Every K8s object specified here — Deployments, Service, Ingress, HPA, ConfigMap, ExternalSecret, ServiceAccount, PodDisruptionBudget, and the **NetworkPolicy egress allowlist** — is unbuilt.
- **No separate sandbox image.** `DockerSandbox` is real and live-verified, but pulls the public `python:3.12-slim` tag; it is **tag-pinned, not digest-pinned**, contrary to the hardening target here and in `../09_security/security_architecture.md` §10.
- **No worker role deployment.** `run_to_completion` drives a single workflow instance; there is no multi-instance worker loop, so lease-based horizontal scaling is untested in a real deployment.
- **No backup/restore tooling and no rehearsed restore drill**; no PITR configuration. The audit log itself now has a real writer and hash chain (`P01-S05-M04-T05`/`T06`), but there is still no offsite export of it.
- **No release pipeline, no staging verification, no canary.**

Consequence: AI_OS currently runs only as a local development process against Compose-provided Postgres. Treat this document as the Stage G target, not a description of a deployable system.

Authoritative, always-current status: the per-module completion table in `feature_inventory.md` and `implementation_status.md`; build history in `history/INDEX.md` (all under `docs/19_roadmap/`).

## 1. Purpose

This document specifies how AI_OS is packaged, configured, and deployed, and how it scales. It implements [ADR-0020](../18_decision_log/adr/ADR-0020-deployment-topology-and-scaling.md).

---

## 2. Process Roles

One image, two entry points ([ADR-0020](../18_decision_log/adr/ADR-0020-deployment-topology-and-scaling.md)):

| Role | Entry point | Responsibility | Scaling |
|---|---|---|---|
| `api` | `ai_os_kernel.entrypoints.api:app` (Uvicorn) | HTTP + WebSocket, reads, workflow submission | Stateless; N replicas behind a load balancer |
| `worker` | `ai_os_kernel.entrypoints.worker:main` | Workflow execution, agents, tools, gates, sandboxes | N replicas leasing work via `SKIP LOCKED` |

Both roles run the same composition root, so a component behaves identically in either. The only difference is which loop is started.

Optional single-process mode (`ai_os_kernel.entrypoints.all_in_one`) runs both in one process for local development; it is not supported for production.

---

## 3. Container Image

Multi-stage build, reproducible:

```text
Stage 1 (builder)   python:3.12-slim
                    install uv → uv sync --frozen --no-dev → build wheels
Stage 2 (runtime)   python:3.12-slim (pinned by digest)
                    copy virtualenv only
                    non-root user (uid 10001)
                    no build toolchain, no package manager
                    HEALTHCHECK → /api/v1/health/live (api role)
```

Rules:
- Base images pinned by **digest**, not tag, and rebuilt on a schedule for CVE patching.
- `uv sync --frozen` — the build fails if `uv.lock` is out of date, so an image can never contain unlocked dependencies.
- Runs as non-root; the filesystem is read-only except `/tmp` and the workspace mount.
- No secrets in the image, in any layer, or in build args.
- Image is labelled with the Git SHA and semantic version; the Kernel reports both at `/health/detail`, which is what makes a deployed run's `run_manifest` verifiable.

**Sandbox images** are separate, minimal, pinned by digest, and pre-pulled onto nodes so Tier 1 cold start meets NFR-015.

---

## 4. Environments

| Environment | Topology | Database | Purpose |
|---|---|---|---|
| `local` | all-in-one process or Compose | SQLite (reduced) or Postgres container | Development |
| `dev` | Compose, single node | Postgres container | Shared integration |
| `staging` | Kubernetes, 2 api + 2 worker | Managed Postgres | Pre-production verification |
| `production` | Kubernetes, ≥ 2 api + ≥ 3 worker | Managed Postgres with replica + PITR | Production |

`staging` must match `production` in topology and configuration shape, differing only in scale and credentials. A configuration key that exists in production and not in staging is a defect.

---

## 5. Docker Compose (local and single node)

Services: `api`, `worker`, `postgres` (with `pgvector`), `redis`, `otel-collector`, `prometheus`, `tempo`, `loki`, `grafana`.

Profiles keep the footprint proportionate:

| Profile | Brings up |
|---|---|
| `core` | api, worker, postgres, redis |
| `observability` | + collector, prometheus, tempo, loki, grafana |
| `full` | everything |

The worker mounts a container runtime socket **only in local development** and never in a deployed environment. Local sandboxing uses rootless Podman where available.

---

## 6. Kubernetes

```text
Deployment/aios-api        replicas ≥ 2   role=api
Deployment/aios-worker     replicas ≥ 3   role=worker
Service/aios-api           ClusterIP → Ingress (TLS)
HorizontalPodAutoscaler    target: worker lease-queue depth
ConfigMap/aios-config      non-secret configuration
ExternalSecret/aios-secrets  Vault or cloud secret manager → env references only
ServiceAccount/aios        least-privilege RBAC
PodDisruptionBudget        minAvailable: 1 per role
NetworkPolicy              egress allowlist: Postgres, Redis, providers, OTLP
```

**Probes**, sized for a platform whose steps run for minutes:

| Probe | Path | Notes |
|---|---|---|
| `livenessProbe` | `/api/v1/health/live` | Process responsive only. Must **not** depend on Postgres, or a brief database blip restarts every pod and turns a small incident into an outage. |
| `readinessProbe` | `/api/v1/health/ready` | Dependency-aware; removes the pod from service without restarting it. |
| `startupProbe` | `/api/v1/health/live` | Generous window (NFR-107: ready within 15 s). |

**Graceful shutdown:** `terminationGracePeriodSeconds: 330` against a 300 s drain (NFR-036). On `SIGTERM` a worker stops accepting new leases, finishes in-flight steps, releases leases, and exits. An unfinished step's lease expires and is reclaimed elsewhere — no work is lost.

**Sandbox execution on Kubernetes.** Worker pods need a container runtime for Tier 1 steps. The Docker socket is never mounted. Two supported patterns:

1. **Rootless Podman sidecar** — a sidecar in the worker pod runs Podman rootless; the worker talks to it over a local socket. Default.
2. **Dedicated sandbox node pool with gVisor** — worker pods scheduled to nodes with the `runsc` runtime class via `runtimeClassName: gvisor`. Recommended for hostile-input or multi-tenant deployments ([ADR-0016](../18_decision_log/adr/ADR-0016-tool-execution-sandboxing.md)).

`hostPID`, `hostNetwork`, `privileged`, and host path mounts beyond the workspace volume are prohibited.

---

## 7. Configuration at Deploy Time

Precedence is the single order defined in `../03_architecture/kernel/configuration_manager.md`. In deployment terms:

| Layer | Source |
|---|---|
| Built-in defaults | Code |
| Pack defaults | Pack manifests |
| Platform config | `config/platform.yaml` in the image |
| Environment config | `ConfigMap` / `infra/environments/<env>.yaml` |
| Runtime overrides | API `PATCH /config`, audited |
| Experiment overrides | Per-run, isolated |
| Secret values | Resolved at use from `secret://` references |

Environment variables carry only the bootstrap minimum: `AIOS_ENV`, `AIOS_ROLE`, `AIOS_DATABASE_URL`, `AIOS_REDIS_URL`, `AIOS_SECRET_BACKEND`, `OTEL_EXPORTER_OTLP_ENDPOINT`. Everything else comes from configuration files, so the deployment does not become a second, undocumented configuration system.

---

## 8. Database Migrations

1. Migrations run as a **separate job**, never on application startup — concurrent replicas racing on migration is a corruption path.
2. Kubernetes: a `Job` (or Helm `pre-upgrade` hook) that must succeed before the new `Deployment` rolls.
3. All migrations follow **expand → migrate → contract**, so the previous application version keeps working against the new schema during the roll.
4. Production migrations require human approval ([ADR-0007](../18_decision_log/adr/ADR-0007-human-governance-for-critical-decisions.md)).
5. Rollback is by a forward-fixing migration; `downgrade` exists and is tested but is a break-glass path, not the plan.

---

## 9. Release Process

```text
1  Merge to default branch          all CI stages green
2  Tag  vX.Y.Z                      semantic version
3  Build + push image               labelled with Git SHA + version
4  Deploy to staging                migrations job → rolling update
5  Verify on staging                smoke suite + one full workflow run
6  Human approval                   approval:decide:release
7  Deploy to production             migrations job → rolling update
8  Verify                           health, error rate, cost rate, one canary workflow
```

Rolling update with `maxUnavailable: 0`, `maxSurge: 1`. Rollback is redeploying the previous image tag; if the release included a contracting migration, rollback requires the forward-fix path from §8.

---

## 10. Backup and Recovery

| Asset | Method | Target |
|---|---|---|
| PostgreSQL | Managed continuous archiving + PITR | RPO ≤ 5 min (NFR-034) |
| Blob artifacts | Object-store versioning + lifecycle rules | RPO ≤ 5 min |
| Audit log | Included in Postgres backup **plus** an independent offsite export | No loss tolerated |
| Redis | None — cache only, rebuilt on loss (NFR-038) | n/a |
| Configuration | Version-controlled in Git | n/a |
| Secrets | Backed up by the secret backend, not by AI_OS | n/a |

**Restore is rehearsed quarterly, not assumed.** The rehearsal restores to a scratch environment, verifies the audit hash chain end to end, and confirms an in-flight workflow resumes. A backup that has never been restored is a hypothesis.

---

## 11. Capacity Sizing (starting point)

Sized against the NFR scale assumptions; re-baseline against measurement in Stage D.

| Component | Requests | Limits |
|---|---|---|
| `api` pod | 0.5 CPU, 1 GiB | 2 CPU, 2 GiB |
| `worker` pod | 1 CPU, 2 GiB | 4 CPU, 6 GiB |
| Tier 1 sandbox | 0.5 CPU, 512 MiB | 2 CPU, 4 GiB, 256 PIDs |
| PostgreSQL | 4 vCPU, 16 GiB, 200 GiB SSD | Scale with corpus size |
| Redis | 1 vCPU, 2 GiB | Cache only |

Worker limits are deliberately higher than requests because a Tier 1 step is bursty; sandbox limits are hard because untrusted code must not be able to starve the node.

---

## 12. Final Authority

Order of precedence:

1. Project Constitution
2. Architecture Decision Records
3. Deployment Architecture (this document)
4. `infra/` manifests and Helm values
5. Source Code
