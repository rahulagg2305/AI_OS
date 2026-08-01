# Security Architecture – AI_OS

**Project:** AI_OS (AI Operating System)
**Document:** Security Architecture
**Version:** 1.1
**Status:** Approved
**Last Updated:** 2026-07-28 (§5.1: cross-referenced the real implementation's `SandboxExecutor` name against this table's own `SandboxRuntime` — no other content changed)

---

## 1. Purpose

This document defines the AI_OS threat model and the controls that address it. It is the authoritative security document; `authentication_authorization.md` and `secrets_management.md` are subordinate detail.

AI_OS has an unusual risk profile that must be stated plainly: **it generates code and then executes it, against repositories it did not write, with credentials that can push to production.** Every control below exists because of that sentence.

Governing decisions: [ADR-0016](../18_decision_log/adr/ADR-0016-tool-execution-sandboxing.md), [ADR-0023](../18_decision_log/adr/ADR-0023-identity-roles-and-permissions.md), [ADR-0024](../18_decision_log/adr/ADR-0024-secrets-management-backend.md).

This document is subordinate to:

1. Project Constitution (Article 6)
2. AI Governance Framework
3. System Architecture

---

## Implementation Status (2026-07-28)

**Real, verified against source:** the Tier 1/Tier 2 sandbox split (§5) — `SandboxExecutor`, network-disabled containers, non-root, capability-dropped, per ADR-0016; per-workflow workspace isolation (§5.3); the hash-chained, `UPDATE`/`DELETE`-revoked `governance.audit_log` (§12, migration `0004_governance_audit_log`); the `SecretValue` wrapper and `secret://` reference format (§7); `StepBudget`/`BudgetExceededError` cost ceilings in the LLM Gateway (§13); `ruff`'s `S` (security) rule set, `pip-audit --strict`, and `gitleaks/gitleaks-action` all genuinely wired into `.github/workflows/ci.yml` (§15).

**Not real, despite being stated as mitigated controls:**
- **Updated (2026-08-01, `P03-S05-M14-T03` + `P02-S05-M13-T08`): §9's monotonic-narrowing intersection (T5's primary control) is real and tested; one real, narrower slice of it is now enforced.** `security_manager.narrowing.narrow_permissions` computes the exact principal ∩ workflow ∩ agent ∩ tool formula. `SqlAgentRegistry.resolve_agent`/`SqlToolRegistry.resolve_tool` now reuse that same primitive to refuse resolving an agent/tool whose own manifest-declared `required_permissions` exceed its pack's own manifest-declared `permissions` — a real, enforced ceiling, checked before any entrypoint is loaded. This is the pack-grant term only, not the full chain: `SecurityContext` (the principal term) is still never threaded into resolution at all, and no code reads a *workflow's* declared permissions from a manifest. See `authentication_authorization.md`'s own Implementation Status for the full detail. T5 is therefore still only partially mitigated, not resolved as §4's table implies.
- **Resolved (2026-08-01, `P01-S06-M42-T04`): `tests/security/` now holds one test file per threat (T1–T12), 30 tests total, each exercising that threat's real, current defense against a genuine attempt.** For T10 (no approval-decision enforcement exists) and T11 (no Git Integration Service exists), the tests are disclosed absence-of-capability tripwires, not positive-control proofs — see that ticket's own report for the honest split.
- **Resolved: §8 point 3's "contract suite verifies no forbidden imports" is real.** `ai_os_sdk.testing.forbidden_imports.scan_pack_source` (Platform SDK) is a genuine AST import-scanner, CI-wired via `pack_contract_suite` check 7, confirmed by this session's own `tests/security/test_t4_pack_security.py`.
- **§14 Git Safety has no enforcing component.** No Git Integration Service, and no `git.*` tool (`git.create_pull_request`, `git.clone_or_fetch`, etc.) exists anywhere in the Kernel or the Software Engineering pack. The force-push prohibition, protected-branch policy, and mutating-operation audit trail this section describes have nothing to enforce them yet — T11 is entirely unmitigated in code, though no workflow currently performs a Git write either, so the exposure is latent rather than active.
- **Secrets backend (§7, detailed in `secrets_management.md`): only the `env` backend exists**, not the four this document's threat table assumes are interchangeable.
- **§6's provenance tagging (T2's #2 primary control) does not exist.** `context_manager/models.py`'s `ContextItem`/`SourceRef` has no `trust` field at all — only `source_type` (an enum with exactly one real value, `workflow_state`) and `identifier`. There is no `trusted`/`untrusted` label anywhere in the Context Manager today. This is lower-risk than it sounds only because no ingestion resolver exists yet either (`KNOWLEDGE`, `AI_CONTEXT_PACK`, and the others are explicitly not built, per that enum's own comment) — so no untrusted content currently reaches an agent's context to be mislabeled. The moment a repository- or document-ingesting resolver is built, this becomes a real, live gap, not a latent one.

Authoritative, always-current status: `../19_roadmap/feature_inventory.md` and `../19_roadmap/implementation_status.md`.

---

## 2. Assets

| Asset | Why it matters |
|---|---|
| Provider API keys | Direct financial loss; access to the organisation's model quota |
| Git credentials | Write access to source repositories, including production branches |
| Customer source code | Confidentiality; may be third-party or under NDA |
| Workflow state and audit log | Integrity of the governance record |
| Deployment credentials | Production impact |
| The platform host | Pivot point to the wider network |
| Generated artifacts | Supply-chain integrity of what AI_OS ships |

---

## 3. Trust Boundaries

```text
┌─────────────────────────────────────────────────────────────┐
│ UNTRUSTED                                                   │
│  LLM output · ingested repositories · third-party docs      │
│  web content · tool stdout/stderr                           │
└───────────────────────────┬─────────────────────────────────┘
                            │  provenance-tagged, delimited,
                            │  schema-validated, no authority
┌───────────────────────────▼─────────────────────────────────┐
│ SANDBOX (Tier 1) — ephemeral container                      │
│  no network · read-only root · non-root · caps dropped      │
│  no secrets · no host mounts · no Docker socket             │
└───────────────────────────┬─────────────────────────────────┘
                            │  ToolResult only (structured)
┌───────────────────────────▼─────────────────────────────────┐
│ PLATFORM (Tier 2, trusted)                                  │
│  Kernel · Services · Packs · workspace-scoped file access   │
└───────────────────────────┬─────────────────────────────────┘
                            │  secret:// references
┌───────────────────────────▼─────────────────────────────────┐
│ CREDENTIAL PLANE — Vault / cloud secret manager             │
│  Never reachable from the sandbox                           │
└─────────────────────────────────────────────────────────────┘
```

The single most important property: **the sandbox has no route to the credential plane.** Operations needing credentials are performed by platform services that expose the *operation* and withhold the *credential*.

---

## 4. Threat Model

Threats are numbered for traceability from tests and reviews.

| # | Threat | Impact | Primary controls |
|---|---|---|---|
| T1 | Generated code executes hostile actions (delete, exfiltrate, mine, scan) | Host compromise, data loss | §5 Tier 1 sandbox: no network, dropped caps, non-root, read-only root, resource limits |
| T2 | Prompt injection via ingested repository content or documents | Agent performs attacker-directed actions | §6 provenance tagging, delimited framing, **authority never from content**, output schema validation, approval gates |
| T3 | Secret exfiltration through generated code or logs | Credential compromise | §7 secrets never in sandbox, `SecretValue` wrapper, log redaction, prompt scanning |
| T4 | Malicious or compromised Capability Pack | Platform compromise | §8 manifest validation, closed permission vocabulary, forbidden-import checks, human approval for behaviour-affecting activation |
| T5 | Privilege escalation across the invocation chain | Unauthorized actions | §9 monotonic narrowing, deny by default, no runtime elevation |
| T6 | Supply-chain compromise of a dependency | Arbitrary code in the platform | §10 lockfile, `pip-audit`, pinned base images, provenance for generated artifacts |
| T7 | Data exfiltration to a model provider | Confidentiality breach | §11 context minimisation, secret scanning before send, provider allowlist, no-training contractual requirement |
| T8 | Audit log tampering to hide an action | Loss of accountability | §12 hash chaining, revoked `UPDATE`/`DELETE`, offsite backup, verification job |
| T9 | Resource exhaustion (runaway loop, fork bomb, token spend) | Denial of service, cost blowout | §13 bounded loops, budgets enforced in the Gateway, container limits, rate limits |
| T10 | Unauthorized approval of a governance decision | Ungoverned irreversible action | §9 approval classes, attributable decisions, timeout never approves |
| T11 | Git history or branch destruction | Loss of customer work | §14 force-push prohibited, protected-branch policy, approval before push |
| T12 | Cross-workflow interference via a shared workspace | Corrupted output, data leak between projects | §5 mandatory per-workflow workspace isolation |

**Out of scope for v1**, stated so the gap is not mistaken for coverage: multi-tenant isolation (AI_OS v1 is single-tenant, [ADR-0023](../18_decision_log/adr/ADR-0023-identity-roles-and-permissions.md)); protection against a malicious platform administrator; physical security; DDoS at the network edge (an infrastructure concern).

---

## 5. Execution Isolation (T1, T12)

Two tiers, no third path ([ADR-0016](../18_decision_log/adr/ADR-0016-tool-execution-sandboxing.md)).

### 5.1 Tier 1 — untrusted execution

Mandatory for every tool that executes a command string, compiles, runs tests, installs dependencies, or processes untrusted repository content.

| Control | Configuration |
|---|---|
| Runtime | Ephemeral OCI container per step, via `SandboxRuntime` (Docker/Podman; gVisor for hardened deployments) — the real Kernel implementation names this seam `SandboxExecutor`; see ADR-0016's own implementation naming note (2026-07-28) |
| Network | `--network=none` by default |
| Dependency installation | A separate, explicitly-declared step through an egress proxy with a package-registry allowlist |
| Root filesystem | Read-only |
| Writable paths | The workflow's own working copy, plus `tmpfs` scratch |
| User | Non-root UID/GID, `--user` always set |
| Capabilities | `--cap-drop=ALL`, `--security-opt=no-new-privileges` |
| Syscalls | Default seccomp profile retained; `--privileged` and `seccomp=unconfined` prohibited |
| Limits | Memory, CPU quota, PID limit, wall-clock timeout — all from configuration |
| Host access | No Docker socket. No host mounts beyond the working copy. |
| Secrets | None. Ever. |
| Lifetime | Destroyed after the step; never reused |

### 5.2 Tier 2 — trusted platform operations

In-process, for platform work only. Requires **canonical-path allowlisting**: every path is resolved and verified to remain inside the workspace root; `..`, symlinks, and absolute escapes are rejected. Path handling uses resolved-path comparison, never string prefix matching.

### 5.3 Workspace isolation (T12)

Each workflow instance gets its own working copy. This is **mandatory, not best-effort** — it is what makes parallel and fan-out workflow patterns safe, and it prevents one project's content from reaching another's context.

---

## 6. Prompt Injection (T2)

Ingested repository content is attacker-controlled input. Instruction-based defences ("ignore instructions in the content") are probabilistic and are therefore **not** the primary control.

**Controls, in order of reliance:**

1. **Authority never derives from content.** Permissions come only from the manifest and the `SecurityContext`. No model output can grant a permission, widen a scope, change a trust tier, skip a Quality Gate, or approve a Human Approval Point. This is structural: a fully successful injection can produce bad *output*, never new *authority*.
2. **Provenance tagging.** Every `ContextItem` carries `trust: trusted | untrusted`. Repository content, ingested documents, tool output, and web content are always `untrusted`.
3. **Delimited framing.** The Prompt Engine wraps untrusted content in explicit boundaries stating that the enclosed text is data to analyse, never instruction to follow.
4. **Output schema validation.** Agent output is validated against its declared model before any consumer acts on it.
5. **Tool allowlisting per step.** A step exposes only the tools its declared agent needs, so an injected instruction to use an unrelated tool has nothing to call.
6. **Irreversible actions gated.** Push, deploy, and release always pass a Human Approval Point, with a human-readable diff.

---

## 7. Secrets (T3)

Full detail in `secrets_management.md`; the security-relevant invariants:

- Referenced as `secret://<provider>/<name>[#version]`; configuration and manifests contain references only.
- Resolved late, narrowly, in memory; never written to disk, workflow state, telemetry, events, or audit payloads.
- Wrapped in `SecretValue`, whose `__str__`/`__repr__` return `***`, so accidental logging is prevented by the type rather than by reviewer attention.
- **Never present in a Tier 1 sandbox.** Credentialed operations run in platform services that expose a capability, not a credential.
- Prompt assembly rejects content matching a resolved secret value, as defence in depth against a secret reaching a provider.
- Rotation is supported without restart; access is audited by name.

---

## 8. Capability Pack Security (T4)

A pack is code running inside the platform, so it is treated as a supply-chain risk:

1. Manifest validated against the published JSON Schema before anything is imported.
2. Requested permissions must be in the closed vocabulary; unknown permissions fail validation.
3. The contract suite verifies **no forbidden imports**: no provider SDK, no `ai_os_kernel`, no other pack, no database driver.
4. Declared components must match implementations exactly; a mismatch fails activation.
5. Tool `trust_tier` declarations are validated against what the tool does.
6. Activation of a pack that affects platform behaviour requires human approval.
7. Deactivation must be clean; dangling registrations fail the check.

**Manifest signing is not implemented in v1.** This is a known gap, recorded here rather than in a "future enhancements" list: until signing exists, pack provenance is enforced by controlling the install path (packs come from the repository or an internal index, not arbitrary URLs) and by human-approved activation.

---

## 9. Identity and Authorization (T5, T10)

Per [ADR-0023](../18_decision_log/adr/ADR-0023-identity-roles-and-permissions.md):

- Principals: `user` (OIDC), `service_account` (API key/client credentials), `agent` (never authenticates; derives authority from its workflow).
- Roles: `viewer`, `operator`, `approver` (per class), `maintainer`, `admin`.
- **Monotonic narrowing:** `principal ∩ workflow ∩ agent ∩ tool = effective`. Authority only shrinks. There is no runtime elevation path.
- Deny by default; absence of a permission is denial.
- Approval classes are granted separately, so an operator who may approve a release does not thereby approve architecture.
- Every authentication failure, authorization denial, and approval decision is audited with the principal identity.

---

## 10. Supply Chain (T6)

| Control | Detail |
|---|---|
| Dependency pinning | `uv.lock` committed; `uv sync --frozen` in CI and image builds |
| Vulnerability scanning | `pip-audit` in CI, gating on high/critical |
| Base images | Pinned by digest, rebuilt on a schedule |
| Secret scanning | `gitleaks` in CI |
| Generated artifacts | Recorded with the producing workflow ID, model, prompt versions, and content hash, so anything AI_OS ships is attributable |
| Sandbox images | Minimal, pinned by digest, no build tools beyond what the language toolchain needs |

---

## 11. Data Handling and Provider Egress (T7)

- **Minimisation.** The Context Manager sends the minimum context required for the step; it does not attach whole repositories.
- **Secret scanning before send** (§7).
- **Provider allowlist.** Only configured providers may be routed to; an unlisted provider cannot be reached even if configured elsewhere.
- **Retention and training.** Providers used in production must be under an agreement prohibiting training on submitted data; this is a procurement control and is recorded per provider in configuration.
- **Prompt content is not logged.** Prompt IDs and versions are; bodies containing customer source are not.
- **Ingested repository content** is stored in the platform's own storage and is subject to the platform's retention policy, not retained indefinitely by default.

---

## 12. Audit Integrity (T8)

- Append-only `audit_log` in PostgreSQL; each row includes the SHA-256 of the previous row's canonical form ([ADR-0017](../18_decision_log/adr/ADR-0017-observability-stack.md)).
- `UPDATE` and `DELETE` revoked for the application role.
- A scheduled verification job walks the chain and alerts on a break.
- Audited events: authentication outcomes, authorization denials, approval decisions, secret access (by name), configuration changes, pack lifecycle transitions, Tier 1 executions, and all Git write operations.
- Audit records go to the database, **not** through the sampled telemetry pipeline.

---

## 13. Resource and Cost Controls (T9)

| Control | Enforced by |
|---|---|
| Bounded loops | Workflow definitions declare maximum iterations and fan-out ([ADR-0021](../18_decision_log/adr/ADR-0021-declarative-workflows-no-dynamic-task-planner.md)) |
| Token and cost ceilings | `StepBudget` enforced by the LLM Gateway; exceeding it raises `BudgetExceededError` |
| Container limits | Memory, CPU, PIDs, wall clock per Tier 1 step |
| Concurrency limits | Max concurrent workflows and max concurrent sandboxes, from configuration |
| API rate limits | Per-principal token bucket |
| Alerting | Cost-anomaly alerts on spend rate |

---

## 14. Git Safety (T11)

- Credentials live in the Git Integration Service, never in the sandbox.
- `push --force`, `push --force-with-lease` to protected branches, branch deletion, and history rewriting are **prohibited operations** — not gated, not configurable-on, absent from the tool surface.
- All pushes target a feature branch; integration to a protected branch happens through a pull request.
- Every mutating Git operation is audited with actor, repository, branch, and commit range.
- Working copies are per-workflow and discarded after use.

---

## 15. Secure Development Requirements

- `ruff` security rules (`S`) enforced in CI.
- No `eval`, `exec`, `pickle` on untrusted input, `shell=True`, or string-built SQL. All SQL uses parameter binding.
- All external input validated by Pydantic at the boundary.
- Security-relevant changes require human review ([ADR-0007](../18_decision_log/adr/ADR-0007-human-governance-for-critical-decisions.md)).
- Tests exist for each numbered threat's primary control; `tests/security/` is organised by threat ID so coverage of this model is visible.

---

## 16. Incident Response

1. **Detect** — alerts on authorization-denial spikes, audit-chain breaks, cost anomalies, sandbox escapes attempts, unexpected egress.
2. **Contain** — revoke the affected credential, deactivate the implicated pack, halt workflows via `workflow:control`.
3. **Assess** — reconstruct from the audit log and workflow event log ([ADR-0011](../18_decision_log/adr/ADR-0011-persistence-and-workflow-state.md)).
4. **Remediate** — rotate secrets, patch, and add a regression test for the specific failure.
5. **Record** — write an incident record and, where the architecture is implicated, an ADR.

Runbook detail: `../12_operations/operations_runbook.md`.

---

## 17. Current Status

This document establishes the security architecture and threat model for v1. Known accepted gaps, as originally recorded: manifest signing (§8), multi-tenant isolation (§4), and gVisor as a non-default sandbox runtime (§5.1). Each is recorded in the Decision Log's open decision points with a trigger for revisiting.

**As of 2026-07-28, four further gaps were found during verification against source** (see Implementation Status near the top) that are not yet in that accepted-gaps list because they were not previously known: the monotonic-narrowing chain only computes the principal term (T5 partially mitigated, not resolved); `tests/security/` is empty despite §15's claim of per-threat coverage; no forbidden-import contract suite exists (T4's control #3 aspirational); no Git Integration Service or `git.*` tool exists (T11 unmitigated in code, currently latent since no workflow performs a Git write); and the Context Manager has no `trust` field at all (T2's provenance-tagging control does not exist, currently latent since no untrusted-content resolver is built either). These should be added to this document's own accepted-gaps list and the Decision Log's open decision points in a future step — this audit step is docs-only and does not itself edit the Decision Log.

---

## 18. Final Authority

Order of precedence:

1. Project Constitution
2. AI Governance Framework
3. System Architecture
4. Architecture Decision Records
5. Security Architecture (this document)
6. Authentication & Authorization / Secrets Management
7. Source Code

---

## 19. Related Documents

- [`authentication_authorization.md`](authentication_authorization.md) — the §9 monotonic-narrowing detail, including the module docstring disclosing the real gap
- [`secrets_management.md`](secrets_management.md) — the §7 secrets detail, including the real single-backend status
- [`../03_architecture/kernel/context_manager.md`](../03_architecture/kernel/context_manager.md) — the §6 provenance-tagging component, with no `trust` field yet
- [`../03_architecture/capability_framework/capability_pack_contract.md`](../03_architecture/capability_framework/capability_pack_contract.md) — the Platform SDK gate underlying the missing §8 contract suite
- [ADR-0016](../18_decision_log/adr/ADR-0016-tool-execution-sandboxing.md) · [ADR-0023](../18_decision_log/adr/ADR-0023-identity-roles-and-permissions.md) · [ADR-0024](../18_decision_log/adr/ADR-0024-secrets-management-backend.md) — the three decisions this document implements
- [`../19_roadmap/feature_inventory.md`](../19_roadmap/feature_inventory.md) · [`../19_roadmap/implementation_status.md`](../19_roadmap/implementation_status.md) — live build status
