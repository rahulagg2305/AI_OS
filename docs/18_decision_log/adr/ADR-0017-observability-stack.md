# ADR-0017: Observability Stack — OpenTelemetry with a Tamper-Evident Audit Log

**Status:** Accepted
**Date:** 2026-07-25
**Decision Makers:** Chief Architect
**Related Documents:** `docs/03_architecture/kernel/observability.md`, `docs/16_observability/observability_stack.md`

---

## Context

Observability in AI_OS is not only an operational concern: gate results, token counts, cost, latency, and retry counts are the *product data* that multi-LLM comparison depends on. Telemetry must therefore be structured, correlated, and trustworthy, and must not lock the platform to one backend vendor.

Audit records have a stricter requirement than telemetry: they must be tamper-evident, because they record human approvals, security decisions, and secret access.

## Decision

**Two separate paths, because they have genuinely different requirements.**

**1. Telemetry — OpenTelemetry, vendor-neutral.**

| Concern | Decision |
|---|---|
| Instrumentation | OpenTelemetry SDK for traces, metrics, and logs. No direct vendor SDK anywhere in the codebase. |
| Export | OTLP to an OpenTelemetry Collector. The Collector — not application code — decides the backend. |
| Logging | `structlog` emitting JSON, with trace context injected automatically. Never free-text log lines. |
| Reference backend | Prometheus (metrics), Tempo (traces), Loki (logs), Grafana (visualisation), shipped in the development Compose stack. Production may substitute any OTLP-compatible backend without code change. |
| Correlation | Every record carries `trace_id`, `workflow_id`, and where applicable `step_id`, `agent_id`, `pack_id`+version, `experiment_id`, `principal_id`. Propagated via OpenTelemetry context, including across the sandbox boundary as environment variables. |
| Metric naming | `aios.<subsystem>.<metric>` with OpenTelemetry semantic conventions where they exist. |
| Cost and token metrics | Emitted by the LLM Gateway only, so there is exactly one source of truth for spend. |

**2. Audit — PostgreSQL append-only with hash chaining.**

Audit records (human approvals, authentication and authorization decisions, secret access, configuration changes, pack lifecycle transitions, Tier 1 sandbox executions) are written to an `audit_log` table where each row includes the SHA-256 of the previous row's canonical form. Any deletion or modification breaks the chain and is detectable by a verification job. `UPDATE`/`DELETE` are revoked for the application role.

Audit records are **not** routed through OTLP: a lossy, sampled, buffered telemetry pipeline is the wrong medium for records that must be complete and provably unaltered.

**Never in telemetry:** secret values, raw credentials, full prompt bodies containing customer source code (prompt *identity and version* is recorded, content is not), or personal data. Redaction is applied at the emitting boundary.

## Alternatives Considered

- **A vendor SDK directly (Datadog, New Relic, Honeycomb)** — Better out-of-box experience; rejected because it embeds a vendor in every module and contradicts the Constitution's vendor-neutral instrumentation principle. All remain available as Collector exporters.
- **Prometheus client library + separate tracing library** — Rejected: two correlation models and two propagation mechanisms, which is exactly the fragmentation OpenTelemetry exists to remove.
- **Audit records through the same OTLP pipeline** — Rejected for the completeness and tamper-evidence reasons above.
- **A blockchain or external notary for audit** — Rejected as disproportionate; hash chaining plus restricted grants and offsite backup meets the requirement at a fraction of the complexity.
- **Sampling traces by default** — Rejected for workflow traces specifically: they are the replay substrate and must be complete. Sampling applies only to high-volume infrastructure spans.

## Consequences

### Positive
- Backend-swappable without touching application code.
- One correlated view across workflow, agent, tool, gate, and LLM call.
- Audit integrity is verifiable, not merely asserted.
- Cost data has a single authoritative producer.

### Negative
- Running the Collector plus reference backends adds moving parts to local development; mitigated by a single Compose profile.
- Unsampled workflow traces produce significant volume, requiring a retention policy.
- Hash chaining makes audit writes strictly sequential; acceptable given their low rate.

### Neutral
- Dashboards are defined as code (Grafana JSON in `infra/`) so they are reviewable and versioned.

## Compliance

Complies with the Constitution (Observability by Default), the Logging/Audit/Observability design (immutable or append-only audit, no secrets in telemetry, vendor-neutral instrumentation).

## References

- `docs/16_observability/observability_stack.md`

---

## Implementation Status (appended 2026-07-28, updated 2026-08-01 — not part of the Accepted decision)

**Status in code:** Partially implemented

Real OpenTelemetry spans and one metric are emitted, with `structlog` configured to emit JSON carrying trace context (`ai_os_kernel/observability/`). **Real OTLP/HTTP export is now built** (`P01-S05-M04-T03`): when `OTEL_EXPORTER_OTLP_ENDPOINT` is set (a bootstrap-minimum env var, `ObservabilitySettings`, read directly — corrected from an earlier draft of that same step, which had wrongly used a `PlatformConfig` field), both `configure_tracing()`/`configure_metrics()` use a real `OTLPSpanExporter`/`OTLPMetricExporter` (proven against a real, in-process HTTP receiver, not merely asserted as configured) instead of the console exporters — the identical "one-line change, nowhere else" swap both functions' own docstrings already anticipated. **The reference backend is now real too** (`P01-S05-M04-T04`): `infra/docker-compose.yml`'s `observability` profile stands up a real Collector, Prometheus, Tempo, Loki, and a provisioned Grafana, proven end to end against a real `docker compose up` (a real span/metric genuinely reaching the Collector and becoming queryable in Prometheus). Unset/not deployed is still every real environment's default today — nothing runs this profile automatically. On the audit side the audit log path (`governance.audit_log`) now has a real hash-chained writer and a scheduled verification job (`P01-S05-M04-T05`/`T06`), started in `_lifespan`.

Live status: [`feature_inventory.md`](../../19_roadmap/feature_inventory.md) · Build history: [`history/INDEX.md`](../../19_roadmap/history/INDEX.md)
