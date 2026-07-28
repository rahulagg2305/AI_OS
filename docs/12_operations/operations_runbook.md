# Operations Runbook – AI_OS

**Project:** AI_OS (AI Operating System)
**Document:** Operations Runbook
**Version:** 1.0
**Status:** Approved
**Last Updated:** 2026-07-25

---

## 1. Purpose

Day-to-day operation of AI_OS: what to watch, what the alerts mean, and what to do when they fire. Written to be actionable at 3 a.m. by someone who did not build the system.

---

## 2. Service Level Objectives

From `../02_requirements/non_functional/nfr.md`:

| SLO | Target | Alert threshold |
|---|---|---|
| API read availability | 99.5 % monthly | Error rate > 1 % over 5 min |
| API read latency p95 | 200 ms | > 400 ms over 10 min |
| Workflow step platform overhead p95 | 500 ms | > 1.5 s over 10 min |
| Workflow success rate | ≥ 95 % excluding intentional rejections | < 90 % over 1 h |
| Outbox relay lag p95 | ≤ 5 s | > 5 s over 10 min (also the ADR-0012 trigger) |
| Cost rate | — | Hourly spend > 3× trailing 7-day hourly mean |
| Audit chain | Verified daily | Any break — immediate |

---

## 3. Dashboards

| Dashboard | Answers |
|---|---|
| Platform Overview | Is it up? What is running? What is waiting on a human? |
| Workflow Operations | Which workflows are running, stuck, failing, retrying? |
| LLM Usage & Cost | Where is money going, by model, workflow, agent, pack? Cache hit rate? |
| Quality Gates | Which gates fail most? Trend over time? |
| Agent Performance | Invocations, success rate, latency, token use per agent |
| System Health | Kernel components, pack health, Postgres, Redis, sandbox pool |
| Security | Auth failures, authorization denials, sandbox executions, secret access |

Dashboards are defined as code in `infra/grafana/` so they are reviewed and versioned like anything else.

---

## 4. Alert Runbooks

Each alert names its likely causes and first actions. The general rule: **capture the `trace_id` before changing anything**, because most of these are diagnosable from one trace.

### A1 — API error rate elevated

*Likely:* database connection saturation; a bad deploy; provider outage surfacing as 500s.
1. Check `/api/v1/health/detail` for component status.
2. Check Postgres connection count and pool saturation.
3. Group errors by `error_code` — a single dominant code points straight at the cause.
4. If it began within 15 minutes of a deploy, roll back (§7).

### A2 — Workflows stuck in `running`

*Likely:* worker died without releasing a lease; a step exceeding its timeout; sandbox pool exhausted.
1. Query stale leases: leases whose `expires_at` has passed with no heartbeat.
2. Confirm worker replicas are alive and heartbeating.
3. Check the sandbox pool for saturation (NFR-004: 20 concurrent).
4. Expired leases are reclaimed automatically; if they are not, the relay or worker loop is wedged — restart the affected worker, which is safe because state is durable.

### A3 — Workflows stuck in `waiting_for_human`

*Not a fault.* This is the platform working as designed.
1. Check pending approvals and their age.
2. Verify notifications were delivered (`Notification` delivery status).
3. If an approval has passed its timeout, the escalation policy should have fired; if it has not, that is a genuine defect — a timeout must never silently do nothing.

### A4 — Cost anomaly

1. Open LLM Usage & Cost, group by workflow and agent to find the source.
2. Look for a loop: repeated identical steps with the same `step_name` and rising `attempt`.
3. Check whether prompt-cache hit rate collapsed (NFR-043) — a prefix-stability regression can multiply input cost without any behaviour change, and is easy to miss.
4. Contain: cancel the offending workflow (`workflow:control`), or lower the budget ceiling in configuration.
5. Then find the cause; do not just raise the budget.

### A5 — Provider errors or outage

1. Confirm which provider from `evaluation.llm_calls` group-by-provider.
2. Verify fallback engaged (`fallback_used = true`). If it did not, the alias fallback chain is misconfigured.
3. If all providers in a chain are failing, reduce concurrency rather than letting retries amplify the outage.

### A6 — Quality gate failure spike

1. Identify the gate and whether the spike is one workflow or many.
2. If one: likely a genuine defect in generated output. Inspect findings.
3. If many, starting suddenly: suspect the *gate*, not the output — a toolchain update, a threshold change, or a missing dependency in the sandbox image.
4. Do **not** lower a threshold to clear an alert. Threshold changes are configuration changes and are audited.

### A7 — Audit chain break

**Treat as Sev-1.**
1. Do not modify the audit table.
2. Identify the sequence number where verification failed.
3. Compare against the offsite export to determine whether rows were altered or deleted.
4. Preserve evidence; begin incident response (§8). A break means either a database-level compromise or a defect in the chain writer — both are serious.

### A8 — Sandbox failures

1. Distinguish *escape attempt* (Sev-1) from *resource limit hit* (usually normal).
2. Resource limits: check whether the step's work genuinely needs more, or is looping.
3. Image pull failures: check the sandbox image digest is present on nodes.
4. Any evidence of containment failure: halt Tier 1 execution platform-wide via the feature flag, then investigate.

### A9 — Postgres saturation

1. Check connections, slow queries, index bloat, replication lag.
2. Common cause at this scale: vector index queries competing with transactional load ([ADR-0013](../18_decision_log/adr/ADR-0013-search-and-vector-store.md)). If confirmed, move reads to a replica; if persistent, that is the trigger for a dedicated vector store.
3. Check whether `workflow_events` has grown past the archival window (§6).

### A10 — Readiness failing but liveness passing

Working as intended: a dependency is unavailable and the pod has been removed from service without being restarted. Fix the dependency; do not restart pods to clear it.

---

## 5. Routine Operations

| Task | Cadence | Notes |
|---|---|---|
| Audit chain verification | Daily, automated | Alerts on break |
| Backup restore rehearsal | Quarterly | To a scratch environment; verify chain + workflow resume |
| Dependency vulnerability review | Weekly | `pip-audit` report |
| Base image rebuild | Monthly, or on CVE | Re-pin digests |
| Secret rotation | Per policy, ≥ quarterly | No restart required (NFR-085) |
| Cost review | Weekly | Per-model, per-pack trend |
| Event log archival | Automated at 180 days | Must preserve replayability |
| NFR re-baselining | Per stage completion | Replace `(baseline)` values with measured ones |
| Capacity review | Monthly | Against NFR scale assumptions |

---

## 6. Data Retention Operations

Per `../08_database/data_model.md`. Retention values are configuration, not code.

| Data | Action at expiry |
|---|---|
| `workflow_events` > 180 days | Export event rows to object storage in replayable form, then prune |
| `llm_calls` > 2 years | Aggregate, then prune detail |
| `audit_log` | **Never pruned** within 7 years; archived only |
| Ingested third-party repository content | Purge per project policy (default 90 days after last use) |
| Idempotency keys > 24 h | Delete |

Archival of `workflow_events` preserves the event rows themselves rather than a summary, because replay is a stated requirement (FR-114).

---

## 7. Deploy and Rollback

**Deploy:** see `../11_deployment/deployment_architecture.md` §9.

**Rollback:**
1. Redeploy the previous image tag.
2. If the release included a **contracting** migration, rollback is **not** safe — apply a forward-fixing migration instead. This is why expand/migrate/contract is mandatory: it keeps rollback available for the window that matters.
3. Verify health, error rate, and one canary workflow.
4. Record the rollback and its cause; if architecture was implicated, write an ADR.

---

## 8. Incident Response

**Severity:**

| Sev | Definition | Response |
|---|---|---|
| 1 | Data loss, security breach, sandbox escape, audit tampering | Immediate; all hands |
| 2 | Platform unavailable, or all workflows failing | Immediate |
| 3 | Degraded performance, one pack failing | Same business day |
| 4 | Cosmetic or single-workflow issue | Scheduled |

**Process:** Detect → Contain → Assess → Remediate → Record.

- **Contain** first, understand second, for Sev-1 and Sev-2. Containment levers: revoke the affected credential, deactivate the implicated pack, halt Tier 1 execution, cancel workflows, scale workers to zero (state is durable, so this loses nothing).
- **Assess** from the workflow event log and the audit log, correlated by `trace_id`.
- **Remediate** with a regression test for the specific failure — no fix ships without one.
- **Record** an incident report; where architecture is implicated, an ADR.

---

## 9. Break-Glass Procedures

| Situation | Procedure |
|---|---|
| Runaway cost | Set the global budget ceiling to zero in configuration; the Gateway refuses new calls immediately. Then cancel workflows. |
| Suspected credential compromise | Rotate at the secret backend; the platform picks up the new value within the cache TTL (default 300 s) — no restart. |
| Malicious pack suspected | Deactivate the pack via `pack:manage`. Running workflows using it fail cleanly rather than being killed mid-write. |
| Sandbox containment doubt | Disable Tier 1 execution via feature flag. All workflows needing it fail fast with a clear error — preferable to running unverified containment. |
| Database emergency read-only | Set the platform to read-only mode; the API serves reads, workers stop leasing. |

Every break-glass action is audited with the acting principal and reason. None of them require editing the database directly — if a situation seems to, that is a gap to be recorded and fixed rather than worked around by hand.

---

## 10. Final Authority

Order of precedence:

1. Project Constitution
2. Architecture Decision Records
3. Deployment Architecture
4. Operations Runbook (this document)
5. Source Code
