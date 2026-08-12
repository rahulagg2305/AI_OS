# Kernel Architecture – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Kernel Architecture  
**Version:** 2.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## Purpose

This document defines the official architecture of the AI_OS Platform Kernel.

The Kernel is the domain-agnostic runtime core of AI_OS. It provides the foundational services required by all Capability Packs, Platform Services and external interfaces while remaining completely independent of business and customer-specific logic.

This document is subordinate to:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Capability Pack Contract  

---

## Implementation Status (2026-07-28)

**Built:** 10 of the 17 components below exist as real code under `kernel/src/ai_os_kernel/`, all at partial scope: Workflow Engine (22 modules), LLM Gateway (11 modules + `adapters/`), Prompt Engine, Context Manager, Configuration Manager, Manifest Loader, Capability Manager, Security Manager, Observability, Health. The composition root — the real, explicit, no-DI-container startup order required by [ADR-0010](../../18_decision_log/adr/ADR-0010-composition-and-dependency-injection.md) — is `kernel/src/ai_os_kernel/bootstrap.py`. Three additional real packages exist that are cross-cutting rather than components in the list below: `secrets_manager/` (ADR-0024, `env` backend only), `sandbox/` (ADR-0016, `LocalSubprocessSandbox` + `DockerSandbox`), and `git_integration/` (`P03-S01-M24-T01` — commit/branch/push, genuinely audited; a real Platform Service per `../services/git_integration.md`, deliberately packaged as a Kernel subpackage rather than a separate `platform_services/` tier, a disclosed scope decision). `persistence/` (13 modules) holds the shared schema and engine that several components' tables live in. `routes/` and `entrypoints/` hold the `api` process role's real HTTP surface; the `worker` role's entrypoint exists but there is no multi-instance worker loop yet.

**Not built:** 7 of the 17 components are empty stubs — a docstring-only `__init__.py` and zero other `.py` files: Knowledge Manager, Memory Manager, Retrieval, Evaluation Engine, Quality Gate Engine, Traceability Engine, Event Bus. The build order below is therefore accurate as a *plan*, not as a description: Stage A's Configuration Manager / Observability / Health & Lifecycle / Manifest Loader all exist at partial scope, but Stage B's Quality Gate Engine and Event Bus do not exist at all, and Stage D's two components do not exist at all. The Platform SDK boundary described under "Capability Pack Interaction" is **specified but not built** — `platform_sdk/` currently contains exactly one real file (`platform_sdk/schemas/manifest.schema.json`); there is no `ai-os-sdk` package, so packs presently import Kernel internals directly as a documented, dated, temporary compromise (see `../capability_framework/capability_pack_contract.md`). Of the five horizontal-scaling mechanisms listed under "Scalability", (1) Postgres-resident state, (2) `SKIP LOCKED` leasing, (3) idempotency-keyed steps and (5) per-step stateless sandboxing are real; (4) the transactional outbox is a table (`platform.event_outbox`) with no relay or publisher.

Authoritative, always-current status: `../../19_roadmap/feature_inventory.md` (per-module completion table). Detailed build history: `../../19_roadmap/history/INDEX.md`.

---

## Design Goals

The Kernel shall be:

- Domain-agnostic
- Highly modular
- Interface-driven
- LLM-agnostic
- Secure
- Observable
- Configurable
- Extensible through Capability Packs
- Independently testable

The Kernel shall never contain domain-specific business logic.

---

## High-Level Kernel Structure

```text
Platform Kernel
│
├── Workflow Engine          sole orchestrator; owns state, scheduling, retries
├── LLM Gateway              sole provider egress (generation + embeddings)
├── Prompt Engine
├── Context Manager
├── Knowledge Manager   ┐
├── Memory Manager      ├─ retrieval sources, consumed via the Context Manager
├── Retrieval           ┘
├── Evaluation Engine
├── Configuration Manager
├── Manifest Loader          discover · validate · register
├── Capability Manager       lifecycle · activation · health
├── Security Manager
├── Quality Gate Engine
├── Traceability Engine
├── Event Bus
├── Observability & Audit
└── Health & Lifecycle
```

**Build order (v2.0).** The Kernel is not built all at once. Stage A implements Configuration Manager, Observability, Health & Lifecycle, and Manifest Loader. Stage B adds Workflow Engine (sequential), LLM Gateway, Prompt Engine, Context Manager, Capability Manager, Quality Gate Engine, and Event Bus. Stage C adds Security Manager enforcement and sandboxed Tool invocation. Stage D adds Evaluation Engine and Traceability Engine. Building the full component set before the first workflow runs would be over-investment; the order above is the sequence in `../../19_roadmap/implementation_roadmap.md`.

---

## Core Components

### Workflow Engine
Owns workflow execution, agent coordination, retries, failure handling, approvals, scheduling and Quality Gate enforcement.

### LLM Gateway
Single entry point for all LLM communication.

Responsibilities:
- Provider abstraction
- Routing
- Retries
- Fallbacks
- Rate limiting
- Token accounting
- Cost tracking

Direct provider access is prohibited.

### Prompt Engine
- Versioned prompts
- Prompt templates
- Rendering
- Validation

### Context Manager
Builds execution context using:
- Knowledge Manager
- Memory Manager
- AI Context Packs
- Runtime state

### Knowledge Manager
Provides indexed access to:
- Documentation
- ADRs
- Specifications
- Architecture
- Patterns

### Memory Manager
Manages:
- Conversation memory
- Workflow memory
- Engineering memory
- Long-term reusable assets

### Evaluation Engine
Measures:
- Quality
- Performance
- Cost
- Accuracy
- Multi-LLM benchmarking
- Experiment comparison

### Configuration Manager
Central source for:
- Runtime configuration
- Feature flags
- Environment overrides

### Manifest Loader
Discovers, validates and registers Capability Packs through manifests. Validation is strict and fail-closed; a pack that fails leaves no partial registration. Referred to as "Plugin Manager" in earlier drafts — that name is withdrawn, and the responsibilities are split between this component and the Capability Manager.

### Capability Manager
Controls installation, activation, deactivation, upgrades and health of Capability Packs.

### Security Manager
Provides:
- Authentication
- Authorization
- Secret integration
- Policy enforcement

### Quality Gate Engine
Executes mandatory quality gates before and after critical workflow stages.

### Traceability Engine
Maintains Requirement → Architecture → Implementation → Test traceability and supports impact analysis.

### Event Bus
Provides asynchronous communication between Kernel components and Capability Packs.

### Observability & Audit
Structured logging, metrics, and distributed tracing via OpenTelemetry, plus a separate append-only, hash-chained audit log. Telemetry and audit are deliberately different paths: telemetry may be sampled and buffered, audit may not ([ADR-0017](../../18_decision_log/adr/ADR-0017-observability-stack.md)).

### Health & Lifecycle
Reports runtime health, startup validation, readiness and lifecycle status.

---

## Key Design Rules

- Kernel remains domain-agnostic.
- Domain logic exists only inside Capability Packs.
- All LLM calls pass through the LLM Gateway.
- Components communicate through interfaces or the Event Bus.
- Configuration replaces hardcoding.
- Everything important is observable, traceable and auditable.
- Human governance rules are enforced.

---

## Capability Pack Interaction

Capability Packs interact with the Kernel **only through the Platform SDK**, which is the single boundary. A pack receives a `PackContext` carrying only the capabilities its manifest declared and was granted; there is no `kernel` attribute and no escape hatch, so an undeclared capability is not merely forbidden — it is absent from the object the pack holds ([ADR-0010](../../18_decision_log/adr/ADR-0010-composition-and-dependency-injection.md)).

The complete pack-facing surface is specified in `../platform/platform_sdk.md`. Direct Kernel access, direct database access, and provider SDK imports are prohibited and are checked by the pack contract suite.

---

## Cross-Cutting Services

Applied across every Kernel component:

- Configuration
- Security
- Logging
- Monitoring
- Audit
- Metrics
- Traceability
- Error Handling

---

## Extensibility

New functionality is introduced by installing new Capability Packs.  
The Kernel should rarely require modification.

---

## Scalability

The Kernel runs as two process roles — `api` and `worker` — from one image, both built by the same composition root. Horizontal scaling works by a specific mechanism rather than by assertion ([ADR-0020](../../18_decision_log/adr/ADR-0020-deployment-topology-and-scaling.md)):

1. Workflow state lives in PostgreSQL, never in worker memory, so any worker can run any workflow.
2. Workers claim work with `SELECT … FOR UPDATE SKIP LOCKED`; leases expire, so a crashed worker's work is reclaimed.
3. Steps are idempotency-keyed, so a reclaimed step re-executes safely.
4. Cross-process events go through a transactional outbox.
5. Sandboxed execution is per-step and stateless, so it follows the worker.

The scaling ceiling is shared PostgreSQL. Concurrency targets and the trigger conditions for revisiting the topology are in `../../02_requirements/non_functional/nfr.md`.

---

## Current Status

This document establishes the Kernel architecture. Sixteen of the seventeen components have a detailed design document in this directory; **Retrieval is the exception** — its design lives in `../services/search_vector_search.md` (with [ADR-0013](../../18_decision_log/adr/ADR-0013-search-and-vector-store.md)) rather than under `kernel/`, because search is specified once for both Knowledge and Memory. Every technology choice is recorded in an ADR (see `../../18_decision_log/README.md`). The composition and lifecycle mechanism is specified in [ADR-0010](../../18_decision_log/adr/ADR-0010-composition-and-dependency-injection.md); component startup order is explicit in `kernel/src/ai_os_kernel/bootstrap.py` (this document previously gave the path as `kernel/bootstrap.py`, which does not exist — the package root is `kernel/src/ai_os_kernel/`).

---

## Final Authority

Order of precedence:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Capability Pack Contract  
5. Kernel Architecture  
6. Subsystem Design Documents  
7. Source Code

---

## Related Documents

**Governing decisions (ADRs):**
- [ADR-0001 — Modular Capability Pack Architecture](../../18_decision_log/adr/ADR-0001-modular-capability-pack-architecture.md)
- [ADR-0004 — Interface-Driven and Configuration over Code](../../18_decision_log/adr/ADR-0004-interface-driven-and-configuration-over-code.md)
- [ADR-0010 — Composition and Dependency Injection](../../18_decision_log/adr/ADR-0010-composition-and-dependency-injection.md)
- [ADR-0017 — Observability Stack](../../18_decision_log/adr/ADR-0017-observability-stack.md)
- [ADR-0020 — Deployment Topology and Scaling](../../18_decision_log/adr/ADR-0020-deployment-topology-and-scaling.md)
- Full index: `../../18_decision_log/README.md`

**Superior documents:**
- `../../00_constitution/project_constitution.md`
- `../../00_constitution/ai_governance_framework.md`
- `../platform/system_architecture.md`
- `../capability_framework/capability_pack_contract.md`

**Peer / dependent documents:**
- `../platform/platform_sdk.md` — the only pack-facing surface
- `../platform/technology_stack.md`
- Component designs in this directory: `workflow_engine.md`, `llm_gateway.md`, `prompt_engine.md`, `context_manager.md`, `knowledge_manager.md`, `memory_manager.md`, `evaluation_engine.md`, `configuration_manager.md`, `manifest_loader.md`, `capability_manager.md`, `security_manager.md`, `quality_gate_engine.md`, `traceability_engine.md`, `event_bus.md`, `observability.md`, `health_lifecycle.md`
- `../services/search_vector_search.md` — the Retrieval component's design document
- `../../08_database/data_model.md` — all Kernel-owned tables
- `../../02_requirements/non_functional/nfr.md` — concurrency and scaling targets
- `../../20_glossary/glossary.md`

**Status and history:**
- `../../19_roadmap/feature_inventory.md`, `../../19_roadmap/implementation_roadmap.md`, `../../19_roadmap/history/INDEX.md`
