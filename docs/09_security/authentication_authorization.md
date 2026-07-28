# Authentication & Authorization Deep Dive – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Authentication & Authorization Deep Dive  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## 1. Purpose

This document provides a deeper design of **Authentication** and **Authorization** in AI_OS.

It builds on the Security Manager Design and defines how identities are established and how permissions are enforced across the platform, including human users, services, workflows, and agents.

This document is subordinate to:

1. Project Constitution  
2. AI Governance Framework  
3. Security Manager Design  
4. Kernel Architecture  
5. Capability Pack Contract  

---

## 2. Design Goals

Authentication & Authorization must:

- Establish clear identity for every significant action
- Enforce least privilege
- Support both human and non-human actors
- Integrate cleanly with Capability Pack permissions declared in manifests
- Be auditable
- Remain flexible enough for different deployment environments

---

## 3. Authentication

### 3.1 Goals
- Verify the identity of users and services interacting with AI_OS
- Support multiple authentication mechanisms as needed (local, SSO, API keys, service identities, etc.)
- Propagate identity safely into the Security Context of workflows

### 3.2 Key Concepts
- **Principal** — the identity performing an action (user, service account, system component)
- **Credentials** — secrets or tokens used to prove identity
- **Security Context** — the authenticated identity + attributes carried through a request or workflow

### 3.3 Rules
- Unauthenticated access must be denied by default for protected operations.
- Credentials must never appear in logs or in Capability Pack source.
- Service-to-service authentication should use strong, rotatable identities.

---

## 4. Authorization

### 4.1 Goals
- Decide whether a given principal is allowed to perform a given action on a given resource
- Enforce permissions declared by Capability Packs and by platform policies
- Support fine-grained control where necessary (e.g., Git write, LLM invoke, secret access)

### 4.2 Roles

Decided in [ADR-0023](../18_decision_log/adr/ADR-0023-identity-roles-and-permissions.md). A principal may hold several roles; role→permission mappings are configuration.

| Role | Grants |
|---|---|
| `viewer` | Read workflows, experiments, gate results, health. No mutation. |
| `operator` | `viewer` + start / cancel / retry workflows, run experiments |
| `approver` | `viewer` + decide Human Approval Points. **Grantable per class** — `approver:release` is distinct from `approver:architecture`, so authority to ship is not authority to approve a design |
| `maintainer` | `operator` + install / activate / deactivate packs, edit non-security configuration |
| `admin` | All, including security policy, role assignment, and secret management. Every action audited |

### 4.3 Permission Model

Permissions are discrete rights in a **closed vocabulary** published in the SDK, formatted `<resource>:<action>` — for example `filesystem:read`, `git:write`, `llm:invoke`, `sandbox:execute`, `workflow:start`, `pack:manage`, `secret:manage`. The full list is in `../../platform_sdk/schemas/manifest.schema.json`. A manifest requesting an unknown permission **fails validation**; the vocabulary cannot be extended by a pack.

### 4.4 Monotonic Narrowing — the core rule

Authority only ever shrinks along the invocation chain:

```text
principal permissions
  ∩ workflow declared permissions
  ∩ agent declared permissions (manifest)
  ∩ tool declared permissions (manifest)
  = effective permissions for this tool invocation
```

An agent can never hold a permission its invoking workflow lacks; a tool can never exceed its agent. The result is carried in an immutable `SecurityContext`. **There is no runtime elevation path**, and no LLM output can widen the set — which is what makes prompt-injection containment structural rather than probabilistic.

Subset relationships are validated at **pack load time** (manifest rules 16–17), so an over-broad declaration fails at install rather than surfacing as a runtime denial mid-workflow.

### 4.3 Rules
- Deny by default.
- Agents and Tools may only exercise permissions that have been granted to them.
- Human Approval Points and high-impact operations may require elevated privileges or additional checks.
- Authorization decisions must be auditable.

---

## 5. Security Context Propagation

- Once authentication succeeds, a Security Context is created.
- The Security Context travels with the Workflow / request (alongside Trace ID and Workflow ID).
- Downstream components (Agent Invoker, Tool Invoker, LLM Gateway, Git Integration, etc.) consult the Security Context when making authorization decisions.

---

## 6. Relationship with Other Components

- **Security Manager** is the primary owner of authentication and authorization logic.
- **Manifest Loader / Capability Manager** validate and register requested permissions.
- **Workflow Engine** and **Agent Invoker** enforce authorization before privileged actions.
- **Git Integration**, **Storage**, **LLM Gateway**, and other services check permissions before execution.
- **Observability / Audit** records authentication and authorization events (especially failures and privileged actions).
- **Dashboard** and **Voice** interfaces authenticate human users.

---

## 7. Observability & Audit Requirements

Must record:

- Authentication successes and failures
- Authorization denials
- Privilege escalations or sensitive permission usage
- Correlation with Trace ID / Workflow ID / Principal

---

## 8. Current Status

This document deepens the Authentication & Authorization design.

Concrete identity providers, token formats, permission catalogs, and policy engines will be refined during implementation.

---

## 9. Final Authority

Order of precedence:

1. Project Constitution  
2. AI Governance Framework  
3. Security Manager Design  
4. Authentication & Authorization Deep Dive  
5. Source Code
