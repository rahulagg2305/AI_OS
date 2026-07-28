# Human Approval Points Framework – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Human Approval Points Framework  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## Implementation Status (2026-07-28)

**Built: nothing functional.** The `workflow.approvals` table exists as schema only (migration `0003`, with the documented six-value `status` CHECK constraint) — **it has no writer and no reader.**

Nothing creates a pending approval when a `human_approval` step is reached: that step type completes as a **no-op** via `NoOpStepExecutor`, so a workflow declaring an approval point runs straight through it. There is no Human Approval Manager, no durable pause/resume, no notification of any channel (the Notification Service is also 0% built), and no decision-recording path.

The invariant that **a timeout never implies approval** ([ADR-0007](../../18_decision_log/adr/ADR-0007-human-governance-for-critical-decisions.md)) is currently satisfied only vacuously — no approval can time out because none is ever created. Outstanding Stage C deliverable.

Authoritative, always-current status: `../../19_roadmap/feature_inventory.md` and `../../19_roadmap/implementation_status.md`. Build history: `../../19_roadmap/history/INDEX.md`.

## 1. Purpose

This document defines the framework for **Human Approval Points** in AI_OS.

Human Approval Points are explicit pauses in a workflow where the system requires a human decision before continuing. They implement the “Human Governance” principle from the Project Constitution and AI Governance Framework.

This document is subordinate to:

1. Project Constitution  
2. AI Governance Framework  
3. Workflow Architecture  
4. Standard Workflow Patterns  

---

## 2. Design Goals

Human Approval Points must:

- Make critical decisions visible and intentional
- Prevent the system from autonomously making irreversible or high-impact choices
- Be clearly defined in workflows
- Support multiple channels for human response (Dashboard, API, Voice/Jarvis, etc.)
- Be fully auditable
- Have clear timeout and escalation behaviour

---

## 3. When Human Approval is Mandatory

The following categories always require human approval (as established in the Governance Framework):

- Final Requirements approval
- Architecture approval
- Production deployment approval
- Major design or scope changes
- Changes to the Project Constitution or Governance rules
- Introduction of new Capability Packs that affect core behaviour
- Any other decision explicitly marked as requiring human governance

Additional approval points may be defined by specific workflows or Capability Packs.

---

## 4. Human Approval Point Contract

Every Human Approval Point must define:

| Field              | Description                                      | Required |
|--------------------|--------------------------------------------------|----------|
| id                 | Unique identifier within the workflow            | Yes      |
| name               | Human-readable name                              | Yes      |
| description        | What decision is being requested                 | Yes      |
| context            | Information the human needs to make the decision | Yes      |
| options            | Allowed decisions (e.g., Approve, Reject, Request Changes) | Yes |
| timeout            | Maximum wait time                                | No       |
| escalationPolicy   | What happens on timeout or repeated rejection    | No       |
| channels           | How the human will be notified                   | No       |

---

## 5. Execution Flow

1. Workflow Engine reaches a Human Approval Point.
2. Workflow state is set to `WaitingForHuman`.
3. Notification is sent through configured channels (Dashboard, email, Voice, etc.).
4. System waits for a valid human response.
5. Upon response:
   - **Approve** → Workflow continues
   - **Reject** → Workflow follows the rejection path (may terminate or compensate)
   - **Request Changes** → Workflow may loop back to an earlier step
6. The decision is recorded permanently in the audit log and workflow history.

---

## 6. Key Design Rules

- Agents may never override or skip a Human Approval Point.
- The Workflow Engine is the only component allowed to resume a workflow after human approval.
- All human decisions must be attributable (who decided, when, and what they decided).
- Timeouts must be handled explicitly; silent continuation is forbidden for mandatory approval points.

---

## 7. Relationship with Other Components

- **Workflow Engine** owns the pause and resume logic.
- **Dashboard** is the primary interface for human interaction.
- **Voice (Jarvis)** may provide an alternative notification and response channel.
- **Security Manager** ensures only authorized humans can approve.
- **Observability / Audit** records every decision.
- **Evaluation Engine** can track how often human intervention was required.

---

## 8. Current Status

This document establishes the baseline framework for Human Approval Points.

Concrete UI/UX designs, notification channel implementations, and timeout policies will be refined during later phases (especially Dashboard and Voice).

---

## 9. Final Authority

Order of precedence:

1. Project Constitution  
2. AI Governance Framework  
3. Workflow Architecture  
4. Human Approval Points Framework  
5. Source Code
