# Security Manager Design – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Security Manager Design  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## 1. Purpose

This document defines the design of the **Security Manager**, a core component of the AI_OS Platform Kernel.

The Security Manager is responsible for enforcing authentication, authorization, least privilege, secret handling policies, and other security controls across the platform. It ensures that Agents, Tools, Workflows, and Capability Packs operate within approved security boundaries.

This document is subordinate to:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Kernel Architecture  
5. Capability Pack Contract  

---

## 2. Design Goals

The Security Manager must:

- Enforce least privilege
- Provide a consistent authorization model
- Protect secrets and credentials
- Validate that Capability Packs and Agents only receive the permissions they have declared and been granted
- Support auditability of security-relevant actions
- Remain domain-agnostic
- Integrate with the rest of the Kernel without becoming a bottleneck

---

## 3. Core Responsibilities

- Authenticate callers where applicable (users, services, external systems)
- Authorize actions based on declared permissions and policies
- Manage and inject secrets securely (never expose them to Capability Packs unnecessarily)
- Validate permissions declared in manifests
- Enforce security policies at key points (Agent invocation, Tool invocation, Workflow start, etc.)
- Produce audit records for security-relevant events
- Support policy updates without requiring Kernel code changes where practical

---

## 4. High-Level Structure

```text
Security Manager
│
├── Authentication Service
├── Authorization Engine
├── Permission Registry
├── Secret Manager Interface
├── Policy Engine
├── Security Context Propagator
└── Audit Logger
```

---

## 5. Key Concepts

### Permission
A discrete right that can be granted (e.g., `filesystem:read`, `git:write`, `llm:invoke`, `network:external`).

### Security Context
The set of identities, roles, and permissions associated with a running workflow or agent invocation.

### Policy
Rules that determine whether a particular action is allowed given the current security context.

---

## 6. Key Design Rules

- Capability Packs must declare the permissions they need in their manifest.
- Agents and Tools may only exercise permissions that have been granted.
- Secrets must never be hard-coded or stored inside Capability Packs.
- Security checks should fail closed (deny by default).
- All significant security decisions must be auditable.

---

## 7. Relationship with Other Components

- **Manifest Loader** and **Capability Manager** interact with the Security Manager during registration and activation to validate requested permissions.
- **Workflow Engine** and **Agent Invoker** consult the Security Manager before performing privileged actions.
- **Tool Invoker** enforces tool-specific permissions.
- **LLM Gateway** relies on the Security Manager / Secret Manager for provider credentials.
- **Configuration Manager** works with the Security Manager for secure configuration values.
- **Dashboard** and external APIs rely on authentication and authorization services.

---

## 8. Observability & Audit

Security-relevant events that must be logged include:

- Authentication successes and failures
- Authorization decisions (especially denials)
- Secret access (without logging the secret values themselves)
- Permission grants or changes
- Policy violations

---

## 9. Concrete Decisions

The items v1.0 of this document deferred are now decided:

| Concern | Decision | Reference |
|---|---|---|
| Authentication | OIDC bearer tokens (users); API keys / client credentials (service accounts); agents never authenticate | [ADR-0023](../../18_decision_log/adr/ADR-0023-identity-roles-and-permissions.md) |
| Authorization model | Role + permission intersection with **monotonic narrowing**; deny by default; no runtime elevation | ADR-0023 |
| Roles | `viewer`, `operator`, `approver` (per class), `maintainer`, `admin` | ADR-0023 |
| Permission vocabulary | Closed set published in the SDK; unknown permissions fail manifest validation | `../capability_framework/manifest_schema.md` |
| Policy engine | None in v1 — role + permission intersection is sufficient. The authorization interface is designed so an external engine (OPA, Cedar) can be adopted later without changing call sites | ADR-0023 |
| Secret backend | `secret://` references resolved through pluggable backends; Vault is the production reference | [ADR-0024](../../18_decision_log/adr/ADR-0024-secrets-management-backend.md) |
| Sandbox enforcement | Two trust tiers; Tier 1 = ephemeral container, no network, no secrets | [ADR-0016](../../18_decision_log/adr/ADR-0016-tool-execution-sandboxing.md) |
| Multi-tenancy | **Out of scope for v1** — single tenant; the project boundary is organisational, not a security boundary | ADR-0023 |

The full threat model (T1–T12) and the controls addressing each are in `../../09_security/security_architecture.md`, which is the authoritative security document.

---

## 10. Final Authority

Order of precedence:

1. Project Constitution  
2. AI Governance Framework  
3. System Architecture  
4. Kernel Architecture  
5. Security Manager Design  
6. Source Code
