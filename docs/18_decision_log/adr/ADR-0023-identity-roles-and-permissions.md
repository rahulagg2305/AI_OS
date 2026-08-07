# ADR-0023: Identity, Roles, and the Permission Model

**Status:** Accepted
**Date:** 2026-07-25
**Decision Makers:** Chief Architect, Project Owner
**Related Documents:** `docs/09_security/authentication_authorization.md`, `docs/09_security/security_architecture.md`

---

## Context

The security documents defined permission *strings* (`git:write`, `llm:invoke`) but no principals, no roles, and no rule for how a workflow's authority relates to the authority of the agents and tools running inside it. Without that, "least privilege" cannot be implemented: there is nothing to compare a request against.

## Decision

**Three principal types, five roles, and a strict monotonic narrowing rule.**

**Principals**

| Type | Authenticated by | Example |
|---|---|---|
| `user` | OIDC bearer token | a human operator |
| `service_account` | API key or client credentials | CI system, external integration |
| `agent` | **Never authenticates.** Derived at invocation from the workflow's security context | `software-engineering/backend-developer` |

**Roles** (a principal may hold several; roles grant permission sets, defined in configuration)

| Role | Grants |
|---|---|
| `viewer` | Read workflows, experiments, gate results, health. No mutation. |
| `operator` | `viewer` + start/cancel/retry workflows, run experiments. |
| `approver` | `viewer` + decide Human Approval Points. Approval classes are grantable separately (for example `approver:release` distinct from `approver:architecture`). |
| `maintainer` | `operator` + install/activate/deactivate packs, edit non-security configuration. |
| `admin` | All, including security policy, role assignment, and secret management. Every `admin` action is audited. |

**The narrowing rule — the core of the decision.** Authority only ever shrinks along the invocation chain:

```
principal permissions
  ∩ workflow declared permissions
  ∩ agent declared permissions (manifest)
  ∩ tool declared permissions (manifest)
  = effective permissions for this tool invocation
```

An agent can never hold a permission its invoking workflow lacks; a tool can never exceed its agent. Effective permissions are computed at invocation and carried in an immutable `SecurityContext`. There is **no elevation path at runtime**, and no LLM output can widen the set — which is what makes the prompt-injection containment in [ADR-0016](ADR-0016-tool-execution-sandboxing.md) hold.

**Permission naming:** `<resource>:<action>`, with a closed vocabulary published in the SDK. A manifest requesting an unknown permission fails validation. Deny by default; absence of a permission is denial, never a default-allow.

**Multi-tenancy is explicitly out of scope for v1.** AI_OS v1 is a single-tenant platform: one organisation, one trust boundary, projects as an organisational rather than a security boundary. This is stated so that no one mistakes the project boundary for isolation. Multi-tenancy would require row-level security, per-tenant encryption, per-tenant rate limits, and per-tenant sandbox pools, and is a separate ADR when required.

## Alternatives Considered

- **Flat permissions with no roles** — Rejected: unmanageable in practice; every principal becomes a hand-maintained permission list.
- **Full ABAC / policy engine (OPA, Cedar) from the start** — Powerful and a plausible future step; rejected as premature. It adds a policy language and evaluation service before the requirements that justify them exist. The permission vocabulary is deliberately designed so an external policy engine can be adopted later behind the existing authorization interface.
- **Agents as first-class authenticating principals with their own credentials** — Rejected: it would let an agent hold authority independent of the workflow that invoked it, breaking the narrowing rule and creating credentials that a compromised agent could exfiltrate.
- **Multi-tenancy in v1** — Rejected as scope that would substantially delay the core product without a current requirement.

## Consequences

### Positive
- Least privilege becomes computable and testable rather than aspirational.
- A compromised or injected agent cannot exceed the authority of its workflow.
- Role assignment is manageable and auditable.

### Negative
- Workflow authors must declare the permissions their workflows need; under-declaration surfaces as a runtime denial (with a clear error naming the missing permission).
- The closed permission vocabulary requires an SDK change to extend — deliberate friction.

### Neutral
- Single-tenancy is a documented limitation rather than an unexamined assumption.

## Compliance

Complies with the Constitution (Article 6: Least Privilege, Secure Defaults) and the AI Governance Framework (Least Authority).

## References

- `docs/09_security/authentication_authorization.md`
- `docs/03_architecture/capability_framework/manifest_schema.md`

---

## Implementation Status (appended 2026-07-28, updated 2026-08-07 — not part of the Accepted decision)

**Status in code:** Partially implemented

**Updated 2026-08-07 (`P07-S02-M14-T01`): the "user | OIDC bearer token" row is now genuinely real, not merely documented.** `security_manager.token_verifier.OidcBearerTokenVerifier` verifies against a real JWKS endpoint (RS256, issuer/audience checked), selected only when a real provider is configured (`PlatformConfig.oidc_issuer`/`oidc_audience`/`oidc_jwks_uri`, all three together) — every current environment, which configures none of them, keeps authenticating bearer JWTs against the **pre-shared signing secret** unchanged, a deliberate, zero-regression choice (see `security_manager.md`'s own Implementation Status for the full detail). The Security Manager still enforces 5 permissions across 9+ HTTP routes, deny-by-default. The decision's substance is partially in force: none of the five roles exist as such (only their permission grants are modelled), agents are not derived principals with a `SecurityContext`, and the monotonic narrowing intersection (principal ∩ workflow ∩ agent ∩ tool) is now computed (`ai_os_kernel.security_manager.narrowing`, `P03-S05-M14-T03`). One real slice of it is enforced end to end: `P02-S05-M13-T08` wired the agent/tool terms to real manifest-sourced data (`catalog.agents`/`catalog.tools.required_permissions` checked against `catalog.packs.manifest`'s own `permissions` at resolution) and refuses an over-granted agent/tool before it ever loads. The principal and workflow terms still have no real data source or wiring — `SecurityContext` is never threaded into resolution, and no code parses a workflow's declared permissions out of a manifest — so the full four-way chain still never runs. Single-tenancy holds trivially, by absence of any tenant concept.

**Update (2026-08-02, `P03-S05-M14-T06`): the `approver` role's own "grantable per class" clause is now real**, the first genuinely class-scoped (not merely flat) role check anywhere in this codebase — `ai_os_kernel.security_manager.approval_authorization.is_authorized_to_decide_approval`, gating `workflow_engine.human_approval.ApprovalService.decide()`.

**Update (2026-08-03, `P03-S05-M14-T07`): role *administration* is now real too, closing the gap the line above disclosed.** `ai_os_kernel.security_manager.role_administration.RoleAdministrationService` grants/revokes a real, persisted `approver:<class>` role for a principal — `admin`-gated (reusing the same `admin` role this ADR's own table already reserves for "role assignment"), every grant/revoke a real, hash-chained `governance.audit_log` row. Persisted grants *augment* a bearer token's own `roles` claim, never replace it: `ApprovalService.decide()` unions active grants into `principal.roles` before the unchanged class-scoped check runs, so a token-only principal's behaviour is unaffected. Proven end to end against real Postgres: a decision refused, then genuinely enabled by a real grant for the identical, unchanged bearer token, then genuinely disabled again by a real revoke.

**Update (2026-08-03, `P03-S05-M14-T08`): role administration is now reachable over real HTTP too — `POST`/`DELETE /api/v1/security/role-grants`**, authenticated the identical way the decide route is (bare `authenticate`, authorization deferred entirely to `RoleAdministrationService`). Proven end to end, real HTTP, real Postgres: an `admin` genuinely grants then revokes a role through the route; a non-admin request to either endpoint is refused with a `403` and makes no real grant.

**Update (2026-08-03, `P03-S05-M14-T09`): the principal term of the monotonic-narrowing intersection is real too now, threaded into the identical agent/tool resolution point `P02-S05-M13-T08` already enforces the pack-grant term at.** `security_manager.narrowing.over_permitted_permissions` reuses the same `intersect_declared_permissions` primitive. Since resolution can happen long after the triggering HTTP request ended (a worker-loop tick has no bearer token at all), a triggering principal's `SecurityContext.permissions` is captured once, at trigger time, into a new, nullable `workflow_instances.principal_permissions` column, and read back at every later step — `NULL` means unenforced, never an empty-set "holds nothing" claim; the one real caller with a live `SecurityContext` (`routes/workflows.py`'s `start_workflow`) now supplies it. Proven end to end against real Postgres: a pack grants both `llm:invoke` and `sandbox:execute` — enough for the pre-existing pack-grant term alone to resolve the agent — but a principal holding only `sandbox:execute` is genuinely refused resolving that identical agent, isolating the principal term as the cause. The workflow term and the full four-way single-call intersection still do not exist.

Live status: [`feature_inventory.md`](../../19_roadmap/feature_inventory.md) · Build history: [`history/INDEX.md`](../../19_roadmap/history/INDEX.md)
