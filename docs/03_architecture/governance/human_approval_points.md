# Human Approval Points Framework – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Human Approval Points Framework  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## Implementation Status (2026-08-03, `P03-S05-M14-T08`)

**§7's "Security Manager ensures only authorized humans can approve" is now real (`P03-S05-M14-T06`).** Before this step, `decide()` proved only *attribution* (a real, non-empty `principal_id`) — genuinely anyone could decide anything. `workflow_engine.human_approval.ApprovalService` now sits in front of it and enforces ADR-0023's own documented per-class `approver` grant (`security_manager.approval_authorization.is_authorized_to_decide_approval`): a principal must hold `admin` or the exact `approver:<approval_class>` role (`approval_class` = the point's own `id`, per T04/T05's own reuse) before a decision is even attempted — an unauthorized attempt never reaches the database, proven both with fakes and against a real Postgres row (the approval stays exactly `pending`).

**Updated (`P03-S05-M14-T07`): role *administration* is now real too, closing the gap this section itself used to name.** `security_manager.role_administration.RoleAdministrationService` (`admin`-gated, audited via `governance.audit_log`) grants/revokes a real, persisted `approver:<class>` role for a principal; `ApprovalService.decide()` unions real, active grants into `principal.roles` before the unchanged class-scoped check above runs, so a token-only principal's behaviour is unaffected. Proven end to end, real Postgres: a decision refused, then genuinely enabled by a real grant for the identical bearer token, then genuinely disabled again by a real revoke.

**Updated (`P03-S05-M14-T08`): role administration is now reachable over real HTTP too — `POST`/`DELETE /api/v1/security/role-grants`.** The last open item in this thread — the RBAC mechanism above is now administrable end to end, not only through direct service-layer calls, closing the Human Approval RBAC work started in T04/T05/T06.

**Updated (`P03-S03-M30-T06`): a real HTTP route/Bearer-token wiring for this call site now exists too — `POST /api/v1/workflows/{workflow_id}/approvals/{approval_id}/decisions`.** Real Bearer/JWT authentication (`security_manager.authenticate`, unchanged mechanism), zero flat permission check — a first version tried one and found it genuinely incompatible with §7's own per-class model (see `security_manager.md`'s own updated Implementation Status for the concrete failure), so the full authorization decision is deferred entirely to `ApprovalService`, already correct. Resumption is real too, for the one real workflow that can pause today (`se.delivery_pipeline`): the route calls `workflow_engine.delivery_pipeline.resume_pipeline_after_approval` synchronously, the identical one-shot-HTTP-call shape the pipeline's own trigger route already uses — proven end to end, real Postgres, real HTTP, a real paused instance resuming through a real, authorized decision to a real commit and push. The generic multi-instance worker loop is deliberately *not* the resumption mechanism (investigated: its own fixed composition cannot correctly execute `se.delivery_pipeline`'s `quality_gate`/`decision`/`human_approval` steps at all) — `se.delivery_pipeline` is now excluded from that loop's own discovery entirely, closing a real race the investigation surfaced (the loop could otherwise rediscover a just-resumed instance and mis-advance it with the wrong composition before the route's own correct resume ran).

**A real, minimal Human Approval Manager now exists — the pause/resume core of §5's Execution Flow, genuinely built, not the full framework document.** `workflow.approvals` (migration `0003`) now has both a real writer and a real reader: `ai_os_kernel.workflow_engine.human_approval.SqlApprovalRepository`. A `human_approval` step, when a real `HumanApprovalStepExecutor` is wired in (`DispatchingStepExecutor`'s own `human_approval_executor` — unwired by default, the identical "unconfigured means unaffected" precedent `quality_gate`/`decision`/`parallel`/`sub_workflow` already established), genuinely creates a pending `approvals` row and transitions the real instance to `waiting_for_human` (§5 steps 1–2) — no longer a no-op. The instance stays genuinely, durably paused — proven across repeated real `advance()` attempts, real wall-clock time, and even past a declared `timeout` — until a real, attributable decision (`decide()`, requiring a real, non-empty `principal_id` — §6: "who decided, when, and what") resumes it (`approved`) or halts it (`rejected`, §5 step 5's "may terminate").

**The invariant that a timeout never implies approval ([ADR-0007](../../18_decision_log/adr/ADR-0007-human-governance-for-critical-decisions.md)) is now a real, proven guarantee, not a vacuous one** — a real, Postgres-backed test lets a declared timeout genuinely elapse and confirms the approval is still `pending` and the instance still `waiting_for_human`, real time later.

**Still genuinely partial — a disclosed, product-owner-approved scope, not the full framework.** RBAC (`security_architecture.md` §9: "approval classes are granted separately") is now enforced, and role *administration* (granting a real principal an `approver:<class>` role in the first place) is now real too (see above); no notification channel of any kind (the Notification Service is still 0% built); no automatic `timed_out`/`cancelled` transition or escalation policy (no reaper job exists yet, mirroring `WorkflowLeaseReaper`'s own earlier, separate step); `changes_requested`'s own "loop back to an earlier step" semantics are undefined anywhere in this document and are not built. **Closed 2026-08-10 (`P06-S03-M39-T02`): the "no way to list approvals at all" gap this line found is now real.** `ApprovalRepository` gained `list_pending()` — every real, currently `pending` row, oldest-`requested_at`-first; `routes/approvals.py` gained `GET /api/v1/approvals` (api_architecture.md §6.2), gated by a new, real `approval:read` permission granted only to `approver`/`admin` (the only two roles §4.2's own role table mentions approvals for at all). The Dashboard's own Pending Approvals view (`dashboard/src/views/PendingApprovalsList.tsx`) is this route's first real consumer, and also genuinely *decides* through the existing `POST .../decisions` route — closing FR-092's own full acceptance criterion ("An approval is decided from the Dashboard and the workflow resumes"), not only the read half. `GET /approvals/{id}` (detail) and `GET /approvals/history` remain genuinely not built — a caller must still already know a `(workflow_id, step_id)` or `approval_id` to read a *specific* approval's own full context; only "what is pending right now" is answerable today.

Authoritative, always-current status: `../../19_roadmap/feature_inventory.md`. Build history: `../../19_roadmap/history/INDEX.md`.

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
