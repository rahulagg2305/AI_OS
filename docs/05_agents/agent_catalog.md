# Agent Catalog – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Agent Catalog  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## 1. Purpose

This document provides the official catalog of Agents that AI_OS will support in its initial releases.

It defines the identity, responsibility, and scope of each Agent so that:

- Capability Packs can implement them consistently
- The Workflow Engine can orchestrate them correctly
- Future LLMs and developers can understand the division of responsibilities

This document is subordinate to the Agent Architecture & Agent Contract.

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

## 4. Initial Agent Catalog (16 Agents)

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

---

## 5. Agent Ownership

- Fifteen of the agents above are owned by the **Software Engineering Capability Pack** (`software-engineering/…`).
- **`existing-project-analyzer` is owned solely by the Project Intelligence Pack** (`project-intelligence/existing-project-analyzer`). It is not an agent of the Software Engineering pack and carries no `SE-…` identity.
- An agent owned by one pack may **participate** in a workflow declared by another. That is not pack coupling: the Workflow Engine invokes the agent, the workflow declares the reference, and neither pack imports the other.
- Future Capability Packs may introduce additional specialized agents.

---

## 5. Rules

- No agent may take on responsibilities that belong to another agent without an explicit workflow-level decision.
- Agents must stay within the scope defined in this catalog.
- Any proposal to add, remove, or significantly change an agent’s responsibility requires an ADR.

---

## 6. Current Status

This catalog defines the initial target set of agents.

Detailed specifications (inputs, outputs, tools, prompts, quality gates) for each agent will be defined inside the respective Capability Pack documentation.

---

## 7. Final Authority

Order of precedence:

1. Project Constitution  
2. AI Governance Framework  
3. Agent Architecture & Agent Contract  
4. Agent Catalog  
5. Capability Pack specific agent definitions  
6. Source Code
