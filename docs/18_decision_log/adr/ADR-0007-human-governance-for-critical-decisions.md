# ADR-0007: Human Governance for Critical Decisions

**Status:** Accepted
**Date:** 2026-07-25
**Decision Makers:** Chief Architect, Project Owner
**Related Documents:** `docs/03_architecture/governance/human_approval_points.md`, `docs/00_constitution/ai_governance_framework.md`

---

## Context

AI_OS is designed to act autonomously over real repositories, real infrastructure, and real releases. Some of those actions are irreversible or carry consequences the platform cannot evaluate — cost, compliance, business risk, reputational risk. Autonomy must therefore stop at a defined line rather than at the model's own discretion.

## Decision

A defined set of decisions requires explicit human approval before the platform may proceed: final requirements approval, architecture approval, production deployment, production schema changes, breaking API changes, security policy changes, repository restructuring, changes to the Constitution or Governance Framework, and activation of a Capability Pack that alters platform behaviour.

Mechanically:
- Human Approval Points are declared in workflow definitions and enforced by the Workflow Engine.
- The workflow enters `WaitingForHuman` and persists; it does not poll, spin, or proceed.
- **Timeout never implies approval.** A timeout follows the declared escalation policy or fails the workflow.
- Every decision is attributable: principal, decision, timestamp, and the context shown at decision time are recorded in the audit log.
- Only an authenticated principal holding the `approver` role for that approval class may approve ([ADR-0023](ADR-0023-identity-roles-and-permissions.md)).
- No agent may approve, skip, or override an approval point, and no LLM output can grant approval authority.

## Alternatives Considered

- **Full autonomy with post-hoc audit** — Rejected: irreversible actions cannot be un-done by an audit trail.
- **Human approval on every step** — Rejected: destroys the platform's purpose and induces rubber-stamping, which is worse than no gate because it manufactures false assurance.
- **Confidence-threshold-based auto-approval** — Rejected: self-reported model confidence is not calibrated and is exactly the wrong signal to delegate irreversibility to.

## Consequences

### Positive
- Irreversible actions always have an accountable human decision behind them.
- Approval latency is visible and measurable, so governance cost can be managed with evidence.

### Negative
- Long-running workflows block on human availability; mitigated by durable state, multi-channel notification, and escalation policy.

### Neutral
- Approvals are reachable from Dashboard, API, CLI, and Voice; the channel does not change authorization ([ADR-0014](ADR-0014-api-style-and-realtime-transport.md)).

## Compliance

Complies with the Project Constitution (Human Governance) and the AI Governance Framework (Human Approval Points).

## References

- `docs/13_dashboard/information_architecture.md`
- `docs/09_security/authentication_authorization.md`
