# Deployment Architecture – AI_OS

**Project:** AI_OS (AI Operating System)
**Document:** Deployment Architecture
**Version:** 1.0
**Status:** Approved
**Last Updated:** 2026-07-25

---

## Implementation Status (updated 2026-08-10, `P07-S01-M40-T01`)

**Barely built — this document is close to pure specification.** Read this before treating any deployment artifact below as existing.

**Built:** `infra/docker-compose.yml`'s `core` profile (Postgres 16 + pgvector, Redis 7) and, as of `P01-S05-M04-T04`, its real `observability` profile (Collector, Prometheus, Tempo, Loki, a provisioned Grafana — §5's own documented profile table, proven end to end against a real `docker compose up`); `infra/environments/{local,dev,staging,production}.yaml`. Alembic migrations run as a separate command, consistent with the migration-as-Job principle here.

**Updated (`P01-S01-M40-T04`): a real, working `Dockerfile` now exists at the repo root — closing the "There is no Dockerfile anywhere" gap this section used to name.** Multi-stage build (`builder`: `python:3.12-slim`, `uv sync --frozen --no-dev`; `runtime`: `python:3.12-slim` **digest-pinned**, non-root **uid 10001**, no build toolchain or package manager), `HEALTHCHECK` against `/api/v1/health/live`, image labelled with `GIT_SHA`/`VERSION` build args (never hardcoded), no secrets in any layer. One image, two entry points, selected at container start by `AIOS_ROLE` (`deploy/entrypoint.sh`) — exactly ADR-0020's model. **Proven real, locally**: `docker build` succeeds; the `api`-role container starts, reaches Docker's own `healthy` state, and genuinely serves `/api/v1/health/live` (200), `/api/v1/health/ready` (503, real component detail, gracefully degraded with no database configured — not a crash), and `/api/v1/version`; the manifest loader genuinely discovers the real `software-engineering` pack inside the image. **Not yet proven**: the documented **read-only root filesystem** (`docker run --read-only --tmpfs /tmp`) — the image does not need root-fs writes at import time, but this specific runtime flag combination has not been exercised.
**Updated (`P01-S01-M40-T05`): the `worker` role now genuinely runs standalone — closing the gap the line above used to disclose.** `ai_os_kernel.bootstrap.build_workflow_worker_loop` is the one real construction shared by the `api` role's own background task and `ai_os_kernel.entrypoints.worker:main`, so neither duplicates it. Each process gets a real, distinct `worker_id` (hostname + PID) rather than one shared literal, since ADR-0020's own *N*-replica target means `workflow_leases.worker_id` must be able to tell replicas apart. A real, reproduced bug was found and fixed along the way: registering the standalone process's `SIGTERM`/`SIGINT` handlers *after* any `ai_os_kernel.bootstrap` call silently broke `asyncio`'s signal delivery for the rest of the process (isolated to OpenTelemetry SDK configuration in that import graph) — `docker stop` always fell through to a hard `SIGKILL`. Fixed by registering signal handlers first, before any such call. **Proven real, locally, against a real Postgres**: a standalone `worker`-role container (no `api` process involved) discovers and completes a real, independently-seeded workflow instance across two real poll ticks, then stops cleanly (`exit 0`, a real `graceful_shutdown.job_stopped` log line) on `docker stop` — the identical "stop leasing, finish in-flight work, exit" shape §7 documents. `worker`-role horizontal scaling itself (multiple real replicas contending for leases) is still untested in any real deployment — this step makes one replica genuinely real, not the N-replica scenario.
- **Updated (`P07-S01-M40-T01`): a real, partial Helm chart now exists — `infra/kubernetes/helm/ai-os/`, closing the "no Kubernetes manifests and no Helm chart" gap this line used to name in full.** `Deployment/aios-api` (replicas 2)/`Deployment/aios-worker` (replicas 3), `Service/aios-api` (ClusterIP), `ConfigMap/aios-config`, `ServiceAccount/aios`, `PodDisruptionBudget` (one per role), and `HorizontalPodAutoscaler/aios-worker` are all real — validated via `helm lint`/`helm template` and, further, against a real, temporary `kind` cluster (`kubectl apply --dry-run=server`, then a genuine, non-dry-run apply against a live Kubernetes API server, confirmed via `kubectl get`; pods correctly report `ErrImagePull`, since no container registry has been decided anywhere in this repo — the one real, expected, disclosed limitation, not a manifest defect). Probes on `aios-api` use the real, verified `/api/v1/health/live`/`/api/v1/health/ready` paths this section's own table already names. **Still genuinely unbuilt, each for a real, specific, disclosed reason (see the chart's own README.md): no `Ingress`** (no ingress controller/TLS issuer/hostname decided anywhere); **no `ExternalSecret`** (requires the External Secrets Operator in-cluster — the Vault backend itself is real as of `P07-S02-M19-T01`, but no Kubernetes-specific secrets-sync mechanism exists; the chart instead references an already-existing, externally-managed `Secret` by name only); **the HPA scales on CPU, not "worker lease-queue depth"** (that custom metric needs a metrics-adapter — Prometheus Adapter or KEDA — neither built nor installed anywhere); **`aios-worker` has no HTTP probes at all** (the `worker` entry point runs no HTTP server — verified directly in its own source — so the documented probe paths exist only on the `api` role). `infra/terraform/` remains empty.
- **Updated (`P07-S01-M40-T02`): the `NetworkPolicy` egress allowlist is now real too, opt-in (`networkPolicy.enabled`, default `false` — zero regression for a default install, product-owner decision).** When enabled, a real, non-invented DNS (`kube-dns`) + same-namespace baseline (covers `otel-collector`) always applies; real Postgres/Redis/provider destinations are environment-specific (managed services this chart does not deploy — this document's own table above names them "Managed Postgres" in every real target environment), so they are the operator's own responsibility to declare via `networkPolicy.egress.additionalRules` — a real, literal Kubernetes `NetworkPolicyEgressRule` list, never an invented value. Proven both offline and against a real, temporary `kind` cluster, the identical proof shape `P07-S01-M40-T01` already established.
- **Updated (`P07-S01-M40-T01`, continued, 2026-08-10): the rootless Podman sidecar pattern (§6's own pattern 1, "Default") is now real, opt-in (`sandboxSidecar.enabled`, default `false` — zero regression), and genuinely proven up through one specific real boundary, not fabricated past it.** `values.yaml`'s own extensive comment records the full design history: a first fork (`/dev/fuse`/`fuse-overlayfs` needs a `hostPath` device mount, prohibited by this section's own "host path mounts beyond the workspace volume are prohibited" rule) was resolved by switching to Podman's `vfs` storage driver instead — no `/dev/fuse`, no host path, at the disclosed cost of layer duplication instead of copy-on-write (accepted for short-lived Tier 1 execution). Two narrow `securityContext` relaxations on the sidecar container only (never the worker container, never `hostPID`/`hostNetwork`/`privileged`) were confirmed necessary by real, local reproduction: `SYS_ADMIN` (for `unshare(CLONE_NEWUSER)`) and `seccompProfile: Unconfined` (for `crun`'s own session-keyring `keyctl` call). Proven end to end against a real, local Docker daemon: a genuine nested container (network disabled, read-only root, uid 65534 — `DockerSandbox`'s own real Tier 1 controls) starts and returns real output through the shared socket, exactly as `DockerSandbox.docker.from_env()`'s own `DOCKER_HOST` handling expects, with zero Kernel code change. **A second, deeper real limitation was found only by testing the identical manifest against a genuine `kind` cluster (containerd CRI), not a bare `docker run`: Podman's own setuid `newuidmap`/`newgidmap` helpers fail with "operation not permitted" under this runtime, confirmed unaffected by `SYS_ADMIN`, `seccomp: Unconfined`, or `allowPrivilegeEscalation: true` — most likely a `nosuid` container-filesystem mount flag no Pod-level `securityContext` field can override.** Per product-owner decision, the chart change ships disclosed-but-unverified rather than being reverted or further escalated: `tests/integration/infra/test_ai_os_helm_chart.py::test_the_sandbox_sidecar_is_genuinely_accepted_but_cannot_yet_start_rootless_podman` asserts this exact, current, reproducible failure explicitly (the same "assert the real expected failure, don't silently tolerate a different one" discipline the base chart's own `ErrImagePull` assertion already established), so a future environment change that resolves it makes this test fail loudly rather than leaving a stale assertion in place. **The gVisor pattern (§6's pattern 2) remains entirely unbuilt, but a real feasibility investigation (2026-08-10, `P07-S01-M40-T01`) found it genuinely de-risked, the opposite result from the Podman pattern's own containerd-CRI blocker**: a real `runsc` + `containerd-shim-runsc-v1` (downloaded from the real gVisor release bucket), installed into a throwaway `kind` node's containerd config and exposed via a real `RuntimeClass` (`handler: runsc`), successfully ran a real test pod — `kubectl logs` showed the genuine gVisor kernel signature (`Linux version 4.19.0-gvisor`, `dmesg`'s own "Starting gVisor..." banner), on the identical Docker Desktop/WSL2 kernel this whole chart is already validated against. Architecturally simpler than Podman too: §6's pattern 2 schedules the *whole worker pod* onto gVisor-capable nodes via `runtimeClassName: gvisor` — no nested container runtime, no sidecar, no `newuidmap`-class helper at all, so `LocalSubprocessSandbox` (not `DockerSandbox`) would back Tier 1 tool execution once a worker pod is itself already kernel-isolated by `runsc`. Not yet built into the chart (an opt-in `RuntimeClass` template + `values.yaml` knob, mirroring `sandboxSidecar.enabled`'s own precedent, proven the identical throwaway-`kind`-cluster way) — a real, now de-risked next slice, not attempted this step, and the throwaway cluster used for this investigation was deleted afterward (no persistent infrastructure left behind). A related, more targeted question — whether ADR-0016's own `DockerSandbox(runtime="runsc")` config line can be verified against *this machine's actual local Docker Engine* — remains open: that would need `runsc` registered in Docker Desktop's own persistent `daemon.json`, a change to the host outside this repo, deliberately not made without explicit product-owner approval (see `P03-S01-M20-T05`'s own ticket for the same finding recorded from that ticket's side).
- **No separate sandbox image.** `DockerSandbox` is real and live-verified, but pulls the public `python:3.12-slim` tag; it is **tag-pinned, not digest-pinned**, contrary to the hardening target here and in `../09_security/security_architecture.md` §10.
- **Updated (`P07-S01-M40-T03`): real backup/restore tooling and a real, automated rehearsal now exist** — `infra/scripts/backup.sh`/`restore.sh` plus `tests/integration/infra/test_backup_restore_rehearsal.py`, proving a real hash-chain `verify_chain()` pass survives a genuine restore into a separate, empty database. Still missing: PITR configuration, the audit log's own offsite export, and the "in-flight workflow resumes" half of §10's own rehearsal description (see that section's own Implementation Status note for the full, disclosed breakdown).
- **No release pipeline, no staging verification, no canary.**

Consequence: AI_OS now has a real, runnable container image and a real, partial Helm chart proven against a genuine (if temporary, local) Kubernetes cluster, including a real, opt-in `NetworkPolicy` egress allowlist — but no real registry, no managed cluster, no Ingress/ExternalSecret, and no release pipeline. Treat this document as the Stage G target, not a description of a fully deployable production system.

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

A single-process mode (`ai_os_kernel.entrypoints.all_in_one`) is **designed but not built** — corrected 2026-08-11 (full-project audit), which found this line previously described it in the present tense as though it existed. `kernel/src/ai_os_kernel/entrypoints/` contains only `__init__.py`, `api.py` and `worker.py`; there is no `all_in_one` module. It would not be supported for production in any case. For local development today, run the `api` role — its `_lifespan` already starts the same worker loop as a background task (see the Implementation Status note above), so one process genuinely does both.

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

**Updated (`P07-S01-M40-T03`): the rehearsal mechanism itself is now real, not merely documented — `infra/scripts/backup.sh`/`restore.sh` (real `pg_dump`/`pg_restore`, custom format, portable across every Postgres deployment this document names) plus a real, automated, repeatable proof (`tests/integration/infra/test_backup_restore_rehearsal.py`): a genuinely populated database is backed up, restored into a completely separate, genuinely empty one, and the restored `governance.audit_log` passes a real `verify_chain()` — the hash-chain-integrity half of this section's own literal rehearsal description. **Still disclosed, unbuilt**: the "confirms an in-flight workflow resumes" half (this rehearsal seeds only `audit_log`, not a real paused `workflow_instances` row); the quarterly cadence itself (a scheduling/ops concern, not a mechanism); and Managed continuous archiving/PITR (a cloud-provider-specific capability — no provider is decided anywhere in this repo, so it cannot be built without inventing one).

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
