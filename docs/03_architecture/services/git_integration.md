# Git Integration Service – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Git Integration Service  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## Implementation Status (2026-07-28)

**Built: nothing. This document is a design specification only.** No Platform Service exists in code — the `platform_services/` directory has **no tracked content at all**, so it is absent from a fresh clone (git does not track empty directories). No Kernel component consumes this service. No Git operation of any kind is performed by AI_OS today — no clone, no commit, no push. The Software Engineering pack's Build Agent writes files into a sandbox working directory and nothing places them under version control.

Consequence for the threat model: the T11 ("Git history or branch destruction") controls in `../../09_security/security_architecture.md` §14 — force-push prohibition, protected-branch policy, credentials never entering a sandbox — are **currently satisfied only because no Git capability exists**. They become real implementation requirements with this service. Stage C deliverable.

Authoritative, always-current status: the per-module completion table in `feature_inventory.md` and `implementation_status.md`; build history in `history/INDEX.md` (all under `docs/19_roadmap/`).

## 1. Purpose

This document defines the design of the **Git Integration Service**, a shared Platform Service in AI_OS.

The Git Integration Service provides a controlled, auditable interface for interacting with Git repositories. It is the primary way Agents and Tools perform version-control operations (clone, status, diff, commit, branch, etc.) without embedding Git logic directly in agents.

This document is subordinate to:

1. Project Constitution  
2. System Architecture  
3. Kernel Architecture  
4. Security Manager Design  
5. Software Engineering Pack  

---

## 2. Design Goals

The Git Integration Service must:

- Provide a safe, permission-aware interface to Git operations
- Support the most common workflows needed by software engineering agents
- Be fully observable and auditable
- Prevent uncontrolled or destructive operations
- Work with both local and remote repositories
- Remain configuration-driven

---

## 3. Core Responsibilities

- Clone / fetch repositories
- Report status and diffs
- Stage and commit changes (under strict controls)
- Create and switch branches
- Support pull / push operations (with authorization)
- Provide repository metadata
- Enforce permissions and policies
- Emit detailed audit events for all mutating operations

---

## 4. High-Level Structure

```text
Git Integration Service
│
├── Git Interface (abstract)
├── Repository Manager
├── Operation Executors
│     ├── Read Operations (status, diff, log, show)
│     └── Write Operations (add, commit, branch, merge, push)
├── Permission & Policy Checker
├── Working Copy Manager
└── Observability & Audit
```

---

## 5. Key Design Rules

- Agents never invoke the Git CLI directly; they go through this service or approved Tools that use it.
- **Credentials live in this service and never enter a sandbox.** The service exposes the *operation* (`push`) and withholds the *credential*. A sandboxed step receives a capability, not a secret ([ADR-0024](../../18_decision_log/adr/ADR-0024-secrets-management-backend.md)).
- Working copies are **isolated per workflow instance — mandatory, not best-effort.** This is what prevents concurrent-write corruption in parallel and fan-out workflows.
- Every mutating operation is audited with actor, repository, branch, and commit range.

### 5.1 Prohibited Operations

These are **absent from the tool surface** — not gated, not configurable-on, not available with elevated permission:

| Operation | Why |
|---|---|
| `push --force` / `--force-with-lease` to a protected branch | Destroys customer work irrecoverably |
| Branch deletion on a protected branch | Same |
| History rewriting (`rebase --force`, `filter-branch`, `reset --hard` + push) | Same |
| Direct push to a protected branch | Bypasses review; all changes go via a feature branch and pull request |

Making these unavailable rather than permission-gated is deliberate: a permission can be misconfigured, and the consequence here is unrecoverable. Every push targets a feature branch; integration happens through a pull request with human approval ([ADR-0007](../../18_decision_log/adr/ADR-0007-human-governance-for-critical-decisions.md)).

---

## 6. Relationship with Other Components

- **Software Engineering Pack** (especially Backend, Frontend, DevOps, Release, Refactoring agents) is the primary consumer.
- **Tools** in the Software Engineering Pack will typically wrap this service.
- **Security Manager** enforces who can perform which Git operations.
- **Workflow Engine** provides the context (which workflow / experiment is performing the operation).
- **Observability** records every significant Git operation.
- **Storage Service** may be used for temporary working copies or artifacts.
- **Configuration Manager** supplies repository URLs, credentials references, and policies.

---

## 7. Observability & Audit Requirements

Every significant Git operation must record:

- Operation type
- Repository identifier
- Branch / commit information
- Success / failure
- Actor (workflow, agent, user)
- Trace ID / Workflow ID
- Timestamp

Mutating operations are especially important for the audit trail.

---

## 8. Current Status

This document defines the design baseline for the Git Integration Service.

Concrete command mappings, working-copy isolation strategies, and permission models will be refined during implementation.

---

## 9. Final Authority

Order of precedence:

1. Project Constitution  
2. System Architecture  
3. Kernel Architecture  
4. Git Integration Service  
5. Source Code
