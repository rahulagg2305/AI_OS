# Software Engineering Capability Pack – Agents

**Project:** AI_OS (AI Operating System)  
**Capability Pack:** Software Engineering  
**Document:** Agents Catalog & Responsibilities  
**Version:** 1.2  
**Status:** Approved  
**Last Updated:** 2026-07-28 (updated the "Currently Implemented Subset" section: `requirements-analyst` is now real, 5 of 16 — see that section for the full reasoning; no other content changed)

---

## Purpose

This document defines the agents belonging to the Software Engineering Capability Pack and their responsibilities, common operating rules, contracts, governance and workflow participation.

It extends the platform Agent Architecture with software-engineering-specific guidance.

This document is subordinate to:

1. Capability Pack Contract  
2. Agent Architecture & Agent Contract  
3. Agent Catalog  
4. Software Engineering Pack – Overview  

---

## Design Principles

- Single Responsibility
- Workflow-driven orchestration
- No direct agent-to-agent communication
- Stateless where practical
- Tool-first execution
- LLM-agnostic
- Fully observable
- Governed by Quality Gates

---

## Standard Agent Contract

Every agent shall define:

- Agent ID
- Name
- Purpose
- Inputs
- Outputs
- Required Tools
- Supported Workflows
- Permissions
- Quality Gates
- Entrypoint
- Version

---

## Agent Catalog & Responsibilities

**Identifier convention.** Agents are identified as `software-engineering/<slug>`. The `SE-0nn` codes used in v1.0 of this document are **withdrawn** — they conflicted with the kebab-case IDs in the Agent Catalog, and one agent (`existing-project-analyzer`) carried three different identities across three documents. They must not appear in manifests, prompts, telemetry, or traceability links.

| Agent ID | Name | Primary Responsibility |
|---|---|---|
| `software-engineering/requirements-analyst` | Requirements Analyst | Analyze, refine and validate requirements |
| `software-engineering/architecture` | Architecture | Design and validate architecture |
| `software-engineering/technical-planner` | Technical Planning | Create implementation plans (plan artifacts) |
| `software-engineering/backend-developer` | Backend Development | Backend services and APIs |
| `software-engineering/frontend-developer` | Frontend Development | UI and frontend implementation |
| `software-engineering/database` | Database | Data models, schema and migrations |
| `software-engineering/api-designer` | API Design | API contracts and versioning |
| `software-engineering/devops` | DevOps | CI/CD, IaC and deployment |
| `software-engineering/security` | Security | Security reviews and remediation |
| `software-engineering/qa-test` | QA/Test Engineer | Automated testing and validation |
| `software-engineering/code-reviewer` | Code Review | Quality and standards review |
| `software-engineering/documentation` | Documentation | Technical documentation |
| `software-engineering/release` | Release | Versioning and releases |
| `software-engineering/refactoring` | Refactoring | Maintainability improvements |
| `software-engineering/performance` | Performance | Performance optimization |
| `software-engineering/build` | Build | Generate and write exactly one file from a design or instruction (added 2026-07-28 — see "Currently Implemented Subset" below for why this entry exists) |

**Not owned by this pack.** `project-intelligence/existing-project-analyzer` (legacy system analysis) belongs to the Project Intelligence Pack. It participates in this pack's workflows via the Workflow Engine, but it is not a Software Engineering agent and has no `SE-…` identity.

Contract-level specifications (I/O schemas, tools, prompts, permissions, behavioural requirements, tests) are in `../../05_agents/agent_specifications.md`.

---

## Currently Implemented Subset (2026-07-28)

This document describes the full, intended agent catalog for this pack's mature design. As of this date, a much smaller, real slice actually exists in `capability_packs/software-engineering/`, built under a separate product-owner reprioritization toward "the shortest real path to a working multi-agent software-engineering pipeline" (see `docs/19_roadmap/implementation_status.md`'s own header for the full framing). This section exists so a reader of this document is never misled about the gap between the two.

**Real today: 5 of the 16 agents listed above.**

| Agent ID (real) | Entrypoint | Notes |
|---|---|---|
| `software-engineering/requirements-analyst` | `ai_os_pack_software_engineering.agents.requirements_analyst:RequirementsAnalystAgentEntrypoint` | **Added 2026-07-28.** Matches this document's own catalog exactly. Analyzes/refines a raw requirement into a structured requirements analysis only — no architecture design, no code, no validation of acceptance criteria beyond what the model itself states (this catalog's own "validate requirements" is only half-real). Proven independently; not yet wired into `se.delivery_pipeline` (see below). |
| `software-engineering/architecture` | `ai_os_pack_software_engineering.agents.architecture:ArchitectureAgentEntrypoint` | Matches this document's own catalog exactly. Design proposal only — no code generation, no validation of an existing architecture (this catalog's own "Design **and validate** architecture" is only half-real). |
| `software-engineering/build` | `ai_os_pack_software_engineering.agents.build:BuildAgentEntrypoint` | **New catalog entry, added by this reconciliation.** Its real scope — write exactly one generic file from a design/instruction, through the sandbox — does not fit `backend-developer`'s own documented scope ("Backend services and APIs", implying a narrower, stack-specific role this agent does not have) or any other pre-existing entry. Rather than force-fit an ill-matching id or leave an undocumented one in code, this catalog gained a new, honestly-scoped entry instead. |
| `software-engineering/qa-test` | `ai_os_pack_software_engineering.agents.verification:TestAgentEntrypoint` | Matches this document's own catalog exactly (renamed from an earlier, undocumented `test` id during this same reconciliation). Deliberately makes **no LLM call at all** — pass/fail comes only from a real sandboxed exit code, narrower than this catalog's own "Automated testing and validation." |
| `software-engineering/documentation` | `ai_os_pack_software_engineering.agents.documentation:DocumentationAgentEntrypoint` | Matches this document's own catalog exactly. Records one Build+Test result as one Markdown file — narrower than this catalog's own general "Technical documentation." |

**Not yet real: the other 11** (`technical-planner`, `frontend-developer`, `database`, `api-designer`, `devops`, `security`, `code-reviewer`, `release`, `refactoring`, `performance`, and `project-intelligence/existing-project-analyzer`). No code, manifest entry, or prompt exists for any of them in this pack today.

**Four of the five real agents are chained into one real, declared workflow**, `se.delivery_pipeline` — see `workflows.md`'s own "Currently Implemented Subset" section for why this is a distinct real workflow, not a rename of any of that document's own 7 documented ones. `requirements-analyst` is proven independently (its own dedicated tests) but not yet wired in as that workflow's own first step — the identical "prove alone first, chain later" sequencing every other agent in this pack's history has followed.

This section should be updated (or removed, once the gap closes) every time an agent listed above genuinely gets built, per `implementation_status.md`'s own maintenance discipline.

---

### Detailed Responsibilities

**Requirements Analyst**  
- Analyze requirements and specifications  
- Detect ambiguities and gaps  
- Produce structured requirements  
- Propose acceptance criteria  

**Architecture**  
- Design solution architecture  
- Define component boundaries  
- Maintain Architecture Decision Records (ADRs)  
- Ensure architectural compliance  

**Technical Planning**  
- Break work into implementation tasks  
- Define sequencing and dependencies  
- Produce executable plans  

**Backend Development**  
- Build backend services and APIs  
- Follow coding standards  
- Deliver production-grade code  

**Frontend Development**  
- Build UI and client-side logic  
- Integrate backend APIs  
- Maintain UX consistency  

**Database**  
- Design schemas and migrations  
- Optimize integrity and performance  
- Define data access patterns  

**API Design**  
- Define versioned API contracts  
- Maintain consistency and compatibility  

**DevOps**  
- Build CI/CD pipelines  
- Manage containers, IaC and deployment readiness  

**Security**  
- Review architecture and code  
- Detect vulnerabilities  
- Recommend mitigations  

**QA/Test Engineer**  
- Design automated tests  
- Improve coverage  
- Validate acceptance criteria and quality gates  

**Code Review**  
- Review correctness, readability and standards  
- Provide structured feedback  

**Documentation**  
- Maintain READMEs, APIs and design documentation  
- Keep documentation synchronized with implementation  

**Release**  
- Manage versioning  
- Prepare changelogs and release notes  
- Verify release readiness  

**Refactoring**  
- Reduce technical debt  
- Improve maintainability  
- Preserve observable behaviour  

**Performance**  
- Identify bottlenecks  
- Profile workloads  
- Recommend or implement optimizations  

**Build** (added 2026-07-28 — see "Currently Implemented Subset" above)  
- Given a design or instruction, produce exactly one concrete file implementing it  
- Write it to disk through the sandbox — no direct filesystem access  
- Deliberately generic and stack-agnostic — narrower and more mechanical than Backend/Frontend/Database Development, which this pack has not yet built  

---

## Common Rules

All agents shall:

- Obey the Agent Contract and Communication Rules
- Execute only through the Workflow Engine
- Use the LLM Gateway for AI capabilities
- Use approved Tools for side effects
- Respect Quality Gates and Human Approval Points
- Follow Coding Standards & Best Practices
- Emit structured logs, metrics and traces

---

## Supported Workflows

- New Product Development
- Feature Development
- Bug Fix
- Legacy Modernization
- Architecture Assessment
- Code Review
- Release Management
- Production Support

---

## Security & Observability

Every invocation shall record Trace ID, Workflow ID, Agent ID, tool calls, LLM usage, token consumption, cost, duration and outcome while following least-privilege access and never exposing secrets.

---

## Extensibility

Additional agents may be added through future versions of this Capability Pack without Kernel changes, provided they comply with the Manifest Schema and Agent Contract.

---

## Current Status

This document establishes the baseline Software Engineering Capability Pack agent catalog. Detailed schemas, permissions, prompts and implementation specifications are maintained in individual agent documents.

---

## Final Authority

1. Capability Pack Contract  
2. Agent Architecture & Agent Contract  
3. Agent Catalog  
4. Software Engineering Pack – Overview  
5. Software Engineering Pack – Agents  
6. Source Code
