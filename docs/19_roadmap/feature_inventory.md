# AI_OS Feature, Module & Phase Completion Tracker

**Status:** Active — Living Document
**Created:** 2026-07-28
**Last Updated:** 2026-07-29 (module 27: **Steps 1, 2, 2a, 3, 4, 5, 6, and 6a of 18 complete** — real Kernel-side adapters (`kernel/src/ai_os_kernel/sdk_adapters/`) now genuinely implement `LLMGateway`/`PromptRegistry`/`ToolInvoker` over `DispatchingLLMGateway`/`PromptEngine`/`LocalSubprocessSandbox`, proven against real underlying objects, resolving the timeout-precedence nuance step 6 left open; 34% → 40%. Prior entry: **Steps 1, 2, 2a, 3, 4, 5, and 6 of 18 complete** — the `ToolInvoker` Protocol is real, proven against the actually-executed sandbox, which found and fixed a too-strict validator and a real circular import; 30% → 34%. Prior entry: **Steps 1, 2, 2a, 3, 4, and 5 of 18 complete** **Steps 1, 2, 2a, 3, and 4 of 18 complete** — the `LLMGateway` Protocol is real and the actual `DispatchingLLMGateway` provably satisfies it unmodified; 22% → 26%. Prior entry: **Steps 1, 2, 2a, and 3 of 18 complete** — the first two Protocols exist and every real agent/tool provably satisfies them unmodified; 18% → 22%. Prior entry: **Steps 1, 2, and 2a of 18 complete** — the five Protocol/reality reconciliation decisions are recorded in `platform_sdk.md`; Step 3's scope shrank as a result. 15% → 18%. Prior entry: the build sequence was revised from 15 to 18 steps after an independent architecture review — see `../03_architecture/platform/platform_sdk_v1_scope.md` §6a — and Steps 1–2 are complete (packaging scaffold + error taxonomy + shared boundary models), 10% → 15%. See `../03_architecture/platform/platform_sdk_v1_scope.md`. Prior entries: the build was scoped as a 15-step plan, awaiting approval; before that, the product-owner decision recorded module 27 as a **hard gate** blocking any new agent (module 29) or new pack (modules 32–34) until it is built. See `history/026_platform_sdk_gate_and_audit_completion.md`.)

> **This document is now cross-referenced from every architecture document.** As of the 2026-07-28 consolidation audit, 82 documents carry an `## Implementation Status` section pointing here as the authority on per-module completion. When you change a module's percentage here, that document's own section may also need updating — `docs/process/standing_rules.md` covers the discipline.

---

## 1. Purpose & How to Use

This is the master tracker for **every** documented v1 feature, module, and remaining phase of AI_OS, cross-checked against real source inspection (not assumption) as of 2026-07-28. It complements, and is more granular than, `implementation_status.md` (which stays short and links here).

- **Section 2** — the full documented feature/capability inventory, grouped by area, extracted from every architecture document.
- **Section 3** — the module list: every Kernel component, Platform Service, Capability Pack, and cross-cutting system, as a distinct trackable unit.
- **Section 4** — concrete, checkable implementation phases, reconciled with `implementation_roadmap.md`'s Stage A–H sequence.
- **Section 5** — the completion table: the living tracker. **Update this table's percentages, status, and "what remains" at the end of every future step** (standing rule — see `CLAUDE.md` / `docs/process/standing_rules.md`).
- **Section 6** — overall weighted progress and the single biggest remaining phase.

**Honesty rule for this document:** a percentage reflects real source inspection (code read, `find`/`grep` run, tests counted), never a guess from a document's intent. An empty package directory is 0%, not "in progress." An unstarted item says so plainly.

---

## 2. Full Feature / Capability Inventory (Documented v1 Scope)

Grouped by area. Each group cites its governing document(s). This is what the *documentation* specifies — Section 5 tracks what actually exists.

### 2.1 Platform Architecture & Cross-Cutting Rules
*(`system_architecture.md`, `technology_stack.md`, `kernel_architecture.md`)*
- Modular-monolith Kernel with 17 domain-agnostic components; two deployable process roles (`api`, `worker`) from one image
- Hexagonal/interface-driven design; Capability Packs as the only extension mechanism; Platform SDK as the only pack-facing surface
- 8 mandatory architectural rules (domain logic only in packs; all model/speech traffic through their Gateways; Workflow Engine is sole orchestrator; no runtime agent-to-agent orchestration; declared-not-planned control flow; Tier 1 sandbox for all untrusted execution; etc.)
- Full, ADR-backed technology stack: Python 3.12/`asyncio`/Pydantic v2/`uv`; PostgreSQL 16 + SQLAlchemy Core + Alembic + `asyncpg`; `pgvector` + FTS + RRF hybrid search; Redis 7; FastAPI + OpenAPI 3.1 + WebSocket; React 19 dashboard stack; OpenTelemetry + `structlog`; OIDC + Vault; Docker/Podman/gVisor sandboxing; 25 Accepted ADRs governing all of the above

### 2.2 Workflow Engine (`workflow_engine.md`, `workflow_architecture.md`, `workflow_patterns.md`, `state_management.md`, `error_handling_retry.md`)
- Definition loading/validation against the Workflow Contract; instance create/run/pause/resume/complete
- Event-sourced state (append-only log + snapshot, one transaction) across 9 canonical states (`created`…`cancelled`)
- Lease-based work distribution (`SELECT…FOR UPDATE SKIP LOCKED`, heartbeat, expiry reclaim)
- 7 supported step types: Agent, Tool, Decision, Parallel, Sub-workflow, Quality Gate, Human Approval
- Step Contract: 5 invocation fields (`agentId`, `toolId`, `promptId`, `promptVersion`, `modelAlias`)
- Idempotency keys per `(workflow_id, step_name, attempt)`; mandatory per-instance workspace isolation
- 8 orchestration patterns: Sequential, Parallel (with mandatory `all`/`any`/`collect` join policy), Request–Review–Revise Loop (bounded iterations + cost ceiling), Human-in-the-Loop Gate, Quality Gate Pipeline, Fan-out/Fan-in, Compensation/Saga, Experiment
- Gate Coordinator (interprets Quality Gate Engine results, decides consequence); Human Approval Manager (durable pause/resume); Failure & Retry Manager; Scheduler (delayed/scheduled starts, concurrency limits)
- Unified 6-category error taxonomy (`transient`/`permanent`/`quality`/`infrastructure`/`budget`/`security`) with a single retry-ownership boundary (Gateway owns provider retry, Workflow Engine owns step retry)
- Full execution replay support

### 2.3 LLM Gateway (`llm_gateway.md`)
- Sole provider-access point (generation, tool calls, structured output, streaming, embeddings, token counting) — provider SDKs importable only inside adapters
- Neutral `LLMRequest`/`LLMResponse` contract; alias-only routing (never literal model IDs); per-alias fallback chains
- Capability Negotiator matrix (13 fields) + 4 degradation rules (use/emulate/fail/never-emulate)
- Retry & Fallback Manager: chain traversal, circuit breaker, exponential backoff+jitter, unified error taxonomy
- Policy & Budget Enforcer: 5 documented checks (per-step, per-workflow, per-experiment cost ceilings; allowed-model policy; per-principal rate limit; context-window-fit pre-check)
- Prompt Cache Planner (ADR-0025 breakpoint placement); Rate Limiter; Response Normalizer; Token & Cost Accountant (sole source of spend truth)
- Provider-adapter conformance suite; adding a provider requires zero pack/agent changes (NFR-101)
- Every call emits a span + `evaluation.llm_calls` row; never logs API keys, prompt bodies with customer code, or raw provider responses

### 2.4 Prompt Engine (`prompt_engine.md`)
- Prompt as versioned, immutable artifact (SemVer); Markdown files owned by packs, rendered via restricted (non-executing) templating
- Prompt Registry, Version Manager, Template Renderer, Variable Validator, Prompt Resolver (role/alias-based), Composition Engine (inheritance)
- `cache_boundary_index` marking the stable/volatile split for LLM Gateway prompt caching
- Every render traceable: prompt ID + version + variables + linked LLM call

### 2.5 Context Manager (`context_manager.md`)
- Assembles context from 6 documented sources: Workflow State, Knowledge Manager, Memory Manager, AI Context Packs, Runtime Configuration, User Inputs
- Mandatory `trust: trusted|untrusted` tagging on every `ContextItem`; untrusted content structurally delimited, never grants authority
- Size & Token Budget Enforcer (hard limit, explicit `items_excluded_count`, no silent truncation)
- Context Filter/Ranker as a first-class component; Context Audit Logger (persisted, replayable assembly record)
- Deterministic assembly (same request/conditions → same context) for experiment reproducibility

### 2.6 Knowledge Manager & Memory Manager (`knowledge_manager.md`, `memory_manager.md`, `knowledge_base_structure.md`)
- Knowledge: platform knowledge (Constitution, architecture, ADRs, standards) + project knowledge (requirements, specs, generated docs); ingestion, indexing (structured + vector), query engine, versioning, provenance tracking
- Directory taxonomy: `architecture_memory/`, `best_practices/`, `design_patterns/`, `anti_patterns/`, `engineering_memory/`, `lessons_learned/`, `reusable_patterns/`, `reusable_workflows/`, `known_limitations/`, `onboarding/`
- Memory: workflow (short-lived), engineering (long-lived), reusable assets — explicit promotion/demotion logic, decay/archival; memory never overrides Knowledge; writes mediated only through `MemoryService.write()`

### 2.7 Retrieval / Search & Vector Search (`search_vector_search.md`)
- Keyword (Postgres FTS/GIN), vector (pgvector HNSW/cosine), and hybrid (Reciprocal Rank Fusion) search
- Every vector records `embedding_model_id`/version/dimensions; `index_generation` pinnable for experiment reproducibility
- Metadata filters and access control applied as SQL predicates (never post-filter, never leaks through ranking)
- Documented scale trigger to a dedicated vector store (Qdrant) behind the same `VectorIndex` Protocol

### 2.8 Evaluation Engine & Benchmarking (`evaluation_engine.md`, `benchmarking/overview.md`)
- Metrics: cost, performance, quality (gate pass/fail, coverage, static/security findings), process (retries, human interventions), and pack-contributed domain metrics
- Run manifest recording (full reproducibility bundle, ADR-0022); comparison statistics with **mean and variance across ≥3 replicates**, never a single-run point value; cache-served runs excluded and flagged
- Clear responsibility split: Benchmarking Pack defines/submits experiments; Workflow Engine executes; Evaluation Engine collects/stores/computes statistics
- Reproducibility rules: pinned prompts/tools/config, sampling params excluded from experiment variables, response caching disabled for experiments

### 2.9 Configuration Manager (`configuration_manager.md`, `configuration_management.md`)
- 7-layer precedence: built-in defaults → pack defaults → platform config → environment config → runtime overrides (audited) → experiment overrides (isolated, highest precedence) → secret resolution
- Feature flags; typed/validated config (`pydantic-settings`); resolved config recorded in every run manifest
- Minimal bootstrap env vars only (`AIOS_ENV`, `AIOS_ROLE`, `AIOS_DATABASE_URL`, `AIOS_REDIS_URL`, `AIOS_SECRET_BACKEND`, `OTEL_EXPORTER_OTLP_ENDPOINT`) — everything else is a config file value

### 2.10 Manifest Loader & Manifest Schema (`manifest_loader.md`, `manifest_schema.md`)
- Dual discovery: entry-point (`ai_os.capability_packs`, production) + filesystem scan (development), validated identically
- 21 validation rules (11 schema-level, 10 semantic — kernel/SDK version compatibility, global ID uniqueness, reference resolution, monotonic-permission-subset checks, circular-dependency detection, declared-vs-actual component match)
- Fail-closed: no valid manifest → never loaded, never partially registered
- Explicitly deferred for v1: signed manifests, marketplace metadata, multi-language entrypoints

### 2.11 Capability Manager (`capability_manager.md`, `capability_pack_contract.md`)
- 8-state canonical lifecycle: `discovered → validated → installed → configured → activated → {deactivated|failed} → uninstalled`, every transition audited with actor+reason
- Activation of a behavior-affecting pack requires human approval (ADR-0007)
- Health monitoring, upgrade path, clean deactivation/removal

### 2.12 Security Manager & Threat Model (`security_manager.md`, `security_architecture.md`, `authentication_authorization.md`, `secrets_management.md`)
- 3 principal types (`user`/`service_account`/`agent`); 5 roles (`viewer`/`operator`/`approver`-per-class/`maintainer`/`admin`)
- **Monotonic narrowing**: `principal ∩ workflow ∩ agent ∩ tool = effective permissions` — no runtime elevation, structural containment of prompt injection
- Closed permission vocabulary published in the SDK; unknown permission fails manifest validation
- 12 named threats (T1–T12) each with a documented primary control (sandboxing, provenance tagging, secret isolation, manifest validation, permission narrowing, supply-chain scanning, egress allowlisting, hash-chained audit, resource ceilings, attributable approvals, Git safety rails, workspace isolation)
- Secrets: `secret://<provider>/<name>[#version]` reference scheme; 4 backends (env/file/vault/cloud); never enters Tier 1 sandbox; never sent to a model (prompt-assembly rejection check)

### 2.13 Quality Gate Engine & Quality Gates Framework (`quality_gate_engine.md`, `quality_gates_framework.md`)
- 8 standard gate categories: Build, Static Analysis, Testing, Security, Architecture & Design, Documentation, Performance, Release Readiness
- Blocking vs. Warning severity; LLM-as-judge gates may only ever be Warning severity (never the sole blocking gate)
- Gates execute inside Tier 1 sandbox when running builds/tests/analysis over generated code
- Clean separation from Workflow Engine: this engine only executes/evaluates; the Workflow Engine's Gate Coordinator decides consequence

### 2.14 Traceability Engine (`traceability_engine.md`, `traceability_model.md`)
- 10 core artifact types (Requirement, Architecture Element/ADR, Design, Module, Source File, Test Case, Gate Result, Workflow/Experiment Run, Documentation, Release)
- 8 core relationships; 7 key queries (impact analysis, coverage gaps, ADR-affected components, etc.)
- Links created explicitly only, never inferred; every link carries provenance

### 2.15 Event Bus (`event_bus.md`)
- `EventBus` SDK Protocol, swappable transport: in-process `asyncio` pub/sub (default) → Redis Streams (on documented scale trigger)
- Transactional outbox for durable/cross-process events, written in the same transaction as the state change; at-least-once delivery, idempotent-by-`event_id` consumers required

### 2.16 Health & Lifecycle, Observability & Audit (`health_lifecycle.md`, `observability.md`, `observability_stack.md`)
- Kernel lifecycle states: Starting/Ready/Degraded/Stopping/Stopped/Failed; liveness/readiness endpoints; pack health aggregation
- Two separate pipelines: telemetry (OTel traces/metrics/logs → Collector → Prometheus/Tempo/Loki/Grafana, sampled/buffered) vs. audit (`governance.audit_log`, PostgreSQL, SHA-256 hash-chained, never sampled, daily verification job)
- Standard metric naming (`aios.<subsystem>.<metric>`); 7 named dashboards; required correlation IDs on every record (Trace/Workflow/Step/Agent/Experiment/Pack/Principal)

### 2.17 Sandbox / Tool Execution (`security_architecture.md` §5, ADR-0016)
- Two trust tiers only: Tier 1 (ephemeral OCI container — no network, read-only root, non-root, caps dropped, no host mounts, no secrets, real resource limits) and Tier 2 (trusted, in-process, canonical-path-allowlisted)
- Dependency installation is a separate, explicitly-declared step through an egress proxy allowlist — never ambient network access
- `SandboxRuntime`/`SandboxExecutor` Protocol; gVisor as a hardened, non-default runtime option

### 2.18 Platform Services (`storage_service.md`, `document_processing.md`, `notification_service.md`, `caching_strategy.md`, `git_integration.md`)
- **Storage Service**: content-addressed (`sha256:<hex>`) artifact store, local-FS (dev) / S3-compatible (prod) backends
- **Document Processing**: format detection, parser adapters (Markdown/plain text/PDF/DOCX/code-aware), chunking, provenance-preserving normalization
- **Notification Service**: Dashboard/Voice/Email/Webhook channels, preference management, delivery tracking
- **Caching (Redis)**: config/secret/document/retrieval caching with correctness-preserving key construction; response caching off by default, unconditionally disabled for experiments
- **Git Integration Service**: controlled read/write Git operations; credentials never leave this service; 4 categorically prohibited operations (force-push/delete/history-rewrite/direct-push to protected branches) — absent from the tool surface entirely, not merely permission-gated

### 2.19 Platform SDK (`platform_sdk.md`)
- 15 Protocol interfaces (`LLMGateway`, `PromptRegistry`, `ContextService`, `RetrievalService`, `MemoryService`, `ToolInvoker`, `EventBus`, `ConfigService`, `SecretResolver`, `StorageService`, `WorkspaceService`, `Telemetry`, `TraceabilityService`, `QualityGateRegistry`, `SpeechGateway`)
- Boundary models (`ArtifactRef`, `TraceContext`, `SecurityContext`, `AgentRequest`/`AgentResult`, `StepBudget`, `ToolRequest`/`ToolResult`); `AiOsError` exception hierarchy
- `CapabilityPack` entry-point contract; `pack_contract_suite` (9 automated compliance checks); SemVer compatibility/deprecation rules

### 2.20 Agents & Workflows (Cross-Pack) (`agent_architecture.md`, `agent_communication.md`, `agent_catalog.md`)
- 16 documented v1 agents across packs (15 Software Engineering + 1 Project Intelligence)
- Mandatory agent contract (id/name/purpose/inputs/outputs/permissions/supportedWorkflows/entrypoint/version); 2 lifecycles (Registration, Invocation — 7 steps)
- 5 allowed / 5 forbidden communication patterns; agents never communicate directly, coordination only via Workflow Engine

### 2.21 Capability Packs
- **Software Engineering** (`software_engineering/*.md`): 15 agents, 6 named workflows (Full Product Creation, Feature Addition, Bug Fix/Maintenance, Refactoring, Code Review & Quality Improvement, Release), tool categories (source code, build/dependency, test, static analysis, git, documentation, container/deployment) each trust-tiered, 7 gate categories
- **Project Intelligence** (`project_intelligence/*.md`): 1 agent (`existing-project-analyzer`), 5 named workflows (Existing System Analysis, Architecture Recovery, Legacy Documentation Generation, Modernization Opportunity Assessment, Safe Enhancement)
- **Voice (Jarvis)** (`voice_jarvis/overview.md`, `14_voice_jarvis/*.md`): wake-word engine, STT/TTS via platform Speech Gateway, Intent Engine (6+ initial intent categories), Voice Session Manager, Response Generator, multi-modal hand-off with Dashboard/API/CLI
- **Benchmarking** (`benchmarking/overview.md`): experiment definition/pinning, replicate management (≥3), cost ceiling enforcement, comparison report generation

### 2.22 APIs & Interfaces (`api_architecture.md`, `cli_design.md`, `dashboard_architecture.md`, `information_architecture.md`, `monitoring_experiment_views.md`)
- REST `/api/v1` + WebSocket `/api/v1/stream`; OpenAPI 3.1 generated + CI-snapshot-tested; RFC 9457 error shape; cursor pagination; `Idempotency-Key`; per-principal rate limiting
- 9 resource endpoint groups (~45 documented endpoints): Workflows, Approvals, Experiments, Quality/Cost/Agents, Packs/Config, Traceability/Observability, Health, plus the WebSocket stream itself
- CLI (`aios`): 8 command groups (`auth`, `workflow`, `approve`, `experiment`, `pack`, `config`, `health`, `logs`), human/JSON output, 7 exit codes
- Dashboard: 10 navigation sections (Overview, Workflows, Approvals, Experiments, Quality, Cost, Agents, System Health, Logs & Traces, Settings), real-time monitoring, side-by-side experiment comparison views

### 2.23 Deployment & Operations (`deployment_architecture.md`, `observability_stack.md`)
- Two process roles (`api`, `worker`) from one digest-pinned, non-root, multi-stage image
- Docker Compose (local, 3 profiles) → Kubernetes + Helm (prod): Deployment/Service/Ingress/HPA/NetworkPolicy/PodDisruptionBudget, `runtimeClassName: gvisor` option
- Migration-as-Job (never on app startup); staged release process with human approval gate; PITR backup + quarterly rehearsed restore drills including audit-chain verification

---

## 3. Module List

Every Kernel component, Platform Service, Capability Pack, and cross-cutting system, tracked as a distinct unit in Section 5.

| # | Module | Category |
|---|---|---|
| 1 | Configuration Manager | Kernel |
| 2 | Manifest Loader (+ Manifest Schema enforcement) | Kernel |
| 3 | Health & Lifecycle | Kernel |
| 4 | Observability & Audit | Kernel |
| 5 | Workflow Engine | Kernel |
| 6 | LLM Gateway | Kernel |
| 7 | Prompt Engine | Kernel |
| 8 | Context Manager | Kernel |
| 9 | Knowledge Manager | Kernel |
| 10 | Memory Manager | Kernel |
| 11 | Retrieval / Search & Vector Search | Kernel |
| 12 | Evaluation Engine | Kernel |
| 13 | Capability Manager | Kernel |
| 14 | Security Manager | Kernel |
| 15 | Quality Gate Engine | Kernel |
| 16 | Traceability Engine | Kernel |
| 17 | Event Bus | Kernel |
| 18 | Tool Invoker (SDK interface) | Kernel/SDK |
| 19 | Secrets Manager | Cross-cutting |
| 20 | Sandbox / SandboxExecutor (Tier 1/2) | Cross-cutting |
| 21 | Storage Service | Platform Service |
| 22 | Notification Service | Platform Service |
| 23 | Caching (Redis) | Platform Service |
| 24 | Git Integration Service | Platform Service |
| 25 | Speech Gateway | Platform Service |
| 26 | Document Processing | Platform Service |
| 27 | Platform SDK (`ai-os-sdk` package) | SDK |
| 28 | Manifest Schema (JSON Schema itself) | SDK |
| 29 | Software Engineering Pack — Agents | Capability Pack |
| 30 | Software Engineering Pack — Workflows | Capability Pack |
| 31 | Software Engineering Pack — Tools & Quality Gates | Capability Pack |
| 32 | Project Intelligence Pack | Capability Pack |
| 33 | Voice (Jarvis) Pack | Capability Pack |
| 34 | Benchmarking Pack | Capability Pack |
| 35 | ~~Analytics Pack~~ — **removed 2026-07-28**, see note | Capability Pack |
| 36 | API (HTTP surface) | Interface |
| 37 | WebSocket stream (`/api/v1/stream`) | Interface |
| 38 | CLI (`aios`) | Interface |
| 39 | Dashboard | Interface |
| 40 | Deployment & Infrastructure (Compose/K8s/Helm/Terraform) | Ops |
| 41 | Threat Controls (T1–T12, cross-cutting) | Cross-cutting |
| 42 | Testing Infrastructure (unit/integration/contract/security/perf/regression) | Cross-cutting |
| 43 | CI Pipeline | Cross-cutting |
| 44 | Platform-wide `AiOsError` exception hierarchy | SDK |

**Note on #35:** `capability_packs/analytics/` was investigated (2026-07-28) — confirmed empty, never git-tracked, and not referenced in any architecture document; `functional_requirements.md` §10 names "analytics" only as an example of an explicitly out-of-v1-scope future domain pack, alongside IoT and finance. Confirmed stale scaffolding, approved for removal, and deleted (see `history/023_docker_sandbox_default_wiring.md`). Row kept, struck through, rather than silently renumbering every row below it — if a real Analytics pack is ever built, it re-enters this table as a new row with its own real percentage, not a resurrection of this one.

---

## 4. Implementation Phases

Reconciled with `implementation_roadmap.md`'s Stage A–H sequence, made concrete and checkable. The multi-agent pipeline work (built under an explicit 2026-07-27 product-owner reprioritization, ahead of and narrower than full Stage C) is tracked as its own phase, **B.5**, between B and C.

| Phase | Name | Roadmap Stage | Status |
|---|---|---|---|
| A | Platform Skeleton | Stage A | Process-complete, not exit-criteria-complete |
| B | Minimum Viable Kernel | Stage B | In progress |
| B.5 | Multi-Agent Delivery Pipeline Proof | *(ad-hoc, pre-Stage-C)* | Complete |
| C | First Real Capability Pack (full scope) | Stage C | Started (via B.5), majority remaining |
| D | Evaluation & Multi-LLM Experimentation | Stage D | Not started |
| E | Project Intelligence | Stage E | Not started |
| F | Dashboard, Voice, Notifications | Stage F | Not started |
| G | Hardening & Production Readiness | Stage G | Not started |
| H | Expansion | Stage H | Not started |

**Checkable exit criteria per phase** (condensed from `implementation_roadmap.md` §3, cross-referenced to Section 5's modules):

- **A**: process starts, ready ≤15s, discovers/validates a pack, rejects invalid manifest, emits correlated telemetry, CI green. → *Mostly met; OTLP export/Compose observability profile remain (module 4).*
- **B**: pack loads; sequential workflow completes; agent calls Gateway + a tool; **killing a worker mid-step loses no state and another worker resumes it**; tokens/cost recorded; full correlated trace. → *Core loop met (modules 5–8 partial); Tool Invoker/Event Bus/Quality Gate Engine/Platform SDK (modules 18, 17, 15, 27) block full exit.*
- **B.5**: one real, declared workflow chains 4 real agents end-to-end through a proven Tier 1 sandbox. → **Met**, narrower than B's own documented deliverable list (no Tool Invoker/Event Bus/Quality Gate Engine used).
- **C**: a specification produces built+tested code; a blocking gate halts progression; an approval pauses/resumes and never on timeout; a Tier 1 step demonstrably has no network/secrets/host access; audit chain verifies. → *Sandbox proof met (module 20); gates/approvals/audit chain (modules 13/15/4) and 12 of 16 agents (module 29) remain.*
- **D**: same workflow runs against 2 models with ≥3 replicates; report shows mean+variance, excludes cached runs, links run manifests; a completed workflow replays; provider substitution needs zero pack/agent changes. → *Second provider adapter already exists (ahead of schedule); everything else (module 12, 34) not started.*
- **E**: a real repository is analysed/documented within limits; every derived context item is tagged `untrusted`; ingestion respects resource limits. → *Not started (module 32).*
- **F**: an approval is decided from the Dashboard and the workflow resumes; live updates over WebSocket; a `viewer` sees no mutating controls anywhere; a voice status query works end to end. → *Not started (modules 36–39).*
- **G**: NFR targets met/re-baselined; a restore rehearsal succeeds incl. audit-chain verification and workflow resumption; every T1–T12 control has a passing test. → *Not started (modules 40–41).*
- **H**: remaining 8 agents with specs written first; remaining workflows; richer Project Intelligence; CLI polish; additional packs as needed. → *Not started.*

---

## 5. Completion Table (Living Tracker)

**Status categories:** `not started` / `schema-only` / `minimal slice` / `functionally complete` / `production-hardened`.
Percentages are against each module's own **documented** v1 scope (Section 2), based on direct source inspection on 2026-07-28 (file counts, `grep`/`find` against `kernel/src/`, `capability_packs/`, `tests/`, `platform_sdk/`, `infra/`, plus the full history in `docs/19_roadmap/history/`).

| # | Module | Phase | % | Status | What Remains |
|---|---|---|---|---|---|
| 1 | Configuration Manager | B | 35% | minimal slice | 4 of 7 precedence layers unbuilt (pack defaults, runtime overrides, experiment overrides, secret-layer integration); no feature flags; no change-audit trail. |
| 2 | Manifest Loader (+ Schema) | A | 55% | minimal slice | Entry-point discovery not implemented (filesystem scan only); several of the 10 semantic rules (workflow-definition existence/circularity, SDK version range) unenforced since no SDK exists yet to check against. |
| 3 | Health & Lifecycle | A | 40% | minimal slice | Only the `Ready` path is real; no graceful-shutdown coordinator; pack health not aggregated into overall readiness. |
| 4 | Observability & Audit | A | 20% | minimal slice | Console exporters only — no OTLP/Collector, no Prometheus/Tempo/Loki/Grafana, no Compose observability profile; `governance.audit_log` is schema-only (no writer, no hash chain, no verification job); 1 of ~15 documented metrics exists. |
| 5 | Workflow Engine | B | 55% | minimal slice | 5 of 7 step types (Decision/Parallel/Sub-workflow/Quality Gate/Human Approval) execute as literal no-ops; no Gate Coordinator consequence logic (Quality Gate Engine is 0%); no Human Approval Manager; no Scheduler/concurrency limits. Core (definition load → instance → lease → agent/tool step → completion) is solid. |
| 6 | LLM Gateway | B | 50% | minimal slice | No `stream()`, no `embed()`, no `count_tokens()` (provider-endpoint token counting), no Rate Limiter; tool-calling loop and structured-output emulation defined in models but not exercised end-to-end; 2 of 5 budget checks real (alias, workflow). |
| 7 | Prompt Engine | B | 40% | minimal slice | No Prompt Resolver (role/alias-based), no composition/inheritance, no `cache_boundary_index` implementation confirmed, no dedicated Observability writer. |
| 8 | Context Manager | B | 30% | minimal slice | 1 of 6 documented sources built (Workflow State, incl. step-output); no Knowledge/Memory/AI-Context-Pack/Runtime-Config resolvers; no Filter/Ranker; no persisted Context Audit Logger. |
| 9 | Knowledge Manager | B | 10% | minimal slice | Kernel package is empty; a real writer + keyword-search reader exist one layer down in `persistence/`, but no indexing/query-engine/provenance component, and no Context Manager resolver reads from it yet. |
| 10 | Memory Manager | B | 0% | not started | Package empty; nothing at any layer — no writer, no store, no promotion logic. |
| 11 | Retrieval / Search & Vector Search | B | 20% | minimal slice | Keyword search real; `pgvector` schema exists but no embedding writer, no vector search, no hybrid RRF, no dedicated Retrieval Service, no scale-trigger logic. |
| 12 | Evaluation Engine | D | 10% | schema-only | All 6 catalog + 6 evaluation tables exist; zero collector/aggregator/comparison-statistics/reporting code. |
| 13 | Capability Manager | B | 35% | minimal slice | Lifecycle register/activate/deactivate real; no automated discovery (manual `register()` only), no upgrade path, no health-monitoring integration, no permissions enforcement beyond activation gating. |
| 14 | Security Manager | C | 20% | minimal slice | Pre-shared-secret JWT, not OIDC; 4 of the published permission vocabulary modeled; monotonic-narrowing chain not enforced end-to-end (Capability Manager doesn't check agent/tool permission subsets); no role administration; no `audit_log` writer. |
| 15 | Quality Gate Engine | B | 0% | not started | Package empty; 0 of the "two Kernel gates" Stage B calls for exist. |
| 16 | Traceability Engine | D | 0% | not started | Package empty. |
| 17 | Event Bus | B | 5% | schema-only | `platform.event_outbox` table exists; no in-process `asyncio` bus, no relay, no `EventBus` Protocol implementation. |
| 18 | Tool Invoker (SDK interface) | B | 15% | minimal slice | No `ToolInvoker` Protocol/package exists anywhere. A narrower, workflow-engine-internal substitute (`ToolStepExecutor` + `SandboxedCommandTool`) covers a slice of the same need but isn't the documented, pack-facing interface. |
| 19 | Secrets Manager | A | 20% | minimal slice | `env` backend only; no file/Vault/cloud backends, no Access Broker, no TTL cache/rotation, no prompt-assembly secret-leak scan. |
| 20 | Sandbox / SandboxExecutor | C | 85% | functionally complete | **Updated 2026-07-28**: the real, Docker-gated end-to-end pipeline test ran for real against a live daemon and passed — network isolation and filesystem containment genuinely held for code the pipeline itself generated and ran, not just an isolated guarantee check (see `history/024`). Two real bugs found and fixed along the way (unrelated to the sandbox mechanism itself — a `python_command`-consistency bug in `pipeline.py`'s own composition, and a test with a hardcoded `sys.executable`). Remaining: digest-pinning the default image, a gVisor option, and the egress-proxy dependency-install step ADR-0016 documents. |
| 21 | Storage Service | B | 0% | not started | No code; no content-addressed artifact store beyond ad-hoc sandbox temp directories. |
| 22 | Notification Service | F | 0% | not started | No code, no channels. |
| 23 | Caching (Redis) | B | 0% | not started | No Redis client usage anywhere in the Kernel despite Redis being provisioned in Compose. |
| 24 | Git Integration Service | C | 0% | not started | No code; the Build Agent writes files via the sandbox but performs no Git operations. |
| 25 | Speech Gateway | F | 0% | not started | No code. |
| 26 | Document Processing | E | 0% | not started | No parser adapters; the Knowledge writer accepts only already-chunked input — no chunking pipeline exists. |
| 27 | Platform SDK (`ai-os-sdk` package) | B | 40% | taxonomy + models + all 5 shapes decided + all Protocols now genuinely implemented by real Kernel adapters | **🛑 HARD GATE (2026-07-28) still active — only `platform_sdk_v1_scope.md` step 15 lifts it.** 18-step sequence (revised from 15 after an architecture review found 3 blocking gaps — §6a). **Steps 1, 2, 2a, 3, 4, 5, 6, 6a done:** real installable distribution with `py.typed`; `ai_os_sdk.errors` + `ai_os_sdk.models` (error taxonomy, `ArtifactRef`, canonical `TraceContext`, `SecurityContext`, `StepBudget`, the `LLMGateway` model set, `RenderedPrompt`, and `ToolDescriptor`/`ToolStatus`/`ToolResult`); `ai_os_sdk.contracts` holds `Agent`/`Tool`/`TrustTier`, `LLMGateway`, `PromptRegistry`, and `ToolInvoker`. **Structural compatibility proven against all 5 real pack agents, both real tools, the real `DispatchingLLMGateway`; `PromptRegistry` and `ToolInvoker` proven by conversion/execution instead of `isinstance` (from-scratch shapes).** **Step 6a is the first to touch real Kernel code**: `kernel/src/ai_os_kernel/sdk_adapters/` now holds real, tested `LLMGatewayAdapter`/`PromptRegistryAdapter`/`ToolInvokerAdapter`, genuinely implementing all three Protocols over `DispatchingLLMGateway`/`PromptEngine`/`LocalSubprocessSandbox` — not merely `isinstance`-true. Resolves the timeout-precedence nuance step 6 left open. **Still nothing wires these adapters into `bootstrap.py`/`EntrypointLoader`/any pack** — that's step 6b, the actual unlock for migration. Zero pack source modified (§6c–§6g). |
| 28 | Manifest Schema (JSON Schema) | A | 95% | functionally complete | The schema itself is real, versioned, and actively enforced. Only documented v1 exclusions (signed manifests, marketplace metadata) remain, by design. |
| 29 | SE Pack — Agents | C | 30% | minimal slice | 5 of 16 documented agents real (`requirements-analyst`, `architecture`, `build`, `qa-test`, `documentation`) — `requirements-analyst` proven independently, not yet chained into `se.delivery_pipeline`. **Frozen at 5 by the module-27 hard gate** — no 6th agent (`technical-planner`/`code-reviewer`/etc.) may be added until the Platform SDK exists. The 5 built agents are grandfathered and unaffected. |
| 30 | SE Pack — Workflows | C | 15% | minimal slice | 1 real workflow (`se.delivery_pipeline`) — a narrower, different shape than either of Stage C's own named targets (`se.product_creation`, `se.implement_task`), both still 0%. 5 other documented workflows (Feature Addition, Bug Fix, Refactoring, Code Review, Release) not started. |
| 31 | SE Pack — Tools & Quality Gates | C | 10% | minimal slice | One internal, non-manifest-declared tool (`SandboxedCommandTool`) real; no manifest-declared Tool; 0 of 7 documented gate categories implemented (blocked on Quality Gate Engine itself being 0%). |
| 32 | Project Intelligence Pack | E | 0% | not started | Directory empty; docs exist, no code. **Blocked from starting by the module-27 hard gate** — this would be a *new* Capability Pack, explicitly prohibited until the Platform SDK exists. |
| 33 | Voice (Jarvis) Pack | F | 0% | not started | Directory empty; docs exist, no code. **Blocked from starting by the module-27 hard gate**, same reasoning as module 32. |
| 34 | Benchmarking Pack | D | 0% | not started | Directory empty; docs exist, no code. **Blocked from starting by the module-27 hard gate**, same reasoning as module 32. |
| 35 | ~~Analytics Pack~~ | — | N/A | **removed** | Investigated and deleted 2026-07-28 — confirmed stale, undocumented, never git-tracked. Excluded from Section 6's weighted total. See Section 3 note and `history/023`. |
| 36 | API (HTTP surface) | B/F | 15% | minimal slice | 9 real authenticated routes vs. ~45 documented across 9 resource groups; no OpenAPI generation/snapshot test, no RFC 9457 error shape (FastAPI default in use), no rate limiting, no `Idempotency-Key` handling. |
| 37 | WebSocket stream | F | 0% | not started | No `/api/v1/stream` route exists. |
| 38 | CLI (`aios`) | F | 0% | not started | No CLI package, no entry-point script declared anywhere. |
| 39 | Dashboard | F | 0% | not started | `dashboard/` directory is empty — no frontend project scaffolded at all. |
| 40 | Deployment & Infrastructure | G | 10% | minimal slice | Docker Compose (Postgres+Redis dev only) exists; no `Dockerfile`, no `api`/`worker` images, no Kubernetes manifests, no Helm chart, no Terraform — `infra/kubernetes/` and `infra/terraform/` are empty. |
| 41 | Threat Controls (T1–T12) | C/G | 35% | minimal slice | **Updated 2026-07-28**: T1 (generated-code containment) now has a real, live-verified proof — network isolation and filesystem containment held for code the pipeline itself generated and ran, not just an isolated check. Sandboxing (T1/T12 — workspace isolation still not yet *mandatory*) and supply-chain scanning (T6, via CI) are the strongest; audit-chain (T8), Git safety (T11, no Git service exists), provider-egress controls (T7), and approval-fraud prevention (T10, no approvals writer) are all effectively unstarted. |
| 42 | Testing Infrastructure | A–G | 40% | minimal slice | **Updated 2026-07-28:** unit + integration are strong — **849 passing, 11 skipped, 0 failing** combined. `tests/security/`, `tests/performance/`, `tests/regression/`, `tests/benchmarks/` have **zero tracked files** (absent from a fresh clone); no `tests/contract/` exists at all. `tests/security/` being empty means **no T1–T12 threat control has a dedicated regression test**, contrary to a Stage C deliverable. A known flake family is now documented in `../10_testing/test_strategy.md`: real-local-HTTP-server tests occasionally fail under full-suite load and pass in isolation (3 instances observed). |
| 43 | CI Pipeline | A | 50% | minimal slice | Lint/types/unit/integration real and green; contract/security/build(image)/frontend stages are correctly gated off (no-op) pending their prerequisites, per design — never actually executed. |
| 44 | Platform-wide `AiOsError` hierarchy | B | 0% | not started | `LLMProviderError` etc. exist locally in the LLM Gateway but do not inherit from any shared hierarchy, because none exists yet anywhere in the codebase. |

---

## 6. Overall Progress Summary

**43 modules tracked** (44 rows retained for traceability; #35, Analytics Pack, was investigated and removed 2026-07-28 — excluded from this total, see its own row). Weighted by each module's relative share of documented v1 scope (core orchestration/security/interface modules weighted higher than peripheral ones):

**Overall weighted completion: ≈ 21%** (module 27, Platform SDK, moved 34% → 40% — real Kernel-side adapters now genuinely implement all three from-scratch/narrowed Protocols against real underlying objects (`DispatchingLLMGateway`, `PromptEngine`, `LocalSubprocessSandbox`), resolving the timeout-precedence nuance left open by the prior step; still nothing wires these adapters into a pack, so the rounded overall figure is unchanged. Prior movement: 30% → 34% — a fifth Protocol (`ToolInvoker`) is real, proven against actually-executed sandbox behavior which caught 2 real bugs pre-emptively; still nothing consumes the package, so the rounded overall figure is unchanged. Prior movement: 26% → 30% — a fourth Protocol (`PromptRegistry`) is real, proven compatible by lossless conversion rather than isinstance since it's a from-scratch shape; still nothing consumes the package, so the rounded overall figure is unchanged. Prior movement: 22% → 26% — a third Protocol (`LLMGateway`) is real and provably satisfied by the real production gateway; still nothing consumes the package, so the rounded overall figure is unchanged. Prior movement: 18% → 22% — the first two Protocols are real and provably satisfied by every existing agent and tool, which de-risks the migration steps materially; still nothing consumes the package, so the rounded overall figure is unchanged. Prior movement: 15% → 18% — all five interface shapes are now decided against real source, which de-risks every remaining SDK step; still no Protocol code, so the rounded overall figure is unchanged. Prior movement: 10% → 15% — the error taxonomy and shared boundary models are real, though still consumed by nothing; not enough on its own to move the rounded overall figure. See `../03_architecture/platform/platform_sdk_v1_scope.md` steps 1–2. Prior movement: modules 20/29/41 moved up when real Docker verification landed and a fifth Software Engineering agent, Requirements Analyst, was built; see `history/024_docker_verification_and_requirements_analyst.md`).

This is deliberately not a simple average of the percentages above — an unweighted mean would overstate progress, since many 0% rows (Dashboard, CLI, Voice Pack, Notification Service, Speech Gateway) are genuinely large, separate bodies of work, not small missing details.

**Single biggest remaining phase by size: Phase F (Dashboard, Voice, Notifications).** It requires an entire separate frontend application (10 navigation sections, real-time views, experiment comparison UI), a full CLI application (8 command groups), a complete voice pipeline (wake word → STT → intent → TTS), a Notification Service, and the WebSocket transport — none of which shares code with anything built so far, unlike Phase C, D, or G, which all extend real infrastructure already in place (Workflow Engine, LLM Gateway, Sandbox). Phase C is a close second and more immediately actionable, since it already has a real, proven foundation (module 20, 29) to build on.

---

## 7. Maintenance

**Standing rule (recorded 2026-07-28, see `CLAUDE.md` / `docs/process/standing_rules.md`):** update this document's Section 5 percentages, status categories, and "what remains" — and Section 6's overall weighted completion — **at the end of every future implementation step**, as part of the standard report. A module whose real state changed but whose row here wasn't updated in the same step is treated the same as an undocumented decision: a gap to flag and fix, not defer.

When a new module, pack, or phase is approved, add it to Sections 3/4/5 in the same step that begins work on it — don't wait until it's finished to start tracking it.
