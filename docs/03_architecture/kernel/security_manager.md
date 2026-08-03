# Security Manager Design – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Security Manager Design  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## Implementation Status (2026-08-03, `P03-S05-M14-T10`)

**Partially built — a minimal slice, not production-credible.** Real: `Principal`, `SecurityContext`, `permissions_for_roles()`, `JWTBearerTokenVerifier`, and a `require_permission()` FastAPI dependency enforcing **four** permissions (`workflow:start`, `workflow:read`, `pack:read`, `pack:manage`) across 9 routes. **A second, real authorization mechanism now exists alongside it, deliberately not folded into the same flat lookup**: `security_manager.approval_authorization.is_authorized_to_decide_approval` enforces ADR-0023's own documented per-class `approver:<class>` role grant (e.g. `approver:release` distinct from `approver:architecture`) — a shape the fixed 5-role `permissions_for_roles()` dict structurally cannot express, since it looks up exact role strings against a static grant table, not a role *family* parameterized by an arbitrary, workflow-declared class. `workflow_engine.human_approval.ApprovalService` is its one real caller today, gating Human Approval Point decisions (`decide()`) before any write; requires `admin` or the exact class-scoped role.

**Updated (`P03-S03-M30-T06`): a real HTTP route now closes "not yet operable end to end without a human hand-editing test/seed data" — `POST /api/v1/workflows/{workflow_id}/approvals/{approval_id}/decisions` (`ai_os_kernel.routes.approvals`).** A real, concrete finding along the way, corrected before shipping: a first version gated this route with `require_permission()`, and a real request proved it genuinely broken — a principal holding only the realistic, minimal grant ADR-0023 itself documents (`approver:approve-git-push`, never a separate bare `approver`) was refused before ever reaching the real, class-scoped check, since `permissions_for_roles()`'s flat, exact-string lookup cannot recognize a class-scoped role at all. Fixed by exporting `security_manager.authenticate` directly (real Bearer/JWT verification, no flat permission check) and deferring the entire authorization decision to `ApprovalService`, which already gets this right.

**Updated (`P03-S05-M14-T07`): role *administration* is now real — a real Bearer token no longer has to already carry the right `approver:<class>` claim.** `security_manager.role_administration.RoleAdministrationService` grants/revokes a real, persisted `approver:<class>` role for a principal (`admin`-gated, `security.role_grants`, data_model.md §9a), genuinely enforced: `ApprovalService.decide()` now optionally unions real, active grants into `principal.roles` before the unchanged class-scoped check runs — a token-only principal's own behaviour is unaffected. **Every grant/revoke is a real, hash-chained `governance.audit_log` row** (`security.role_granted`/`security.role_revoked`/the denied-attempt variants), not merely structlog — the first Security Manager event type to reach that tamper-evident path at all (see the "Not built" line below, corrected accordingly). Proven end to end, real Postgres: a decision refused, then genuinely enabled by a real grant for the identical, unchanged token, then genuinely disabled again by a real revoke.

**Updated (`P03-S05-M14-T08`): role administration is now reachable over real HTTP too — `POST`/`DELETE /api/v1/security/role-grants` (`ai_os_kernel.routes.role_administration`), closing the "service-layer only" caveat the line above disclosed.** The identical shape `P03-S03-M30-T06` already established for the decide route: authenticated via bare `security_manager.authenticate` (no flat permission check), the entire `admin`-only authorization decision deferred to `RoleAdministrationService`, which already gets this right — no parallel authorization mechanism invented for the route boundary. Revoke is a body-carrying `DELETE` (not a path-parameter one), since a role string like `approver:release` is a legitimate resource identifier but embedding it in a URL path invites needless colon-encoding questions. Proven end to end, real Postgres, real HTTP: an `admin` principal genuinely grants then revokes a role through the route (read back directly from `security.role_grants`, not trusted from the response body alone, with both the grant and revoke each producing exactly one real `governance.audit_log` row); a non-admin principal's request to either endpoint is refused with a `403` and makes no real grant.

**Updated (`P03-S05-M14-T09`): the monotonic-narrowing chain's principal term is now real too, threaded into agent/tool resolution alongside the existing pack-grant term.** `security_manager.narrowing.over_permitted_permissions` (reusing the identical `intersect_declared_permissions` primitive `over_granted_permissions` already uses for the pack term) is checked by `SqlAgentRegistry`/`SqlToolRegistry` when a real principal permission set is supplied. Resolution can happen long after the triggering HTTP request ended (a worker-loop tick has no bearer token at all), so a real, disclosed design decision was made rather than assumed: a triggering principal's `SecurityContext.permissions` is captured once, at trigger time, into a new, nullable `workflow_instances.principal_permissions` column, and read back at every later step — `NULL` means unenforced, never an empty-set "holds nothing" claim. The one real caller with a live `SecurityContext` (`routes/workflows.py`'s `start_workflow`) now supplies it. Proven end to end, real Postgres: a pack grants both `llm:invoke` and `sandbox:execute` — enough for the pre-existing pack-grant term alone to resolve the agent — but a principal holding only `sandbox:execute` is genuinely refused resolving that identical agent, isolating the principal term as the cause.

**Updated (`P03-S05-M14-T10`): the monotonic-narrowing chain's workflow term is now real too, reusing the identical `over_permitted_permissions` primitive** (generalized to a `bounding_permissions` parameter so both terms share one function, not two near-identical ones). `catalog.workflow_definitions.declared_permissions` — the manifest's own `workflows[].permissions` ("the permission ceiling for every agent and tool in this workflow", ADR-0023) — is now genuinely derived at pack-registration time (`capability_manager.manifest_catalog_installer.derive_workflow_definition_rows`, mirroring the existing agent/tool/prompt derivation) and read at resolution time (`WorkflowDefinitionCatalog.get_declared_permissions`, keyed on the already-stable `(definition_id, definition_version)` a `WorkflowInstance` pins — no snapshot needed, unlike the principal term, since that pin is never ephemeral the way a bearer token is). `WorkflowInstanceService.advance()` fetches it once per step and threads it through `StepExecutor.execute()` to `SqlAgentRegistry`/`SqlToolRegistry`, exactly the principal term's own threading shape. Proven end to end, real Postgres: a pack grants both `llm:invoke` and `sandbox:execute` — enough for the pack-grant term alone to resolve the agent — but a workflow whose own declared ceiling holds only `sandbox:execute` is genuinely refused resolving that identical agent, isolating the workflow term as the cause. Two of ADR-0023's four terms (agent/tool declared-permission subsets, checked only against the pack grant today, never against `narrow_permissions`'s own full four-way call at real invocation time) remain outstanding.

**Not built:** full OIDC — tokens are **pre-shared-secret JWTs** verified against `AIOS_SECRET_SECURITY_JWT_SIGNING_KEY`, with no identity provider, no JWKS, and no issuer/audience validation, so anyone holding that secret can mint a token for any principal. Also absent: service-account API keys as a distinct mechanism, **the remaining half of the [ADR-0023](../../18_decision_log/adr/ADR-0023-identity-roles-and-permissions.md) monotonic-narrowing chain** (principal and workflow terms are now real at resolution; agent/tool declared-permission subsets are still never checked against `narrow_permissions`'s own full four-way call at real invocation time), the SDK's complete closed permission vocabulary, rate limiting, RFC 9457 error bodies, and a `governance.audit_log` writer for the *rest* of Security Manager's own authn/authz events (plain bearer-token authentication success/failure, route-level `require_permission()` denials — role administration alone now reaches the real audit path, the rest are still structlog-only). Outstanding Stage C/G work.

Authoritative, always-current status: `../../19_roadmap/feature_inventory.md` and `../../19_roadmap/implementation_status.md`. Build history: `../../19_roadmap/history/INDEX.md`.

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
