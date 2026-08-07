# `ai-os` Helm chart (`P07-S01-M40-T01`)

Deploys the real, two-process-role image (`Dockerfile`,
`deploy/entrypoint.sh`, `P01-S01-M40-T04`) as `Deployment/aios-api` and
`Deployment/aios-worker`, per ADR-0020 and
`docs/11_deployment/deployment_architecture.md` §6.

## Real, built, and validated

- `Deployment/aios-api` (replicas ≥ 2), `Deployment/aios-worker`
  (replicas ≥ 3) — both run the one real image, differing only in
  `AIOS_ROLE`.
- `Service/aios-api` (ClusterIP).
- `ConfigMap/aios-config` (non-secret env: `AIOS_ENV`,
  `OTEL_EXPORTER_OTLP_ENDPOINT`, `AIOS_SECRET_BACKEND`).
- `ServiceAccount/aios`.
- `PodDisruptionBudget` (`minAvailable: 1`) for each role.
- `HorizontalPodAutoscaler/aios-worker` — CPU-based (see "Disclosed
  gaps" below for why, not lease-queue depth as the document names).
- Real liveness/readiness/startup probes on `aios-api`, at the real,
  verified paths (`/api/v1/health/live`, `/api/v1/health/ready` —
  confirmed directly against `kernel/src/ai_os_kernel/routes/health.py`'s
  own `APIRouter(prefix="/api/v1", ...)`, matching
  `deployment_architecture.md` §6's own table exactly).
- `terminationGracePeriodSeconds: 330` on both roles (NFR-036).
- `NetworkPolicy/aios-egress` (`P07-S01-M40-T02`) — **opt-in**
  (`networkPolicy.enabled`, default `false`; zero regression for a
  default install). When enabled: a real DNS (`kube-dns`) + same-namespace
  baseline (covers `otel-collector`) always applies, plus any real,
  literal Kubernetes `NetworkPolicyEgressRule` entries an operator
  supplies via `networkPolicy.egress.additionalRules` for their own
  real Postgres/Redis/provider destinations — see `values.yaml`'s own
  comment for why this chart cannot know those destinations itself.
- Validated both offline (`helm lint`, `helm template`) and against a
  real, temporary `kind` cluster: genuine `kubectl apply --dry-run=server`
  followed by a genuine, non-dry-run apply against a live Kubernetes
  API server, confirmed via real `kubectl get` — see
  `tests/integration/infra/test_ai_os_helm_chart.py`.

## Disclosed gaps — real, not fabricated

The following items `deployment_architecture.md` §6 names are
genuinely unbuilt, each for a real, specific reason, not oversight:

- **`aios-worker` has no liveness/readiness/startup probes.** The
  `worker` entry point runs no HTTP server at all (verified directly
  in `kernel/src/ai_os_kernel/entrypoints/worker.py`) — the documented
  probe paths exist only on the `api` role. Probing a path that does
  not exist would fail every worker pod permanently.
- **HPA scales on CPU, not "worker lease-queue depth."** That custom
  metric needs a metrics-adapter (Prometheus Adapter or KEDA) neither
  built nor installed anywhere in this repo.
- **No `Ingress`.** No ingress controller, TLS issuer, or hostname is
  decided anywhere in this repo; `Service/aios-api` stays `ClusterIP`
  only, matching the document's own "ClusterIP -> Ingress" (the arrow
  implies a later hop, not this chart's own scope).
- **No `ExternalSecret`.** The `ExternalSecret` CRD requires the
  External Secrets Operator installed in-cluster, and no Kubernetes
  secrets backend has been selected — the Vault backend itself
  (`P07-S02-M19-T01`) is still unbuilt. This chart instead references
  an already-existing, externally-managed `Secret`
  (`values.yaml`'s own `existingSecretName`, default `aios-secrets`)
  by name only — it never creates, populates, or reads a secret value
  itself.
- **No Podman-sidecar or gVisor sandbox pattern.** `deployment_architecture.md`
  §6's own text already calls this "deliberate node configuration" —
  a real, separate, larger piece of work, not a Helm-chart-shaped one.

## Usage

```
helm lint infra/kubernetes/helm/ai-os
helm template aios infra/kubernetes/helm/ai-os > /tmp/rendered.yaml
kubectl apply --dry-run=client -f /tmp/rendered.yaml
```

A real install additionally requires a real `Secret` named
`aios-secrets` (or `--set existingSecretName=...`) already present in
the target namespace, holding `AIOS_DATABASE_URL`/`AIOS_REDIS_URL`.
