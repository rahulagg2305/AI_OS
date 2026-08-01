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

## Implementation Status (appended 2026-07-28 — not part of the Accepted decision)

**Status in code:** Partially implemented

The Security Manager authenticates bearer JWTs against a **pre-shared signing secret, not OIDC**, and enforces 5 permissions across 9+ HTTP routes, deny-by-default. The decision's substance is partially in force: none of the five roles exist as such (only their permission grants are modelled), agents are not derived principals with a `SecurityContext`, and the monotonic narrowing intersection (principal ∩ workflow ∩ agent ∩ tool) is now computed (`ai_os_kernel.security_manager.narrowing`, `P03-S05-M14-T03`) but not yet enforced end to end — no code parses a workflow's/agent's/tool's declared permissions out of a manifest, so the computation has no real data to run against during an actual invocation. Single-tenancy holds trivially, by absence of any tenant concept.

Live status: [`feature_inventory.md`](../../19_roadmap/feature_inventory.md) · Build history: [`history/INDEX.md`](../../19_roadmap/history/INDEX.md)
