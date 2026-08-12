# Git Integration Service – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Git Integration Service  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## Implementation Status (2026-08-02, `P03-S01-M24-T01`/`P03-S04-M31-T04`/`P03-S01-M24-T02`/`P03-S01-M24-T03`)

**Updated (`P03-S01-M24-T03`): a real, dedicated `git:write` permission check now gates Git-tool reachability — closing the exact gap this document's own §5's paragraph two below used to name.** Before this step, `ai_os_kernel.sdk_adapters.pack_context.build_pack_context` forwarded a configured `git_service` into any entrypoint's `ToolInvokerAdapter` whenever that entrypoint declared `sandbox:execute` — meaning every `sandbox:execute` agent in the pack (`lint`, `qa-test`, `build`, `documentation`, not only `git-push`) could reach `platform.git.push` once a real `GitIntegrationService` existed anywhere, regardless of its own manifest permissions. Fixed: `git_service` is now forwarded only when the entrypoint's own declared `permissions` include `git:write` too — the declared-permission term of ADR-0023's monotonic-narrowing chain (`ai_os_kernel.security_manager.narrowing`), the same partial scope `capability_manager.permission_grant.over_granted_permissions` already carries for the pack-ceiling term (no `SecurityContext` reaches this call site to compute the full principal-inclusive chain — a distinct, later SDK Protocol-widening step, not this one). Proven both directions against the identical real `GitIntegrationService`: `git-push`'s own real, declared `[sandbox:execute, git:write]` genuinely commits and pushes (`tests/unit/kernel/sdk_adapters/test_pack_context.py::TestGitWritePermissionGating`); `lint`'s/`qa-test`'s own real, declared `[sandbox:execute]` alone is refused with `UnknownToolError` on every Git tool id, zero audit rows recorded for the attempt.

**Updated (`P03-S01-M24-T02`): a real config source for remote URL, author identity, and protected branches now exists, and the live delivery-pipeline route is genuinely wired to use it.** `ai_os_kernel.git_integration.settings.GitIntegrationSettings` reads `AIOS_GIT_REMOTE_URL`/`AIOS_GIT_AUTHOR_NAME`/`AIOS_GIT_AUTHOR_EMAIL`/`AIOS_GIT_PROTECTED_BRANCHES` directly from the environment — **not** Configuration Manager/`PlatformConfig` (§6 below still names Configuration Manager as the eventual supplier; this is a disclosed, product-owner-precedented deviation for now, not a doc update to §6's own approved design). The reasoning is `configuration_manager/models.py`'s own stated exclusion principle: a repository's real push destination and author identity are deployment-specific, credential-adjacent values — the identical class already carved out for `AIOS_DATABASE_URL`/`DatabaseSettings` and `OTEL_EXPORTER_OTLP_ENDPOINT`/`ObservabilitySettings`, neither of which is a `PlatformConfig` field either. `ai_os_kernel.git_integration.default_service.build_git_integration_service_from_env` builds a real `GitIntegrationService` from these settings — returning `None` (the existing, safe no-op) when `AIOS_GIT_REMOTE_URL` is absent, and raising `GitIntegrationConfigError` if it is set but author identity or `protected_branches` is missing or resolves to empty (closing this document's own R-001-flagged "an empty protected-branches set is not a safe production default" finding). `bootstrap.py`'s real `se.delivery_pipeline` composition now calls this builder and threads the result through `SqlAgentRegistry(git_service=...)` → `build_pack_context` → `ToolInvokerAdapter`, so a correctly-configured deployment's live HTTP route can genuinely commit and push, not only a hand-wired integration test. `ai_os_pack_software_engineering.agents.git_push.GitPushAgentEntrypoint`'s own `remote_url` constructor default now also reads `AIOS_GIT_REMOTE_URL` (via plain `os.environ`, never a Kernel import — the pack has zero forbidden-import violations today and this keeps it that way) when not passed explicitly, mirroring `ai_os_kernel.sandbox.default_executor.build_default_sandbox_executor`'s own "one env var, read once at construction" shape for the identical zero-arg-constructed-agent problem.

**Updated: the service is now genuinely reachable through `ToolInvoker`, not just callable directly.** `platform.git.commit`/`platform.git.create_branch`/`platform.git.push` are three real, platform-provided tool ids (the identical shape `platform.sandbox.run_command` established) dispatched by `ai_os_kernel.sdk_adapters.tool_invoker_adapter.ToolInvokerAdapter` straight to this service — an agent's own `context.tools.invoke("platform.git.commit", ...)` call reaches the real service, the real sandbox, and a real `git` subprocess, proven end to end. Still no real Software Engineering Pack agent actually calls these tool ids yet (no Build/Release agent code was changed) — the mechanism is real and reachable; wiring a real caller is separate, later work. See `platform_sdk.md` §5.6's own updated decision block for the full reasoning, including why this needed the shim path (Kernel-internal DB access) rather than the zero-arg registry-resolved path.

**A real, minimal Git Integration Service now exists — commit, branch, and push, genuinely audited — the first real Platform Service this codebase has ever had.** Lives at `kernel/src/ai_os_kernel/git_integration/` (a Kernel subpackage, not a separate `platform_services/` uv workspace member — a disclosed, product-owner-approved packaging decision; whether Platform Services become a genuinely separate tier is real, deferred, later architecture work). `GitIntegrationService.commit`/`create_branch`/`push` run real `git` subprocesses through the existing `SandboxExecutor` (real secret exclusion, no shell), audit every mutating operation through the existing, hash-chained `AuditLogWriter`, and resolve an optional push credential through the existing `AccessBroker`/`SecretValue` — no parallel mechanism for any of the three. §5.1's "absent from the tool surface, not gated" rule for a protected-branch push is real: `push()` refuses before any subprocess or credential resolution runs, which is also how this service respects R-001/ADR-0007's human-approval gate without ever calling into it (every real integration path onto a protected branch must go through a PR with human approval — a mechanism this step does not build). §5's "credentials never enter a sandbox" rule is real: a resolved secret travels only via `GIT_ASKPASS` (a real, per-call temp script, mode `0700`, deleted after use) on the push subprocess's own environment — never a URL, `.git/config`, log, or audit payload, proven against a real Postgres audit trail.

**Still genuinely partial.** No clone/fetch/status/diff/pull (this ticket's own Goal names only commit/branch/push); no PR-creation/merge mechanism (real, separate, later work); no credential support in the Tool's own input schema (`ToolInvoker.invoke` carries no `SecurityContext` to resolve one with, a disclosed, deferred gap) — `AIOS_GIT_*` carries no credential field either, matching this; the `git:write` check (`P03-S01-M24-T03`, paragraph above) is the declared-permission term only, not the full principal-inclusive ADR-0023 chain, for the identical `SecurityContext`-unreachable reason. `GitIntegrationService.__init__` itself is still explicit-caller-supplied parameters, not env-aware on its own; the config source is the composition root (`bootstrap.py`), one layer up — see `P03-S01-M24-T02`'s own paragraph above. See `git_integration.py`'s and `tool_invoker_adapter.py`'s own module docstrings for the full reasoning.

Consequence for the threat model: the T11 ("Git history or branch destruction") controls in `../../09_security/security_architecture.md` §14 — force-push prohibition, protected-branch policy, credentials never entering a sandbox — are now real, not merely satisfied by absence. See that document's own Implementation Status.

Authoritative, always-current status: the per-module completion table in `feature_inventory.md`; build history in `history/INDEX.md` (all under `docs/19_roadmap/`).

## 1. Purpose

This document defines the design of the **Git Integration Service**, a shared Platform Service in AI_OS.

The Git Integration Service provides a controlled, auditable interface for interacting with Git repositories. It is the primary way Agents and Tools perform version-control operations (clone, status, diff, commit, branch, etc.) without embedding Git logic directly in agents.

This document is subordinate to:

1. Project Constitution  
2. System Architecture  
3. Kernel Architecture  
4. Security Manager Design  
5. Software Engineering Pack  

---

## 2. Design Goals

The Git Integration Service must:

- Provide a safe, permission-aware interface to Git operations
- Support the most common workflows needed by software engineering agents
- Be fully observable and auditable
- Prevent uncontrolled or destructive operations
- Work with both local and remote repositories
- Remain configuration-driven

---

## 3. Core Responsibilities

- Clone / fetch repositories
- Report status and diffs
- Stage and commit changes (under strict controls)
- Create and switch branches
- Support pull / push operations (with authorization)
- Provide repository metadata
- Enforce permissions and policies
- Emit detailed audit events for all mutating operations

---

## 4. High-Level Structure

```text
Git Integration Service
│
├── Git Interface (abstract)
├── Repository Manager
├── Operation Executors
│     ├── Read Operations (status, diff, log, show)
│     └── Write Operations (add, commit, branch, merge, push)
├── Permission & Policy Checker
├── Working Copy Manager
└── Observability & Audit
```

---

## 5. Key Design Rules

- Agents never invoke the Git CLI directly; they go through this service or approved Tools that use it.
- **Credentials live in this service and never enter a sandbox.** The service exposes the *operation* (`push`) and withholds the *credential*. A sandboxed step receives a capability, not a secret ([ADR-0024](../../18_decision_log/adr/ADR-0024-secrets-management-backend.md)).
- Working copies are **isolated per workflow instance — mandatory, not best-effort.** This is what prevents concurrent-write corruption in parallel and fan-out workflows.
- Every mutating operation is audited with actor, repository, branch, and commit range.

### 5.1 Prohibited Operations

These are **absent from the tool surface** — not gated, not configurable-on, not available with elevated permission:

| Operation | Why |
|---|---|
| `push --force` / `--force-with-lease` to a protected branch | Destroys customer work irrecoverably |
| Branch deletion on a protected branch | Same |
| History rewriting (`rebase --force`, `filter-branch`, `reset --hard` + push) | Same |
| Direct push to a protected branch | Bypasses review; all changes go via a feature branch and pull request |

Making these unavailable rather than permission-gated is deliberate: a permission can be misconfigured, and the consequence here is unrecoverable. Every push targets a feature branch; integration happens through a pull request with human approval ([ADR-0007](../../18_decision_log/adr/ADR-0007-human-governance-for-critical-decisions.md)).

---

## 6. Relationship with Other Components

- **Software Engineering Pack** (especially Backend, Frontend, DevOps, Release, Refactoring agents) is the primary consumer.
- **Tools** in the Software Engineering Pack will typically wrap this service.
- **Security Manager** enforces who can perform which Git operations.
- **Workflow Engine** provides the context (which workflow / experiment is performing the operation).
- **Observability** records every significant Git operation.
- **Storage Service** may be used for temporary working copies or artifacts.
- **Configuration Manager** supplies repository URLs, credentials references, and policies.

---

## 7. Observability & Audit Requirements

Every significant Git operation must record:

- Operation type
- Repository identifier
- Branch / commit information
- Success / failure
- Actor (workflow, agent, user)
- Trace ID / Workflow ID
- Timestamp

Mutating operations are especially important for the audit trail.

---

## 8. Current Status

This document defines the design baseline for the Git Integration Service.

Concrete command mappings, working-copy isolation strategies, and permission models will be refined during implementation.

---

## 9. Final Authority

Order of precedence:

1. Project Constitution  
2. System Architecture  
3. Kernel Architecture  
4. Git Integration Service  
5. Source Code
