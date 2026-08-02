# Software Engineering Capability Pack – Agents

**Project:** AI_OS (AI Operating System)  
**Capability Pack:** Software Engineering  
**Document:** Agents Catalog & Responsibilities  
**Version:** 1.4  
**Status:** Approved  
**Last Updated:** 2026-08-02 (a new catalog entry, `git-push` — this pack's seventh agent, and the first to consume a Platform Service; now chained into `se.delivery_pipeline` as its own new, final step, after Documentation. Prior, 2026-07-30: a new catalog entry, `lint` — this pack's sixth agent, and the first added since the Capability Pack growth gate lifted 2026-07-29 — added specifically to prove the Quality Gate Engine's own gate mechanism generalizes to a second gate category (Static Analysis); now chained into `se.delivery_pipeline` between Build and Test. Prior, same day: `requirements-analyst` wired into `se.delivery_pipeline` as its own first step — all 5 real agents were chained, not 4 of 5. Prior: 2026-07-28, updated the "Currently Implemented Subset" section: `requirements-analyst` is now real, 5 of 16)

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
| `software-engineering/lint` | Lint | Run a real static-analysis tool against a file Build wrote and report a real pass/fail (added 2026-07-30 — see "Currently Implemented Subset" below for why this entry exists) |
| `software-engineering/git-push` | Git Push | Commit and push the file Build wrote through the real Git Integration Service, reached via ToolInvoker (added 2026-08-02 — see "Currently Implemented Subset" below for why this entry exists) |

**Not owned by this pack.** `project-intelligence/existing-project-analyzer` (legacy system analysis) belongs to the Project Intelligence Pack. It participates in this pack's workflows via the Workflow Engine, but it is not a Software Engineering agent and has no `SE-…` identity.

Contract-level specifications (I/O schemas, tools, prompts, permissions, behavioural requirements, tests) are in `../../05_agents/agent_specifications.md`.

---

## Currently Implemented Subset (2026-08-02)

*(This is this document's `## Implementation Status` section — kept under its established name rather than renamed, because the exact phrase "Currently Implemented Subset" is a cross-reference target from several other live documents. Formally recorded as a permitted variant in `docs/process/standing_rules.md`.)*

This document describes the full, intended agent catalog for this pack's mature design. As of this date, a much smaller, real slice actually exists in `capability_packs/software-engineering/`, built under a separate product-owner reprioritization toward "the shortest real path to a working multi-agent software-engineering pipeline" (see `docs/19_roadmap/implementation_status.md`'s own header for the full framing). This section exists so a reader of this document is never misled about the gap between the two.

**Real today: 7 of the 18 agents listed above** (16 original + `lint` + `git-push`, new entries added 2026-07-30/2026-08-02 for the identical reason `build` gained one).

| Agent ID (real) | Entrypoint | Notes |
|---|---|---|
| `software-engineering/requirements-analyst` | `ai_os_pack_software_engineering.agents.requirements_analyst:RequirementsAnalystAgentEntrypoint` | **Added 2026-07-28; wired into `se.delivery_pipeline` as its own first step 2026-07-30.** Matches this document's own catalog exactly. Analyzes/refines a raw requirement into a structured requirements analysis only — no architecture design, no code, no validation of acceptance criteria beyond what the model itself states (this catalog's own "validate requirements" is only half-real). |
| `software-engineering/architecture` | `ai_os_pack_software_engineering.agents.architecture:ArchitectureAgentEntrypoint` | Matches this document's own catalog exactly. Design proposal only — no code generation, no validation of an existing architecture (this catalog's own "Design **and validate** architecture" is only half-real). |
| `software-engineering/build` | `ai_os_pack_software_engineering.agents.build:BuildAgentEntrypoint` | **New catalog entry, added by this reconciliation.** Its real scope — write exactly one generic file from a design/instruction, through the sandbox — does not fit `backend-developer`'s own documented scope ("Backend services and APIs", implying a narrower, stack-specific role this agent does not have) or any other pre-existing entry. Rather than force-fit an ill-matching id or leave an undocumented one in code, this catalog gained a new, honestly-scoped entry instead. |
| `software-engineering/lint` | `ai_os_pack_software_engineering.agents.lint:LintAgentEntrypoint` | **New catalog entry, added 2026-07-30** — this pack's sixth agent, and the first added since the Capability Pack growth gate lifted (2026-07-29). Runs `python -m py_compile <file>` against a file Build wrote, through the sandbox, reporting a real pass/fail from the real exit code — no LLM call at all. `ruff` was tried first and genuinely works against the deterministic tier, but genuinely fails against `DockerSandbox`'s own default image (no `ruff` installed, no dependency-install step exists) — `py_compile`, a stdlib module, works identically on every real backend. Added specifically to prove the Quality Gate Engine's own gate mechanism (`gate_sources`/`success_field`/retry-target) genuinely generalizes to a second, distinct gate category (Static Analysis, not just Testing) via configuration alone — see `ai_os_kernel.workflow_engine.delivery_pipeline`'s own docstring. |
| `software-engineering/qa-test` | `ai_os_pack_software_engineering.agents.verification:TestAgentEntrypoint` | Matches this document's own catalog exactly (renamed from an earlier, undocumented `test` id during this same reconciliation). Deliberately makes **no LLM call at all** — pass/fail comes only from a real sandboxed exit code, narrower than this catalog's own "Automated testing and validation." |
| `software-engineering/documentation` | `ai_os_pack_software_engineering.agents.documentation:DocumentationAgentEntrypoint` | Matches this document's own catalog exactly. Records one Build+Test result as one Markdown file — narrower than this catalog's own general "Technical documentation." |
| `software-engineering/git-push` | `ai_os_pack_software_engineering.agents.git_push:GitPushAgentEntrypoint` | **New catalog entry, added 2026-08-02 (`P03-S04-M31-T04`)** — this pack's seventh agent, and the first to consume a Platform Service (the real Git Integration Service, `P03-S01-M24-T01`) via `platform.git.commit`/`platform.git.push`. Wired as `se.delivery_pipeline`'s new, final step. Genuinely commits and pushes Build's own file when constructed with a real `remote_url`; degrades to a real, structured no-op (`pushed: false`) when not — no real, non-hardcoded default remote exists yet, so every current real caller (the live HTTP route) is genuinely unaffected. Distinct from the already-documented `release` entry (broader: versioning, changelogs, readiness — a separate, later, `P08` agent) and `devops` (broader still) — force-fitting either would misrepresent this narrower slice, the identical reasoning `build`'s own reconciliation already established. |

**Not yet real: the other 11** (`technical-planner`, `frontend-developer`, `database`, `api-designer`, `devops`, `security`, `code-reviewer`, `release`, `refactoring`, `performance`, and `project-intelligence/existing-project-analyzer`). No code, manifest entry, or prompt exists for any of them in this pack today.

**All seven real agents are chained into one real, declared workflow**, `se.delivery_pipeline` — see `workflows.md`'s own "Currently Implemented Subset" section for why this is a distinct real workflow, not a rename of any of that document's own 7 documented ones. `requirements-analyst` was proven independently first (its own dedicated tests), the identical "prove alone first, chain later" sequencing every other agent in this pack's history has followed, then wired in as that workflow's own first step (2026-07-30) — a raw requirement now reaches Requirements Analyst first, and Architecture designs against its real, refined output. `git-push` (2026-08-02) is the pipeline's new, final step, after Documentation.

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

---

## Related Documents

- [`overview.md`](overview.md) · [`workflows.md`](workflows.md) — the pack overview and the one workflow (`se.delivery_pipeline`) that chains all 7 real agents
- [`../../05_agents/agent_specifications.md`](../../05_agents/agent_specifications.md) — contract-level I/O schemas for each catalog entry
- [`../../03_architecture/agents/agent_communication.md`](../../03_architecture/agents/agent_communication.md) · [`../../03_architecture/agents/agent_architecture.md`](../../03_architecture/agents/agent_architecture.md) — the platform rules every agent here follows
- [`../../03_architecture/capability_framework/capability_pack_contract.md`](../../03_architecture/capability_framework/capability_pack_contract.md) — the Platform SDK growth gate that froze this catalog at 5 real agents, now lifted (`platform_sdk_v1_scope.md` step 14) since this pack is fully SDK-compliant — `lint` and `git-push` are the 6th and 7th agents added since, each subject to the standing scope-approval process
- [`../../19_roadmap/feature_inventory.md`](../../19_roadmap/feature_inventory.md) · [`../../19_roadmap/implementation_status.md`](../../19_roadmap/implementation_status.md) — live build status
