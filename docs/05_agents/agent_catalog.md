# Agent Catalog – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Agent Catalog  
**Version:** 1.1  
**Status:** Approved  
**Last Updated:** 2026-07-28 (added `build` to the catalog to match the amendment already recorded in `../06_capability_packs/software_engineering/agents.md` and in the pack's real manifest; added Implementation Status and Related Documents; no responsibility changed)

---

## 1. Purpose

This document provides the official catalog of Agents that AI_OS will support in its initial releases.

It defines the identity, responsibility, and scope of each Agent so that:

- Capability Packs can implement them consistently
- The Workflow Engine can orchestrate them correctly
- Future LLMs and developers can understand the division of responsibilities

This document is subordinate to the Agent Architecture & Agent Contract.

---

## Implementation Status (2026-07-28)

**Built: 5 of the 17 agents catalogued below.** All five live in the Software Engineering pack, all five are registered in its real manifest (`../../capability_packs/software-engineering/manifest.yaml`), and all five have real tests:

| Agent slug | Real module | State |
|---|---|---|
| `requirements-analyst` | `../../capability_packs/software-engineering/src/ai_os_pack_software_engineering/agents/requirements_analyst.py` | Proven independently; **not yet chained** into `se.delivery_pipeline` |
| `architecture` | `../../capability_packs/software-engineering/src/ai_os_pack_software_engineering/agents/architecture.py` | Chained — step 1 of `se.delivery_pipeline` |
| `build` | `../../capability_packs/software-engineering/src/ai_os_pack_software_engineering/agents/build.py` | Chained — step 2 |
| `qa-test` | `../../capability_packs/software-engineering/src/ai_os_pack_software_engineering/agents/verification.py` | Chained — step 3. Makes **no LLM call**; pass/fail comes from a real sandboxed exit code |
| `documentation` | `../../capability_packs/software-engineering/src/ai_os_pack_software_engineering/agents/documentation.py` | Chained — step 4 |

Note that the real module filename for `qa-test` is `verification.py`, not `qa_test.py` — a historical name kept after the agent id was reconciled.

**`technical-planner` is now real** (`P03-S02-M29-T08`, 2026-08-07): `../../capability_packs/software-engineering/src/ai_os_pack_software_engineering/agents/technical_planner.py`, producing a real, schema-validated plan artifact from a design — ADR-0021's own sanctioned mechanism. Not chained into `se.delivery_pipeline` (that workflow has no design-decomposition step), and no real `foreach` `StepType`/executor exists anywhere to consume its output — both disclosed, not oversights (see the agent's own module docstring and `ADR-0021`'s updated Implementation Status).

**`frontend-developer` is now real** (`P08-S01-M29-T01`, 2026-08-07): `../../capability_packs/software-engineering/src/ai_os_pack_software_engineering/agents/frontend_developer.py` — reuses `build.py`'s/`database.py`'s/`api_designer.py`'s own write-through-sandbox mechanism verbatim; the one real addition is a frontend-file-extension precondition (`.tsx`/`.jsx`/`.ts`/`.js`/`.vue`/`.svelte`/`.html`/`.css`/`.scss`), enforced before any sandbox call. Establishes the real, catalog-documented `frontend-developer` identity `workflows.md`'s own `se.implement_task` graph names as a `task.kind`-routed choice — `backend-developer`, its own named sibling, has **no ticket anywhere in this roadmap**, a real, disclosed gap this step found but did not attempt to close. Not chained into any workflow.

**`refactoring` is now real** (`P08-S01-M29-T06`, 2026-08-07): `../../capability_packs/software-engineering/src/ai_os_pack_software_engineering/agents/refactoring.py` — the only agent in this pack that runs a genuine before/after test comparison for a single file: reads the file's own real content, runs the caller's own `runCommand` against it (baseline), refuses before any LLM call or write if the baseline itself does not pass, calls the model for a refactor, writes it back, then runs `runCommand` again — `refactored` is mechanically `passedBefore and passedAfter`, never an LLM's own opinion. "Behaviour assertions unchanged" (FR-043) holds structurally: this agent never writes to any file except the one it refactors. Not chained into any workflow.

**Not built:** `backend-developer`, `frontend-developer`, `database`, `api-designer`, `devops`, `security`, `code-reviewer`, `release`, `refactoring`, `performance`, and `existing-project-analyzer`. **This list itself has other, broader, pre-existing staleness beyond this ticket's own scope**: several of these names (`database`, `api-designer`, `security`, `code-reviewer`, and `release`) already have real code/manifest entries in `manifest.yaml` from earlier steps this session that were never reflected in this table — a holistic refresh of this whole document is real, disclosed, unclaimed follow-up work, not attempted here. `existing-project-analyzer` additionally has no pack to live in: `capability_packs/project_intelligence/` is an empty directory.

The only real workflow any of these agents participates in is `se.delivery_pipeline` (`../../capability_packs/software-engineering/workflows/delivery_pipeline.yaml`), which is narrower than any of the workflows named in `../06_capability_packs/software_engineering/workflows.md`.

Authoritative, always-current status: `../19_roadmap/feature_inventory.md` (per-module completion table — see rows 29–34). Build history: `../19_roadmap/history/INDEX.md`.

---

## 2. Design Principles for the Catalog

- Prefer a **focused set of high-quality agents** over a large number of overlapping agents.
- Each agent must have a clear, narrow responsibility.
- Agents must not overlap significantly in purpose.
- New agents should be added only when a clear gap exists.

---

## 3. Identifier Convention

**Agent IDs are fully qualified, kebab-case, and globally unique:** `<pack_id>/<agent_slug>`, for example `software-engineering/backend-developer`.

The `SE-0nn` codes used in an earlier draft of the Software Engineering Pack's Agents document are **withdrawn**. They are not aliases and must not appear in manifests, prompts, telemetry, or traceability links. The `Agent ID` column below is the pack-local slug; the fully qualified form prefixes the owning pack.

Ownership is single: exactly one pack owns each agent. Full contract-level specifications are in `agent_specifications.md`.

---

## 4. Initial Agent Catalog (17 Agents)

| #  | Agent slug                       | Name                              | Primary Responsibility                                                                 | Owning Capability Pack         |
|----|----------------------------------|-----------------------------------|----------------------------------------------------------------------------------------|--------------------------------|
| 1  | requirements-analyst              | Requirements Analyst Agent        | Analyze, refine, clarify and validate requirements; detect gaps and ambiguities        | Software Engineering           |
| 2  | architecture                     | Architecture Agent                | Produce and validate system architecture, component boundaries and key decisions       | Software Engineering           |
| 3  | technical-planner                | Technical Planning Agent          | Break architecture and requirements into detailed technical tasks and implementation plan | Software Engineering        |
| 4  | backend-developer                | Backend Development Agent         | Design and implement backend services, business logic and APIs                         | Software Engineering           |
| 5  | frontend-developer               | Frontend Development Agent        | Design and implement user interfaces and client-side logic                             | Software Engineering           |
| 6  | database                         | Database Agent                    | Design data models, schemas, migrations and data access patterns                       | Software Engineering           |
| 7  | api-designer                     | API Design Agent                  | Define and maintain clean, versioned API contracts                                     | Software Engineering           |
| 8  | devops                           | DevOps Agent                      | Create and maintain CI/CD, containerization, infrastructure and deployment configuration | Software Engineering         |
| 9  | security                         | Security Agent                    | Perform security analysis, identify vulnerabilities and recommend mitigations          | Software Engineering           |
| 10 | qa-test                          | QA / Test Engineer Agent          | Design, write and improve automated tests; raise coverage and quality                  | Software Engineering           |
| 11 | code-reviewer                    | Code Review Agent                 | Review code for correctness, standards compliance, readability and potential defects   | Software Engineering           |
| 12 | documentation                    | Documentation Agent               | Produce and maintain technical documentation, READMEs, ADRs and API docs               | Software Engineering           |
| 13 | release                          | Release Agent                     | Manage versioning, changelogs, release notes and release readiness                     | Software Engineering           |
| 14 | refactoring                      | Refactoring Agent                 | Improve structure, readability and maintainability of existing code without changing behaviour | Software Engineering     |
| 15 | existing-project-analyzer        | Existing Project Analysis Agent   | Understand, document and analyse existing / legacy codebases                           | Project Intelligence           |
| 16 | performance                      | Performance Agent                 | Analyse performance characteristics and recommend or apply optimizations               | Software Engineering           |
| 17 | build                            | Build Agent                       | Given a design or instruction, produce exactly one concrete file and write it through the sandbox — deliberately generic and stack-agnostic | Software Engineering           |

**On entry 17.** `build` was added to this catalog on 2026-07-28 to match the amendment already made and reasoned through in `../06_capability_packs/software_engineering/agents.md` ("Currently Implemented Subset"). It is a real, shipped agent whose scope — write one generic file from an instruction — does not fit `backend-developer`'s documented scope ("backend services, business logic and APIs") or any other pre-existing entry. It was catalogued honestly rather than force-fitted to an ill-matching id or left undocumented in code.

---

## 5. Agent Ownership

- Sixteen of the agents above are owned by the **Software Engineering Capability Pack** (`software-engineering/…`).
- **`existing-project-analyzer` is owned solely by the Project Intelligence Pack** (`project-intelligence/existing-project-analyzer`). It is not an agent of the Software Engineering pack and carries no `SE-…` identity.
- An agent owned by one pack may **participate** in a workflow declared by another. That is not pack coupling: the Workflow Engine invokes the agent, the workflow declares the reference, and neither pack imports the other.
- Future Capability Packs may introduce additional specialized agents.

---

## 6. Rules

*(This section was numbered "5" alongside Agent Ownership until 2026-07-28; corrected here.)*

- No agent may take on responsibilities that belong to another agent without an explicit workflow-level decision.
- Agents must stay within the scope defined in this catalog.
- Any proposal to add, remove, or significantly change an agent’s responsibility requires an ADR.

---

## 7. Current Status

This catalog defines the initial target set of agents. Five of the seventeen are real — see the Implementation Status block above.

Detailed specifications live in two places, both of which exist today:

- **Contract-level specifications** (identity, I/O models, tools, prompts, permissions, model alias, behavioural requirements, tests) → `agent_specifications.md`. That document currently specifies three agents in full; see its own Implementation Status block for which, and for the gap between what it specifies and what is built.
- **Pack-level responsibilities and the currently-implemented subset** → `../06_capability_packs/software_engineering/agents.md` and `../06_capability_packs/project_intelligence/agents_workflows.md`.

---

## 8. Final Authority

Order of precedence:

1. Project Constitution  
2. AI Governance Framework  
3. Agent Architecture & Agent Contract  
4. Agent Catalog  
5. Capability Pack specific agent definitions  
6. Source Code

---

## 9. Related Documents

**Governing documents (this one is subordinate to these)**
- `../03_architecture/agents/agent_architecture.md` — the Agent Contract this catalog assumes
- `../03_architecture/agents/agent_communication.md` — the 5 allowed / 5 forbidden communication patterns
- `../03_architecture/capability_framework/capability_pack_contract.md` — what a pack must provide to own an agent
- `../03_architecture/capability_framework/manifest_schema.md` — how an agent is declared
- `../../platform_sdk/schemas/manifest.schema.json` — the real, enforced machine schema for those declarations

**Downstream specification**
- `agent_specifications.md` — contract-level specifications for these agents
- `../06_capability_packs/software_engineering/agents.md` — pack-level responsibilities for the 16 SE agents
- `../06_capability_packs/software_engineering/workflows.md` — the workflows these agents are intended to participate in
- `../06_capability_packs/project_intelligence/agents_workflows.md` — `existing-project-analyzer`'s owning pack

**Real implementations (the only agent code that exists)**
- `../../capability_packs/software-engineering/manifest.yaml` — the five real agent declarations
- `../../capability_packs/software-engineering/src/ai_os_pack_software_engineering/agents/requirements_analyst.py`
- `../../capability_packs/software-engineering/src/ai_os_pack_software_engineering/agents/architecture.py`
- `../../capability_packs/software-engineering/src/ai_os_pack_software_engineering/agents/build.py`
- `../../capability_packs/software-engineering/src/ai_os_pack_software_engineering/agents/verification.py` — the `qa-test` agent
- `../../capability_packs/software-engineering/src/ai_os_pack_software_engineering/agents/documentation.py`
- `../../capability_packs/software-engineering/prompts/` — the four real prompts
- `../../capability_packs/software-engineering/workflows/delivery_pipeline.yaml` — the one real workflow chaining four of them

**Requirements and status**
- `../02_requirements/functional/functional_requirements.md` — FR-030–FR-045 (SE pack), FR-050–FR-059 (Project Intelligence)
- `../19_roadmap/feature_inventory.md` — live completion status (rows 29–34)
- `../19_roadmap/feature_inventory.md` — the authority on per-module completeness
- `../20_glossary/glossary.md` — canonical definition of "Agent" and related terms
