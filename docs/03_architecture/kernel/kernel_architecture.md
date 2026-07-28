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

This document establishes the Kernel architecture. Every component has a detailed design document in this directory, and every technology choice is recorded in an ADR (see `../../18_decision_log/README.md`). The composition and lifecycle mechanism is specified in [ADR-0010](../../18_decision_log/adr/ADR-0010-composition-and-dependency-injection.md); component startup order is explicit in `kernel/bootstrap.py`.

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
