# PROJECT_INDEX.md

**AI_OS Project Index**
**Version:** 2.0
**Status:** Approved
**Current Stage:** Stage A – Platform Skeleton

---

## Purpose

This document is the **primary entry point** for both humans and AI models.

Every new developer or AI model must start here before working on the project. Its purpose is to explain what AI_OS is, show the current state, direct readers to the correct documentation, and let any model continue development without prior chat history.

---

## What is AI_OS?

AI_OS (AI Operating System) is a modular, LLM-agnostic, production-grade platform for autonomous software engineering through multiple specialized agents.

Its primary objectives are:

- Create complete production-grade software products from structured specifications
- Analyze, understand, and enhance existing or legacy software systems
- Benchmark multiple LLMs using measurable engineering metrics
- Support future domains through installable Capability Packs
- Provide governance, observability, traceability, quality control, and a configurable voice interface (Jarvis)

AI_OS is **not** a coding assistant. It is an extensible AI platform that orchestrates specialized agents while maintaining architectural consistency and governance.

---

## Current Status

**Documentation baseline:** Approved (`docs/19_roadmap/documentation_freeze.md`)
**Architecture decisions:** 25 ADRs Accepted (`docs/18_decision_log/README.md`)
**Current stage:** **Stage A – Platform Skeleton**
**Implementation:** beginning

The technology stack is decided and recorded. Implementation follows the lettered stages in `docs/19_roadmap/implementation_roadmap.md`.

> **Note on phase numbering.** Earlier versions of this document listed "Phases 0–7" alongside a different "Phases 0–6" scheme in the Documentation Index. Both are retired. There is now one sequence: **Stages A–H**.

---

## Technology Stack (summary)

Full detail and rationale: `docs/03_architecture/platform/technology_stack.md`.

| Layer | Choice |
|---|---|
| Language / runtime | **Python 3.12**, asyncio, `mypy --strict`, Pydantic v2 |
| Packaging | **uv** workspace; each pack is its own distribution |
| Composition | Explicit composition root; **no DI container** |
| Persistence | **PostgreSQL 16** — append-only event log + materialised snapshot |
| Search | **pgvector** + Postgres FTS, hybrid RRF ranking |
| Cache / rate limiting | **Redis 7** |
| Event bus | In-process asyncio + transactional outbox (Redis Streams at a stated trigger) |
| API | **FastAPI** REST `/api/v1` + WebSocket; OpenAPI 3.1; RFC 9457 errors |
| Dashboard | **React 19 + TypeScript + Vite** |
| Model access | **LLM Gateway only** — alias-based routing, all providers behind adapters |
| Sandboxing | **Ephemeral OCI containers**, no network by default, no secrets |
| Observability | **OpenTelemetry** → OTLP; hash-chained Postgres audit log |
| Testing / CI | pytest + testcontainers + ruff + mypy; **GitHub Actions** |
| Deployment | Docker Compose (single node), Kubernetes + Helm (production) |

---

## Mandatory Reading Order

1. `README.md`
2. `PROJECT_INDEX.md` (this file)
3. `docs/00_constitution/project_constitution.md`
4. `docs/00_constitution/ai_governance_framework.md`
5. **`docs/20_glossary/glossary.md`** — the vocabulary is precise; several terms are easy to conflate
6. **`docs/18_decision_log/README.md`** — all 25 ADRs and the open decision points
7. `docs/03_architecture/platform/system_architecture.md` and `technology_stack.md`
8. **`docs/03_architecture/platform/platform_sdk.md`** — the boundary everything respects
9. `docs/02_requirements/` — functional requirements, NFRs, constraints
10. The subsystem documents relevant to your task
11. `docs/19_roadmap/implementation_roadmap.md` — what is being built now

**Do not rely on previous conversation history.**

Full index with per-document status: `docs/DOCUMENTATION_INDEX.md`.

---

## Repository Structure

| Folder | Purpose |
|---|---|
| `docs/` | Architecture, requirements, standards, ADRs — the source of truth |
| `platform_sdk/` | The SDK: contracts, models, schemas, testing suite (`ai-os-sdk`) |
| `kernel/` | Platform Kernel implementation (`ai-os-kernel`) |
| `platform_services/` | Shared platform services (`ai-os-services`) |
| `capability_packs/` | Installable Capability Packs, one distribution each |
| `dashboard/` | Mission Control dashboard (TypeScript/React) |
| `knowledge/` | Long-term engineering knowledge, patterns, and memory |
| `ai_context/` | AI Context Packs for rapid model onboarding |
| `traceability/` | Requirement → architecture → module → test mappings |
| `specs/` | Functional and technical specifications for generated products |
| `manifests/` | Machine-readable definitions |
| `config/` | Platform configuration |
| `governance/` | Governance and policy assets |
| `projects/` | Generated customer projects |
| `experiments/` | LLM benchmarking and evaluation artifacts |
| `tests/` | Automated tests (unit, contract, integration, workflow, security, performance) |
| `infra/` | Docker, Compose, Kubernetes, Helm, environment configuration |
| `scripts/` | Automation scripts |
| `tools/` | Internal development tools, including the CLI |
| `assets/` | Images, icons, fonts |
| `workspace/` | Temporary development workspace (prototypes are exempt from documentation-first) |

---

## Primary Use Cases

1. **Product Creation** – Generate production-ready software from structured Markdown specifications.
2. **Existing Project Intelligence** – Understand, document, analyze, and modernize existing systems.
3. **Multi-LLM Benchmarking** – Execute identical workflows across models and compare quality, cost, speed, and process metrics with reported variance.
4. **Future Expansion** – Support additional domains through Capability Packs.

---

## Non-Negotiable Invariants

These are enforced by mechanism, not convention. Each has a governing ADR.

1. The Kernel is domain-agnostic; all domain logic lives in Capability Packs.
2. All model access — including embeddings — goes through the LLM Gateway. No pack may import a provider SDK.
3. Agents never communicate directly. The Workflow Engine is the sole orchestrator and owns all state.
4. Packs interact with the platform only through the Platform SDK.
5. Workflow control flow is declared, never planned at runtime.
6. Untrusted code executes only in a Tier 1 sandbox: no network, no secrets, no host access.
7. Authority only narrows along the invocation chain. No LLM output can grant a permission.
8. Blocking Quality Gates cannot be skipped or self-certified.
9. A Human Approval Point timeout never implies approval.
10. Secrets are referenced, never embedded, and never enter a sandbox, a prompt, or telemetry.
11. Model IDs appear only as aliases outside Gateway configuration.
12. The audit log is append-only and hash-chained.

---

## Development Rules

- Documentation is the single source of truth
- No AI model may invent requirements or architecture
- Architecture and technology decisions are recorded as ADRs before implementation
- Every feature remains modular; interfaces are preferred at real seams
- Configuration is preferred over hardcoding
- Quality gates are mandatory
- Full traceability is maintained from requirement to test
- The platform remains LLM-agnostic

---

## AI Session Checklist

1. Read `README.md` and this file
2. Read the Glossary and the Decision Log index
3. Read the relevant AI Context Pack
4. Read the relevant architecture and requirements documents
5. Check the current stage in the Implementation Roadmap
6. Review traceability for the area you are changing
7. Complete the assigned task
8. Update documentation in the same change
9. Record an ADR if a decision changed

---

## Stage Roadmap

| Stage | Name | Status |
|---|---|---|
| A | Platform Skeleton | **In Progress** |
| B | Minimum Viable Kernel | Planned |
| C | First Capability Pack (thin slice) | Planned |
| D | Evaluation & Multi-LLM Experimentation | Planned |
| E | Project Intelligence | Planned |
| F | Dashboard, Voice, Notifications | Planned |
| G | Hardening & Production Readiness | Planned |
| H | Expansion | Planned |

Detail and exit criteria: `docs/19_roadmap/implementation_roadmap.md`.

---

## Maintenance

Update this document whenever the stage changes, a stage completes, the repository structure changes, a major architectural decision is approved, priorities change, or a new Capability Pack is introduced.
