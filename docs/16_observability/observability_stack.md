# Observability Stack – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Observability Stack (Logging, Metrics, Tracing)  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## Implementation Status (updated 2026-08-01)

**Built:** `structlog` JSON logging with trace-context binding; a real OpenTelemetry `TracerProvider` producing a genuine span per HTTP request with the documented attributes; **exactly one** metric, `aios.http.requests`. **Real OTLP/HTTP export exists** (`P01-S05-M04-T03`) — `configure_tracing()`/`configure_metrics()` use a real `OTLPSpanExporter`/`OTLPMetricExporter` when `OTEL_EXPORTER_OTLP_ENDPOINT` is set (a bootstrap env var, `ObservabilitySettings`), proven against a real receiver in tests; the console exporters remain the default. **The Collector and reference backends are real too** (`P01-S05-M04-T04`): `infra/docker-compose.yml`'s `observability` profile — real Prometheus, Tempo, Loki, and a provisioned Grafana with one real dashboard panel (`aios.http.requests`), proven end to end against a real `docker compose up`. The audit path (`governance.audit_log`) is real too (`P01-S05-M04-T05`/`T06`): a hash-chained writer, `row_hash`/`prev_hash` computed per row, and a scheduled verification job started in `_lifespan`.

**Not built:** nothing runs the `observability` Compose profile automatically — opt-in, local-development tooling only, not part of any deployment. Loki genuinely has no log producer wired to it yet: the Kernel emits structured logs to its own stdout and is not containerised (no Dockerfile exists), so there is no real log-shipping path (a Promtail sidecar scraping container stdout is the standard one) — disclosed in `infra/observability/loki-config.yaml`'s own header, not papered over. Of the metrics named in the metric-catalogue section, **only `aios.http.requests` exists** — none of the workflow, LLM, gate, sandbox, outbox, or authz metrics do. No alerting and only one real dashboard panel. UPDATE/DELETE revocation for a dedicated application database role is not applied (no such role exists yet) and there is no offsite audit-log export.

Authoritative, always-current status: `../19_roadmap/feature_inventory.md`. Build history: `../19_roadmap/history/INDEX.md`.

## 1. Purpose

This document defines the concrete Observability Stack architecture for AI_OS — how logs, metrics, and traces are collected, correlated, stored, and consumed.

It builds directly on the Logging, Audit & Observability Design document and focuses on the practical stack and integration points.

This document is subordinate to:

1. Project Constitution  
2. System Architecture  
3. Kernel Architecture  
4. Logging, Audit & Observability Design  

---

## 2. Design Goals

The Observability Stack must:

- Collect structured logs, metrics, and traces from all major components
- Correlate them via Trace ID and Workflow ID
- Support the Dashboard and Evaluation Engine
- Enable debugging, performance analysis, cost analysis, and multi-LLM comparison
- Be vendor-neutral at the instrumentation level
- Support configurable retention and export

---

## 3. Stack Overview

Technology decided in [ADR-0017](../18_decision_log/adr/ADR-0017-observability-stack.md). Note the **two separate paths** — telemetry and audit have different requirements and do not share a pipeline.

```text
TELEMETRY PATH (may be sampled and buffered)

Producers: Kernel · Services · Capability Packs
    │  OpenTelemetry SDK  (traces, metrics, logs)
    │  structlog → JSON logs with trace context injected
    ▼
OTLP → OpenTelemetry Collector        ← the ONLY place a backend is chosen
    ▼
├── Prometheus   metrics       (reference)
├── Tempo        traces        (reference)
└── Loki         logs          (reference)
    ▼
Consumers: Grafana · Dashboard API · Alertmanager · Evaluation Engine


AUDIT PATH (complete and tamper-evident — never sampled)

Security Manager · Workflow Engine · Capability Manager · Git Service
    ▼
governance.audit_log  (PostgreSQL, append-only, SHA-256 hash chained)
    ▼
Daily verification job → alert on chain break
    ▼
Independent offsite export
```

No application code imports a vendor SDK. Substituting a backend is a Collector configuration change.

### 3.1 Metric naming

`aios.<subsystem>.<metric>`, following OpenTelemetry semantic conventions where they exist. Examples:

```text
aios.workflow.instances_active          gauge
aios.workflow.steps_completed           counter
aios.workflow.step_duration_ms          histogram
aios.llm.requests                       counter   {provider, model, alias}
aios.llm.tokens                         counter   {kind: input|output|cache_read|cache_write}
aios.llm.cost_usd                       counter   {provider, model}
aios.llm.cache_hit_ratio                gauge
aios.gate.evaluations                   counter   {gate_id, status}
aios.sandbox.executions                 counter   {outcome}
aios.outbox.relay_lag_seconds           gauge
aios.authz.denials                      counter
```

### 3.2 Sampling

**Workflow traces are never sampled** — they are the replay substrate (NFR-091). Sampling applies only to high-volume infrastructure spans.

---

## 4. Instrumentation Requirements

All major components must instrument themselves consistently:

- Use the platform’s standard correlation identifiers
- Emit structured logs (not just free text)
- Emit key metrics (latency, counts, costs, success/failure)
- Participate in distributed tracing
- Avoid logging secrets or sensitive personal data

---

## 5. Correlation

The following identifiers must be propagated and recorded:

- Trace ID
- Workflow ID
- Step ID
- Agent ID
- Experiment ID (when applicable)
- Capability Pack ID + version
- Principal / User ID (when applicable)

---

## 6. Relationship with Other Components

- **Workflow Engine** is responsible for creating and propagating Trace ID / Workflow ID.
- **LLM Gateway** emits rich cost and latency metrics.
- **Quality Gate Engine** emits gate results.
- **Evaluation Engine** consumes metrics and outcomes for scoring and comparison.
- **Dashboard** is the primary visualisation surface.
- **Notification Service** may be triggered by alerting rules.
- **Security Manager** emits audit events that flow into the same observability backbone.

---

## 7. Alerting & Dashboards

The stack must support:

- Alerting on error rates, latency, cost anomalies, failed quality gates, and security events
- Standard dashboards defined in the Observability Design document (Platform Overview, Workflow Operations, LLM Usage & Cost, Quality Gates, etc.)

---

## 8. Current Status

This document defines the Observability Stack architecture.

Concrete technology choices (logging backend, metrics system, tracing system), retention policies, and deployment patterns will be decided during implementation.

---

## 9. Final Authority

Order of precedence:

1. Project Constitution  
2. System Architecture  
3. Kernel Architecture  
4. Logging, Audit & Observability Design  
5. Observability Stack  
6. Source Code
