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

## Implementation Status (2026-08-03, `P03-S05-M14-T09`; `workflow:control` added 2026-08-10, `P06-S01-M36-T04`)

**§4.2's "operator: ... start / cancel / retry workflows" grant is now fully real, not just `workflow:start`.** `security_manager.permissions.WORKFLOW_CONTROL` (`"workflow:control"`) gates `POST /api/v1/workflows/{id}/cancel` (`api_architecture.md` §6.1), granted identically to `workflow:start` — `operator`/`maintainer`/`admin`, since this table's own text names both together for the same role, and no role holds one without the other. `retry` remains ungated by anything real, since no retry route exists yet.

**The identity and role layer is real; the permission-narrowing chain it composes into is not — yet, and the gap is disclosed by the implementing module's own docstring, not glossed over.** Verified against `kernel/src/ai_os_kernel/security_manager/models.py`: `Principal` (id, type, roles) and `SecurityContext` (principal + computed `permissions: frozenset[str]`) both exist and are used at the API boundary — §4.2's roles and §3.2's "Security Context" are real.

**§4.2's per-class `approver` grant — "`approver:release` distinct from `approver:architecture`" — is now real too, the first genuinely class-scoped role check in this codebase.** `security_manager.approval_authorization.is_authorized_to_decide_approval` reads `Principal.roles` directly (not `permissions_for_roles()`, whose fixed 5-role dict cannot express a role *family* parameterized by an arbitrary class) and requires `admin` or the exact `approver:<approval_class>` string. Its one real caller, `workflow_engine.human_approval.ApprovalService`, gates Human Approval Point decisions, proven refusing before any write against both fakes and a real Postgres row.

**Updated (`P03-S05-M14-T07`): role *administration* is now real too — the "manual-JWT-crafting gap" this section itself named is closed.** `security_manager.role_administration.RoleAdministrationService` (`admin`-gated, reusing `ADMIN_ROLE` unchanged) grants/revokes a real, persisted `approver:<class>` role for a principal, in a new `security.role_grants` table (data_model.md §9a) — every grant/revoke genuinely audited via the existing `governance.audit_log` writer, allowed and denied alike, the identical shape `AccessBroker` already established. Investigated first: persisted grants *augment* a bearer token's own `roles` claim, never replace it — `ApprovalService.decide()` now optionally unions real, active grants into `principal.roles` before the unchanged `is_authorized_to_decide_approval` check runs, so a token-only principal behaves exactly as before. Proven end to end, real Postgres: a decision refused for a principal holding no grant; the identical principal (bearer token unchanged throughout) then succeeds once an admin grants the role; a fresh decision is refused again once the admin revokes it.

**Updated (`P03-S05-M14-T08`): reachable over real HTTP now too — `POST`/`DELETE /api/v1/security/role-grants`.** The identical shape `P03-S03-M30-T06` already established for the decide route: bare `security_manager.authenticate` (real Bearer/JWT verification, no flat permission check), the entire `admin`-only authorization decision deferred to `RoleAdministrationService`. Proven end to end, real Postgres, real HTTP: an `admin` genuinely grants then revokes a role through the route (read back directly from `security.role_grants`, each producing exactly one real `governance.audit_log` row); a non-admin request to either endpoint is refused with a `403` and makes no real grant.

**Updated (`P03-S03-M30-T06`): reachable over real HTTP now too, and a real, concrete confirmation that `permissions_for_roles()` genuinely cannot express a class-scoped role — not merely a theoretical limit.** `POST /api/v1/workflows/{workflow_id}/approvals/{approval_id}/decisions` (`ai_os_kernel.routes.approvals`) is the first route to authenticate via `security_manager.authenticate` directly rather than `require_permission()` — a first version used the latter and a real request against a principal holding only `approver:approve-git-push` (no separate bare `approver`, the realistic minimal grant this same section already describes) was refused with a `403` before ever reaching `is_authorized_to_decide_approval` at all. `require_permission()`'s own flat, exact-string role lookup has no way to recognize `approver:approve-git-push` as implying anything — confirming §4.2's own class-scoped grant genuinely cannot be expressed by §4.3's flat permission model, exactly as this document's own prior paragraph already predicted.

**§4.4's "Monotonic Narrowing — the core rule" now has two of its four terms genuinely enforced at resolution, not only computed.** `ai_os_kernel.security_manager.narrowing.narrow_permissions`/`is_permitted` (`P03-S05-M14-T03`) compute ADR-0023's exact intersection (principal ∩ workflow ∩ agent ∩ tool). `P02-S05-M13-T08` gave the agent/tool terms a real data source: `catalog.agents.required_permissions`/`catalog.tools.required_permissions` are manifest-sourced values, checked against their own pack's manifest-declared `permissions` at resolution (`SqlAgentRegistry`/`SqlToolRegistry`), reusing the narrowing primitive rather than a bespoke check — an over-granted agent/tool is refused before its entrypoint ever loads.

**Updated (`P03-S05-M14-T09`): the principal term is now threaded into that identical resolution point too — the specific gap this section's own prior paragraph named ("`SecurityContext` is never threaded into resolution at all") is closed.** `security_manager.narrowing.over_permitted_permissions` (new function, reusing the same `intersect_declared_permissions` primitive `over_granted_permissions` already does for the pack-grant term) is checked at agent/tool resolution alongside the existing pack-grant check, when a real principal permission set is supplied. Reaching resolution — which can happen long after the triggering HTTP request (and its bearer token) has ended, including from a worker-loop tick with no request in scope at all — needed a real design decision: a principal's `SecurityContext.permissions` is captured **once**, at workflow-trigger time, into a new `workflow_instances.principal_permissions` column (nullable — `NULL` means unenforced, never an empty-array "holds nothing" claim), and read back by `WorkflowInstanceService.advance()` at every later step, the identical shape `workflow_id` already threads through `StepExecutor.execute()`. The one real caller with a live `SecurityContext` synchronously (`routes/workflows.py`'s `start_workflow`) now supplies it; every other trigger call omits it, leaving that instance's own principal term unenforced, exactly as before this step. Proven end to end, real Postgres: a pack's own manifest grants both `llm:invoke` and `sandbox:execute` — broad enough that the pre-existing pack-grant term alone resolves the agent — but a principal whose own permissions hold only `sandbox:execute` is genuinely refused resolving that identical agent, proving the principal term, not the pack term, is what changed the outcome. Still missing: no code parses a *workflow's* own declared `permissions` out of a manifest, so the full four-way chain still never runs in one call; §4.4's "There is no runtime elevation path" now holds for the principal ⊇ pack ⊇ agent/tool slice, not only pack ⊇ agent/tool.

**§4.3 Permission Model's closed vocabulary is real**: `platform_sdk/schemas/manifest.schema.json` does enumerate and validate the permission strings a manifest may request.

Authoritative, always-current status: `../19_roadmap/feature_inventory.md` and `../19_roadmap/implementation_status.md`.

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

This document deepens the Authentication & Authorization design. See the Implementation Status section near the top: `Principal`/`SecurityContext` and the closed permission vocabulary are real; the full workflow/agent/tool monotonic-narrowing chain (§4.4) is not yet implemented, by the implementing module's own explicit admission.

Concrete identity providers, token formats, permission catalogs, and policy engines will be refined during implementation.

---

## 9. Final Authority

Order of precedence:

1. Project Constitution  
2. AI Governance Framework  
3. Security Manager Design  
4. Authentication & Authorization Deep Dive  
5. Source Code

---

## 10. Related Documents

- [`security_architecture.md`](security_architecture.md) §9 — restates the same monotonic-narrowing chain as an already-mitigated threat control (T5); read alongside this document's Implementation Status for the real gap
- [`secrets_management.md`](secrets_management.md) — the secret-access authorization this system is meant to gate
- [ADR-0023](../18_decision_log/adr/ADR-0023-identity-roles-and-permissions.md) — the decision this document implements
- [`../19_roadmap/feature_inventory.md`](../19_roadmap/feature_inventory.md) · [`../19_roadmap/implementation_status.md`](../19_roadmap/implementation_status.md) — live build status
