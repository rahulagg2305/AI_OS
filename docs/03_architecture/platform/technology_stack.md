# Technology Stack – AI_OS

**Project:** AI_OS (AI Operating System)
**Document:** Canonical Technology Stack
**Version:** 1.1
**Status:** Approved
**Last Updated:** 2026-07-28 (added Implementation Status and Related Documents; corrected the LLM-adapter import-boundary path in §6, which pointed at a directory that does not exist)

**Previously:** 2026-07-25 (v1.0)

---

## 1. Purpose

This document is the single canonical list of technologies **decided** for AI_OS. Every entry is backed by an Architecture Decision Record. If another document names a technology that contradicts this table, this document and its ADRs prevail.

No technology may be introduced into the platform without an entry here and an ADR.

A row in this document means "decided and permitted", **not** "in use today". A decided technology that nothing yet imports is still the binding choice for when that subsystem is built — that is the point of deciding it in advance. Implementation Status below distinguishes the two.

This document is subordinate to:

1. Project Constitution
2. AI Governance Framework
3. System Architecture

---

## 1a. Implementation Status (2026-07-28)

**Built — decided technologies genuinely in use in the codebase today:** Python 3.12/3.13, `asyncio`, `mypy --strict` (283 source files, clean), `typing.Protocol`, Pydantic v2, `pydantic-settings`, `uv` workspace + PEP 621, explicit composition root (`kernel/src/ai_os_kernel/bootstrap.py`); PostgreSQL 16, SQLAlchemy Core 2.0, `asyncpg`, Alembic, the append-only-event-log + materialised-snapshot workflow state, `SELECT … FOR UPDATE SKIP LOCKED` leases; FastAPI, Uvicorn; the `anthropic` provider SDK; `structlog`, OpenTelemetry SDK (traces + one metric); `pytest`, `pytest-asyncio`, `pytest-cov`, `testcontainers[postgres]`, `ruff`, `pip-audit`, GitHub Actions; Docker (as the ADR-0016 Tier 1 sandbox runtime, via the `docker` SDK), Docker Compose (Postgres + Redis, development only). `pgvector` is installed and its schema exists.

**Not built — decided but not yet exercised by any code:** Redis (provisioned in `../../../infra/docker-compose.yml`; **no Kernel code imports a Redis client** — §3's cache/rate-limiting row and all of `../services/caching_strategy.md` are unimplemented); the transactional outbox relay and the in-process `asyncio` event bus (§4 — the `platform.event_outbox` table exists, nothing reads or writes it); OpenAPI 3.1 generation/snapshot tests, RFC 9457 `problem+json` errors, the WebSocket `/api/v1/stream` transport, Typer + Rich CLI, and the entire React/TanStack/Tailwind dashboard stack (§5); `pgvector` HNSW vector search, Postgres FTS `tsvector`/GIN, and Reciprocal Rank Fusion (§3 — only a plain keyword-search reader exists, in `persistence/knowledge_keyword_search.py`); S3-compatible blob storage and content-addressed `sha256:` artifact identity (§3 — no Storage Service exists); embeddings and provider token-counting through the Gateway (§6); the Speech Gateway and its `faster-whisper`/Piper/`openWakeWord` adapters (§6); OIDC human authentication (§7 — a pre-shared-secret JWT verifier stands in), Vault/cloud secret backends and age/SOPS files (§7 — only the `env` backend exists), gVisor (§7); OTLP export to a Collector and the Prometheus/Tempo/Loki/Grafana reference backends, and the hash-chained audit log (§8 — console exporters only; `governance.audit_log` is schema-only); `hypothesis`, `gitleaks`, `vitest`, `playwright` (§9 — not in any dependency group); every §10 deployment technology except Compose (**no `Dockerfile` exists**, no Kubernetes manifests, no Helm chart). SQLite as a local dev database (§3) is permitted but unused — Postgres via `testcontainers` is what tests actually run against.

Nothing in §11 (Explicitly Rejected) has been reintroduced.

Authoritative, always-current status: `../../19_roadmap/feature_inventory.md` (per-module completion table) and `../../19_roadmap/implementation_status.md`. Build history: `../../19_roadmap/history/INDEX.md`.

---

## 2. Core Platform

| Concern | Technology | Version | ADR |
|---|---|---|---|
| Language / runtime | Python | 3.12 (min), tested 3.12 & 3.13 | [ADR-0008](../../18_decision_log/adr/ADR-0008-primary-language-and-runtime.md) |
| Concurrency | `asyncio` | stdlib | ADR-0008 |
| Static typing | `mypy --strict` | ≥ 1.11 | ADR-0008 |
| Interfaces | `typing.Protocol` | stdlib | ADR-0008 |
| Data validation | Pydantic | v2 | ADR-0008 |
| Packaging / dependencies | `uv` workspace, PEP 621 | ≥ 0.5 | [ADR-0009](../../18_decision_log/adr/ADR-0009-packaging-and-dependency-management.md) |
| Composition | Explicit composition root (no DI container) | — | [ADR-0010](../../18_decision_log/adr/ADR-0010-composition-and-dependency-injection.md) |
| Settings | `pydantic-settings` + layered YAML | v2 | ADR-0004 |

## 3. Persistence and State

| Concern | Technology | Version | ADR |
|---|---|---|---|
| System of record | PostgreSQL | 16 | [ADR-0011](../../18_decision_log/adr/ADR-0011-persistence-and-workflow-state.md) |
| Database access | SQLAlchemy **Core** (not ORM) | 2.0 | ADR-0011 |
| Async driver | `asyncpg` | ≥ 0.29 | ADR-0011 |
| Migrations | Alembic | ≥ 1.13 | ADR-0011 |
| Workflow state | Append-only event log + materialised snapshot | — | ADR-0011 |
| Work distribution | `SELECT … FOR UPDATE SKIP LOCKED` leases | — | ADR-0011, ADR-0020 |
| Local dev database | SQLite (single-process only, reduced capability) | 3.4x | ADR-0011 |
| Vector index | `pgvector` (HNSW, cosine) | ≥ 0.7 | [ADR-0013](../../18_decision_log/adr/ADR-0013-search-and-vector-store.md) |
| Keyword search | PostgreSQL FTS (`tsvector`, GIN) | — | ADR-0013 |
| Hybrid ranking | Reciprocal Rank Fusion | — | ADR-0013 |
| Cache / rate limiting | Redis | 7 | [ADR-0025](../../18_decision_log/adr/ADR-0025-caching-strategy.md) |
| Blob / artifact storage | Local filesystem (dev), S3-compatible (prod) | — | ADR-0011 |
| Artifact identity | Content-addressed `sha256:<hex>` | — | ADR-0011 |

## 4. Messaging

| Concern | Technology | ADR |
|---|---|---|
| Event bus (default) | In-process `asyncio` pub/sub | [ADR-0012](../../18_decision_log/adr/ADR-0012-event-bus.md) |
| Durable / cross-process events | Transactional outbox table + relay | ADR-0012 |
| Future transport (on stated trigger) | Redis Streams | ADR-0012 |

## 5. API and Interfaces

| Concern | Technology | Version | ADR |
|---|---|---|---|
| HTTP framework | FastAPI | ≥ 0.115 | [ADR-0014](../../18_decision_log/adr/ADR-0014-api-style-and-realtime-transport.md) |
| ASGI server | Uvicorn | ≥ 0.30 | ADR-0014 |
| API contract | OpenAPI 3.1 (generated, snapshot-tested) | — | ADR-0014 |
| Error format | RFC 9457 `application/problem+json` | — | ADR-0014 |
| Real-time | WebSocket `/api/v1/stream` | — | ADR-0014 |
| CLI | Typer + Rich | ≥ 0.12 | ADR-0014 |
| Dashboard | React 19 + TypeScript + Vite | — | [ADR-0018](../../18_decision_log/adr/ADR-0018-dashboard-technology-stack.md) |
| Dashboard state | TanStack Query + TanStack Router | — | ADR-0018 |
| Dashboard UI | Tailwind CSS + shadcn/ui + Recharts | — | ADR-0018 |

## 6. AI Providers

All model access is through the LLM Gateway ([ADR-0002](../../18_decision_log/adr/ADR-0002-llm-gateway-single-entry-point.md)). Provider SDKs may be imported **only** inside `kernel/src/ai_os_kernel/llm_gateway/adapters/` — the real directory on disk; v1.0 of this document cited `kernel/llm_gateway/adapters/`, which does not exist (the Kernel uses a `src/` layout).

| Concern | Technology | ADR |
|---|---|---|
| Provider adapters | Official first-party provider SDKs (e.g. `anthropic`) | ADR-0002 |
| Model selection | Alias → provider/model mapping in configuration | ADR-0002 |
| Token counting | Provider token-counting endpoints via the Gateway. **Never** `tiktoken` or another provider's tokenizer. | ADR-0002 |
| Embeddings | Through the Gateway, same as generation | ADR-0002, ADR-0013 |
| Speech (STT/TTS/wake word) | Speech Gateway; `faster-whisper`, Piper, `openWakeWord` local adapters | [ADR-0019](../../18_decision_log/adr/ADR-0019-speech-gateway.md) |

### 6.1 Default model aliases

Aliases are the only model identifiers permitted in pack, agent, or workflow definitions. The mapping below is the canonical default set and is environment-overridable.

| Alias | Default model | Intended use | In `config/llm.yaml` today? |
|---|---|---|---|
| `reasoning` | `claude-opus-5` | Architecture, planning, complex analysis, code review | Yes |
| `coding-strong` | `claude-opus-5` | Implementation, refactoring, debugging | Yes |
| `coding-balanced` | `claude-sonnet-5` | High-volume implementation where cost matters | Yes |
| `fast-cheap` | `claude-haiku-4-5` | Classification, extraction, short scoped tasks | Yes |
| `frontier` | `claude-fable-5` | Reserved for the hardest long-horizon work; opt-in only | **No — not yet defined** |
| `local-fast` | `llama3.1:8b` | Local-adapter alias; not part of the canonical five | Yes (checked in, routes to `LocalAdapter`) |

The last column is a correction, not a decision change: `../../../config/llm.yaml` currently ships four of the five canonical aliases plus `local-fast`. `frontier` is decided here but not yet configured — nothing routes it, so a definition naming it would fail alias resolution. Adding it is a one-line configuration change, not an architectural one.

`config/llm.yaml` is also, deliberately, a flatter shape than the full Router configuration in `../kernel/llm_gateway.md` §7 (a plain `alias → model id` map plus per-model pricing, with fallback chains present but commented out) — the file's own header records why.

Default request parameters, per `../kernel/llm_gateway.md`: adaptive thinking enabled, `effort` defaulting to `high` (`xhigh` for coding and agentic workflows). **Sampling parameters (`temperature`, `top_p`, `top_k`) are not sent** — current frontier models reject them, and behaviour is steered by prompt and effort instead. Assistant-turn prefill is not used.

## 7. Security

| Concern | Technology | ADR |
|---|---|---|
| Sandbox runtime | OCI containers via Docker or Podman, behind a `SandboxRuntime` Protocol | [ADR-0016](../../18_decision_log/adr/ADR-0016-tool-execution-sandboxing.md) |
| Hardened sandbox option | gVisor (`runsc`) — configuration change, not redesign | ADR-0016 |
| Human authentication | OIDC (bearer tokens) | [ADR-0023](../../18_decision_log/adr/ADR-0023-identity-roles-and-permissions.md) |
| Machine authentication | API keys / client credentials | ADR-0023 |
| Authorization | Role + permission intersection, computed in the Kernel | ADR-0023 |
| Secrets (reference) | `secret://<provider>/<name>[#version]` | [ADR-0024](../../18_decision_log/adr/ADR-0024-secrets-management-backend.md) |
| Secrets backend (prod) | HashiCorp Vault (reference); cloud secret managers via adapters | ADR-0024 |
| Secrets backend (dev) | Environment variables; age/SOPS encrypted file | ADR-0024 |

## 8. Observability

| Concern | Technology | ADR |
|---|---|---|
| Instrumentation | OpenTelemetry SDK (traces, metrics, logs) | [ADR-0017](../../18_decision_log/adr/ADR-0017-observability-stack.md) |
| Export | OTLP → OpenTelemetry Collector | ADR-0017 |
| Structured logging | `structlog` (JSON, trace-context injected) | ADR-0017 |
| Reference backends | Prometheus, Tempo, Loki, Grafana | ADR-0017 |
| Audit log | PostgreSQL append-only with SHA-256 hash chaining | ADR-0017 |

## 9. Quality Toolchain

| Concern | Technology | ADR |
|---|---|---|
| Test runner | `pytest` + `pytest-asyncio` (strict) | [ADR-0015](../../18_decision_log/adr/ADR-0015-testing-and-ci.md) |
| Coverage | `pytest-cov` (branch): 90 % kernel, 85 % SDK/services, 80 % packs | ADR-0015 |
| Real-dependency tests | `testcontainers` (PostgreSQL, Redis) | ADR-0015 |
| Property tests | `hypothesis` | ADR-0015 |
| Lint + format + security rules | `ruff` | ADR-0015 |
| Types | `mypy --strict` | ADR-0015 |
| Dependency vulnerabilities | `pip-audit` against `uv.lock` | ADR-0015 |
| Secret scanning | `gitleaks` | ADR-0015 |
| Frontend tests | `vitest`, `playwright` | ADR-0015, ADR-0018 |
| CI | GitHub Actions | ADR-0015 |

## 10. Deployment

| Concern | Technology | ADR |
|---|---|---|
| Container images | Docker (multi-stage, `uv sync --frozen`) | [ADR-0020](../../18_decision_log/adr/ADR-0020-deployment-topology-and-scaling.md) |
| Local / single node | Docker Compose | ADR-0020 |
| Multi-node production | Kubernetes + Helm | ADR-0020 |
| Process roles | `api` and `worker` from one image | ADR-0020 |
| Autoscaling | HPA on worker lease-queue depth | ADR-0020 |

---

## 11. Explicitly Rejected

Recorded so these are not silently reintroduced. Rationale is in the referenced ADR.

| Technology | ADR |
|---|---|
| LangChain / LlamaIndex or similar orchestration framework | ADR-0002 |
| DI container (`dependency-injector`, `injector`) | ADR-0010 |
| SQLAlchemy ORM (Core is used instead) | ADR-0011 |
| Temporal / durable-execution engine (v1) | ADR-0011 |
| Kafka, RabbitMQ, NATS (v1) | ADR-0012 |
| Dedicated vector database (v1) | ADR-0013 |
| Elasticsearch / OpenSearch | ADR-0013 |
| GraphQL | ADR-0014 |
| gRPC for client-facing APIs | ADR-0014 |
| MCP in the core API layer (deferred to a pack) | ADR-0014 |
| Celery / RQ | ADR-0020 |
| `tiktoken` for token counting | ADR-0002 |
| Direct subprocess execution of generated code | ADR-0016 |
| Secrets injected into sandboxes | ADR-0024 |
| Response caching enabled by default or in experiments | ADR-0025 |

---

## 12. Maintenance

Update this document whenever an ADR adds, replaces, or removes a technology. Every row must cite an ADR; a row without one is a defect.

---

## 13. Final Authority

Order of precedence:

1. Project Constitution
2. AI Governance Framework
3. System Architecture
4. Architecture Decision Records
5. Technology Stack (this document)
6. Source Code

---

## 15. Related Documents

**Governing ADRs** — every row in this document cites one; the complete set referenced above is ADR-0002, ADR-0004, ADR-0008 through ADR-0020, and ADR-0023 through ADR-0025. Full index: `../../18_decision_log/README.md`.

**Architecture**

- `system_architecture.md` — the layers these technologies implement
- `platform_sdk.md` — the pack-facing surface (specification only; no implementing package yet)
- `../kernel/kernel_architecture.md` and the per-component documents alongside it
- `../../08_database/data_model.md` — the PostgreSQL schema behind §3
- `../../11_deployment/deployment_architecture.md` — §10 in operational detail
- `../../16_observability/observability_stack.md` — §8 in detail
- `../../09_security/security_architecture.md` — §7 in detail
- `../../10_testing/test_strategy.md` — §9 in detail
- `../services/caching_strategy.md` — the Redis row in §3, in detail (unimplemented)
- `../services/search_vector_search.md` — the `pgvector`/FTS/RRF rows in §3, in detail (mostly unimplemented)

**Requirements**

- `../../02_requirements/functional/functional_requirements.md` — FR-007 (all model calls via the Gateway, CI-enforced import boundary), FR-016 (layered configuration), FR-021 (Tier 1 sandbox)
- `../../02_requirements/non_functional/nfr.md` — the measurable targets these technologies are chosen to meet

**Standards**

- `../../21_templates/CODING_STANDARDS_AND_BEST_PRACTICES.md` — how these technologies must be used
- `../../process/coding_standards.md` — the load-bearing subset

**Terminology**

- `../../20_glossary/glossary.md`

**Current state of the build**

- `../../19_roadmap/implementation_status.md`, `../../19_roadmap/feature_inventory.md`, `../../19_roadmap/history/INDEX.md`
