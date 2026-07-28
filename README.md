# AI_OS

**AI Operating System for Autonomous Software Engineering**

AI_OS is a modular, LLM-agnostic, production-grade platform designed to autonomously create, analyze, and enhance software systems through multi-agent collaboration.

It is **not** a coding assistant.
It is an AI Operating System that transforms structured specifications into production-ready software while maintaining architecture, governance, observability, traceability, and quality throughout the software lifecycle.

---

## Vision

Build a platform that can:

- Create complete software products from structured specifications
- Analyze, understand, and modernize existing software systems
- Compare multiple LLMs using measurable engineering benchmarks
- Support multiple domains through installable Capability Packs
- Provide a configurable dashboard and voice interface (Jarvis)
- Preserve project knowledge so development can continue across different AI models

---

## Repository Goals

This repository is the **single source of truth** for AI_OS.

Every design decision, requirement, specification, architecture document, implementation, and knowledge artifact must be maintained here.

**Documentation is considered authoritative.**

---

## Core Principles

1. Documentation First
2. Configuration over Code
3. Interface-Driven Design at real seams
4. Capability Pack Architecture
5. LLM Agnosticism
6. Human Governance for Critical Decisions
7. Observability by Default
8. Traceability by Design
9. Reproducibility — pinned conditions, deterministic platform behaviour, recorded non-determinism

---

## Current Status

**Documentation baseline:** Approved
**Architecture decisions:** 25 ADRs Accepted
**Current stage:** **Stage A – Platform Skeleton — implementation in progress**

The technology stack is decided and every choice is backed by an Architecture Decision Record. Implementation follows `docs/19_roadmap/implementation_roadmap.md`.

**Implementation has started.** The repository is a working `uv` workspace with the Kernel installable and its API skeleton running:

```sh
uv sync
uv run uvicorn ai_os_kernel.entrypoints.api:app --reload
```

See `kernel/README.md` for details on what exists so far.

---

## Technology Stack

Full detail: `docs/03_architecture/platform/technology_stack.md`.

- **Python 3.12** · asyncio · `mypy --strict` · Pydantic v2
- **uv** workspace; each Capability Pack is its own distribution
- **PostgreSQL 16** with an append-only event log; **pgvector** for hybrid search
- **Redis 7** for caching and rate limiting
- **FastAPI** REST + WebSocket; OpenAPI 3.1
- **React 19 + TypeScript + Vite** dashboard
- **OpenTelemetry** telemetry; hash-chained audit log
- **Ephemeral OCI container sandboxes** for all generated-code execution
- **GitHub Actions** CI with pytest, testcontainers, ruff, mypy

---

## Architectural Invariants

Enforced by mechanism, not convention:

- All model access goes through the **LLM Gateway**. No pack may import a provider SDK.
- **Agents never communicate directly.** The Workflow Engine is the sole orchestrator and owns all state.
- Packs interact with the platform **only through the Platform SDK**.
- **Untrusted code runs only in a sandbox** with no network, no secrets, and no host access.
- **Authority only narrows** along the invocation chain; no LLM output can grant a permission.
- Blocking Quality Gates cannot be skipped; an approval timeout never implies approval.

---

## Getting Started (For Humans & LLMs)

Before making any change, read in this order:

1. `README.md`
2. `PROJECT_INDEX.md`
3. `docs/00_constitution/` — Constitution and Governance Framework
4. `docs/20_glossary/glossary.md` — the vocabulary is precise
5. `docs/18_decision_log/README.md` — all ADRs
6. `docs/03_architecture/platform/` — system architecture, technology stack, Platform SDK
7. `docs/02_requirements/` — requirements, NFRs, constraints
8. Relevant subsystem documents and AI Context Packs

**Do not rely on previous conversation history.**

Complete index with per-document status: `docs/DOCUMENTATION_INDEX.md`.

---

## AI Development Rules

Every AI model working on this repository must follow these rules:

- Do not invent requirements or architecture
- Documentation is the source of truth
- Record technology and architecture decisions as ADRs **before** implementing them
- Update documentation whenever implementation changes, in the same change
- Maintain traceability between requirements, architecture, modules, and tests
- Keep the platform modular, configurable, and LLM-agnostic
- Follow the coding standards in `docs/21_templates/CODING_STANDARDS_AND_BEST_PRACTICES.md`
- Never weaken a security control or a quality gate to make something pass

---

## Success Criteria

The platform should enable any AI model to:

- Understand the project with minimal onboarding
- Continue development without prior chat history
- Preserve architectural consistency
- Produce production-grade, maintainable software
- Extend the platform without modifying the core architecture
