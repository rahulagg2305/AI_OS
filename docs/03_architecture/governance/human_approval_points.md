# Human Approval Points Framework – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Human Approval Points Framework  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## Implementation Status (2026-08-02, `P03-S05-M14-T04`/`T05`)

**A real, minimal Human Approval Manager now exists — the pause/resume core of §5's Execution Flow, genuinely built, not the full framework document.** `workflow.approvals` (migration `0003`) now has both a real writer and a real reader: `ai_os_kernel.workflow_engine.human_approval.SqlApprovalRepository`. A `human_approval` step, when a real `HumanApprovalStepExecutor` is wired in (`DispatchingStepExecutor`'s own `human_approval_executor` — unwired by default, the identical "unconfigured means unaffected" precedent `quality_gate`/`decision`/`parallel`/`sub_workflow` already established), genuinely creates a pending `approvals` row and transitions the real instance to `waiting_for_human` (§5 steps 1–2) — no longer a no-op. The instance stays genuinely, durably paused — proven across repeated real `advance()` attempts, real wall-clock time, and even past a declared `timeout` — until a real, attributable decision (`decide()`, requiring a real, non-empty `principal_id` — §6: "who decided, when, and what") resumes it (`approved`) or halts it (`rejected`, §5 step 5's "may terminate").

**The invariant that a timeout never implies approval ([ADR-0007](../../18_decision_log/adr/ADR-0007-human-governance-for-critical-decisions.md)) is now a real, proven guarantee, not a vacuous one** — a real, Postgres-backed test lets a declared timeout genuinely elapse and confirms the approval is still `pending` and the instance still `waiting_for_human`, real time later.

**Still genuinely partial — a disclosed, product-owner-approved scope, not the full framework.** No HTTP route or Bearer-token authentication exists for submitting a decision (`decide()` is a real, tested, callable service-layer method only — the same "Workflow-Engine-level mechanism first, HTTP/production wiring separate" precedent every other step type this session established); no RBAC/permission check against `security_manager`'s own `approver` role (§9: "approval classes are granted separately" is not enforced — any real, non-empty `principal_id` is accepted); no notification channel of any kind (the Notification Service is still 0% built); no automatic `timed_out`/`cancelled` transition or escalation policy (no reaper job exists yet, mirroring `WorkflowLeaseReaper`'s own earlier, separate step); `changes_requested`'s own "loop back to an earlier step" semantics are undefined anywhere in this document and are not built. See `ai_os_kernel.workflow_engine.human_approval`'s own module docstring for the full reasoning.

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
