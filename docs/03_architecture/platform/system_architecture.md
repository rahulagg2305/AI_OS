# System Architecture – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** System Architecture  
**Version:** 2.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## Purpose

This document defines the official high-level system architecture of AI_OS.

It describes the architectural style, major platform components, responsibilities, interactions, boundaries, design principles, and system-wide constraints.

This document serves as the architectural blueprint for the entire platform and shall be consulted before designing or implementing any subsystem.

This document operates under the authority of the Project Constitution and the AI Governance Framework.

---

## Architectural Vision

AI_OS is a modular, extensible, LLM-agnostic AI Operating System designed to orchestrate specialized AI agents that collaboratively perform autonomous software engineering.

The architecture is designed to support:

- Autonomous software engineering
- Existing project intelligence
- Multi-agent collaboration
- Multi-LLM orchestration
- Enterprise governance
- Knowledge preservation
- Long-term maintainability
- Future domain expansion through Capability Packs

---

## Architectural Style

AI_OS follows a hybrid architecture composed of:

- Modular Platform (starting as a modular monolith with clear boundaries)
- Capability Pack Architecture
- Plugin Architecture
- Hexagonal Architecture (Ports & Adapters)
- Interface-Driven Design
- Event-Driven Architecture (where beneficial)
- LLM-Agnostic Architecture

---

## High-Level Architecture

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                               AI_OS Platform                                │
├─────────────────────────────────────────────────────────────────────────────┤
│ User Interfaces                                                             │
│ Dashboard │ CLI │ Voice (Jarvis) │ External integrations                    │
├─────────────────────────────────────────────────────────────────────────────┤
│ API Layer                (transport only — no business logic)               │
│ REST /api/v1 │ WebSocket /api/v1/stream │ AuthN/AuthZ │ Rate limiting       │
├─────────────────────────────────────────────────────────────────────────────┤
│ Platform Kernel                                                             │
│ Workflow Engine (sole orchestrator; owns state, scheduling, retries)        │
│ LLM Gateway │ Prompt Engine │ Context Manager                               │
│ Knowledge Manager │ Memory Manager │ Retrieval                              │
│ Evaluation Engine │ Configuration Manager                                   │
│ Manifest Loader │ Capability Manager │ Security Manager                     │
│ Quality Gate Engine │ Traceability Engine                                   │
│ Event Bus │ Observability & Audit │ Health & Lifecycle                      │
├─────────────────────────────────────────────────────────────────────────────┤
│ Platform Services                                                           │
│ Storage │ Search & Vector Search │ Document Processing │ Git Integration    │
│ Notification │ Caching │ Speech Gateway │ Workspace                         │
├─────────────────────────────────────────────────────────────────────────────┤
│ Platform SDK             (the only pack-facing surface)                      │
├─────────────────────────────────────────────────────────────────────────────┤
│ Capability Packs                                                            │
│ Software Engineering │ Project Intelligence │ Voice (Jarvis) │ Benchmarking │
│ Future domain packs                                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│ External Systems                                                            │
│ LLM Providers │ Speech Providers │ Git Hosts │ PostgreSQL │ Redis │ CI/CD   │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Note on this diagram (v2.0).** Version 1.0 showed a separate "Platform Orchestration" layer containing an Agent Orchestrator, Task Planner, and Execution Coordinator, and listed Workflow Engine and Event Bus outside the Kernel. That contradicted the Kernel Architecture. The reconciliation:

- **Workflow Engine, Event Bus, and Scheduler are Kernel components.** There is exactly one orchestrator; scheduling is a Workflow Engine responsibility, not a peer component.
- **Agent Orchestrator, Task Planner, and Execution Coordinator are removed.** They do not exist. Dynamic decomposition is achieved by a planning *agent* emitting a plan artifact that a declared `foreach` step consumes ([ADR-0021](../../18_decision_log/adr/ADR-0021-declarative-workflows-no-dynamic-task-planner.md)).
- **"Plugin Manager" is two components** with distinct responsibilities: the **Manifest Loader** (discover, validate, register) and the **Capability Manager** (lifecycle, activation, health).
- **MCP is removed from the API layer.** It is an integration surface, not core architecture; if delivered it will be a Capability Pack consuming the public API, with its own ADR ([ADR-0014](../../18_decision_log/adr/ADR-0014-api-style-and-realtime-transport.md)).
- **The Platform SDK is shown explicitly**, because it is the boundary that makes the pack model enforceable.

---

## Platform Layers

### User Interface Layer
Provides all user-facing interaction mechanisms (Dashboard, CLI, REST, Voice/Jarvis, future UIs).

### API Layer
Standardized entry points into the platform: REST for operations, WebSocket for live streams, authentication, authorization, and rate limiting. Business logic shall never reside here. Specified in `../../07_api/api_architecture.md`.

### Platform Kernel
Core runtime, strictly domain-agnostic. Contains the **Workflow Engine** (the sole orchestrator, owning workflow state, step scheduling, retries, gate invocation, and approval handling), the LLM Gateway, Prompt Engine, Context Manager, Knowledge and Memory managers, Evaluation Engine, Configuration Manager, Manifest Loader, Capability Manager, Security Manager, Quality Gate Engine, Traceability Engine, Event Bus, Observability & Audit, and Health & Lifecycle.

### Platform SDK
The only surface Capability Packs may depend on. Defines every interface, boundary model, and error contract crossing the pack boundary, and the contract test suite that proves a pack complies. Specified in `platform_sdk.md`.

### Platform Services
Reusable shared services: Storage, Search & Vector Search, Document Processing, Git Integration, Notification, Caching, Speech Gateway, and Workspace management.

### Capability Packs
Domain-specific functionality. All business/domain logic lives here. Independently installable, versionable, and removable. A pack interacts with the platform **only** through the Platform SDK, and may not depend on the Kernel, on platform services directly, or on another pack.

---

## Key Architectural Rules

- The Platform Kernel shall remain domain-agnostic.
- All domain-specific functionality shall live inside Capability Packs.
- All model communication — including embeddings — shall pass through the LLM Gateway.
- All speech provider communication shall pass through the Speech Gateway.
- Capability Packs shall interact with the platform only through the Platform SDK.
- The Workflow Engine is the sole orchestrator; agents never invoke agents.
- Components shall communicate through interfaces or events.
- Business logic shall never reside in the API Layer.
- Untrusted code shall execute only inside a Tier 1 sandbox.
- Workflow control flow shall be declared, never planned at runtime.

---

## LLM Abstraction Path

```text
Agent (in a Capability Pack)
   ├─→ Prompt Engine        renders a versioned prompt, returns it to the caller
   └─→ LLM Gateway          receives the rendered prompt + tools + schema
          └─→ Provider Adapter → LLM Provider
```

The Prompt Engine **returns** a rendered prompt to the caller; it is not a proxy in the call path. The caller then invokes the LLM Gateway. This is stated explicitly because v1.0 of this document implied a pass-through chain.

Capability Packs shall never communicate directly with a provider, and may not import a provider SDK. Enforced by an import-boundary check in CI.

---

## Knowledge Architecture

Project knowledge shall remain independent of conversation history and individual AI models.

Primary knowledge sources include Documentation, Specifications, Architecture Documents, Decision Records, AI Context Packs, Knowledge Repository, and Traceability Repository.

---

## Workflow Lifecycle

```text
Request
  → Workflow definition loaded and validated (references resolved at pack load)
  → Instance created, state persisted
  → For each declared step:
        Context assembled → Agent or Tool invoked → Output validated → State appended
  → Quality Gates evaluated at declared points
  → Human Approval at declared points (workflow persists and waits)
  → Completion → Knowledge/Memory update → Metrics and run manifest recorded
```

Note that there is no "planning" or "agent assignment" phase: the step sequence and the agent for each step are **declared** in the workflow definition and validated at pack load. Where work must be decomposed at runtime, a planning agent emits a plan artifact that a declared `foreach` step consumes ([ADR-0021](../../18_decision_log/adr/ADR-0021-declarative-workflows-no-dynamic-task-planner.md)).

---

## Architectural Constraints

- Domain-independent Platform Kernel
- Independent and isolated Capability Packs
- Replaceable LLM providers
- Interface-driven communication
- Configuration-driven behavior
- High cohesion / Low coupling
- Full observability and traceability

---

## Deployment and Scale

AI_OS is a **modular monolith deployed as two process roles** — `api` and `worker` — from one image, scaling horizontally over shared PostgreSQL and Redis. Workflow state lives in the database, not in worker memory, and workers lease work with `SELECT … FOR UPDATE SKIP LOCKED`; that is the mechanism by which horizontal scaling works. Criteria for extracting a component into a separate service are stated in [ADR-0020](../../18_decision_log/adr/ADR-0020-deployment-topology-and-scaling.md); absent one of those criteria, extraction is not undertaken.

---

## Architecture Governance

All architectural changes shall:

- Comply with the Project Constitution and AI Governance Framework
- Preserve modularity, traceability, and LLM agnosticism
- Be documented before implementation
- Be approved through the Architecture Decision Record (ADR) process

---

## Final Authority

Order of precedence:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Architecture Decision Records  
5. Subsystem Architecture Documents  
6. Technical Specifications  
7. Source Code