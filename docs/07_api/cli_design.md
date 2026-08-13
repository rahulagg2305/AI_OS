# CLI Design – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** CLI Design  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## Implementation Status (2026-08-10, `P06-S04-M38-T01`, revisited a third time)

**Built: a real `aios` CLI, 6 of 8 documented command groups fully real.** `tools/aios` is a real, installable `ai-os-cli` distribution (Typer + Rich, exactly this document's own §4 tech choice), a pure client of the platform API — no Kernel import, no database credential, ever. `auth` (login/logout/whoami — see below), `health` (live/ready), `workflow` (start/list/show/events/manifest/cancel — only `retry` remains), `approve` (decide/list/show), `pack` (list/show/activate/deactivate, fully real), `config` (get/set/flags, fully real) all call real HTTP endpoints. `--output human`/`--output json` and this section's own §4 exit-code table are both real, driven by the actual HTTP response.

**`auth login`/`whoami` do not round-trip through a real server** — there is no `/auth/login` endpoint anywhere to exchange credentials for a token (the Kernel only ever *verifies* a token someone else already issued: a pre-shared HS256 secret or a real OIDC provider). `login` stores a token the caller already has; `whoami` decodes that token's own claims locally, correct without a server round trip since a JWT's claims are readable without verifying its signature.

**Updated: `workflow cancel` is real.** `POST /api/v1/workflows/{id}/cancel` (`P06-S01-M36-T04`) reuses a new `WorkflowInstanceRepository.cancel`, gated by a new `workflow:control` permission (granted to `operator`/`maintainer`/`admin`, matching `workflow:start`'s own grant). Real, disclosed scope: stops the instance from being discovered again by the worker loop; does not forcibly interrupt an already-in-flight step. §5's own "destructive commands require `--yes` or confirmation" rule is not yet implemented for this command — a pre-existing gap across every command in this CLI, not introduced here (`pack deactivate` doesn't have it either).

**Prior update: `workflow manifest` is real.** `GET /api/v1/workflows/{id}/run_manifest` (`P06-S01-M36-T04`) reuses a new `SqlRunManifestRecorder.get_by_workflow_id` read over the same recorder the Workflow Engine already writes through at real completion — no new persistence concept. A `404` distinguishes "workflow does not exist" from "exists but never completed," both honestly reported, never a fabricated empty manifest.

**Prior update: `approve list`/`show` are real.** The blocker disclosed here through `P06-S04-M38-T01` (`ApprovalRepository` had no method that lists approvals) closed at `P06-S03-M39-T02` (Dashboard's Pending Approvals view: `list_pending()`/`GET /api/v1/approvals`) — wired `approve list` onto that same route and added the one further real route `approve show` needed, `GET /api/v1/approvals/{approval_id}`, over the already-existing `SqlApprovalRepository.get_by_id` read.

**Not built — no HTTP endpoint exists yet, disclosed rather than faked** (every command below is still discoverable via `--help`, and fails with the real, specific reason when run): `workflow retry` (needs a real "retry from where" design decision — no operator-triggered mechanism exists), `logs` (no log-query route), `health detail` (no distinct endpoint — `ready` already returns full per-component detail). **`experiment` left this list on 2026-08-13 (`P06-S04-M38-T01`) and all four of its documented subcommands are real.** Its stated blocker — "Benchmarking Pack still 0% built", later phrased in code as "no `/api/v1/experiments` route exists in production" — stopped being true once api_architecture.md §6.3 became fully real (`P04-S01-M12-T12`/`T13`/`T14`/`T15`); `create`/`run`/`show`/`compare` now call `POST /experiments`, `POST /experiments/{id}/run`, `GET /experiments/{id}` and `GET /experiments/{id}/comparison` respectively. Deliberately **no `experiment list`**, even though `GET /api/v1/experiments` is real: §4's own command tree names four subcommands, and adding a fifth would be inventing undocumented CLI surface. `--definition` takes a JSON object, matching `workflow start --inputs`'s own established shape rather than introducing a file-path convention this CLI has nowhere else.

Authoritative, always-current status: the per-module completion table in `feature_inventory.md`; build history in `history/INDEX.md` (all under `docs/19_roadmap/`).

## 1. Purpose

This document defines the design of the **Command Line Interface (CLI)** for AI_OS.

The CLI is an optional but recommended interface primarily aimed at developers and power users. It provides scriptable, low-latency access to core platform capabilities.

This document is subordinate to:

1. System Architecture  
2. Dashboard Architecture  
3. Multi-modal Interaction Design  
4. Authentication & Authorization Deep Dive  

---

## 2. Design Goals

The CLI must:

- Provide fast, scriptable access to key operations
- Support automation and CI-style usage
- Remain consistent with the same platform APIs used by the Dashboard and other clients
- Be permission-aware and auditable
- Follow good CLI UX practices (clear output, useful exit codes, composability)

---

## 3. Primary Use Cases

- Start and manage workflows
- Query workflow status
- List and act on Human Approval Points
- Trigger or inspect experiments
- View basic cost and quality summaries
- Inspect system / pack health
- Perform administrative tasks (where authorized)

---

## 4. High-Level Structure

**Technology: Typer + Rich**, distributed as `ai-os-cli`, invoked as `aios`. A pure client of the platform API ([ADR-0014](../18_decision_log/adr/ADR-0014-api-style-and-realtime-transport.md)) — it embeds no Kernel logic and holds no database credentials.

```text
aios
├── auth      login · logout · whoami
├── workflow  start · list · show · cancel · retry · events · manifest
├── approve   list · show · decide
├── experiment  create · run · show · compare
├── pack      list · show · activate · deactivate
├── config    get · set · flags
├── health    live · ready · detail
└── logs      tail · search
```

**CLI conventions**, so it composes in scripts rather than only reading well:

| Concern | Rule |
|---|---|
| Output | `--output human` (Rich, default when a TTY) or `--output json` (default when piped) |
| Exit codes | `0` success · `1` general error · `2` usage error · `3` authorization denied · `4` resource not found · `5` operation failed a gate · `6` timeout |
| Destructive commands | Require `--yes` or an interactive confirmation. **Not implemented anywhere in the real CLI as of 2026-08-13** — `workflow cancel`, `pack deactivate` and `experiment run` (which spends real money on billable LLM calls) all execute without confirmation. Recorded when `experiment run` was built rather than implemented for that one command alone, which would have made the convention arbitrary. |
| Long operations | Return immediately with an ID; `--wait` opts into following the WebSocket stream |
| Correlation | `--trace-id` is printed on every mutating command, so a CLI action is traceable to a platform trace |
| Configuration | `~/.config/aios/config.toml` plus `AIOS_*` environment variables |

---

## 5. Design Rules

- The CLI is a client of the platform APIs; it does not embed Kernel business logic.
- All commands must respect authentication and authorization.
- Destructive or high-impact commands should require explicit confirmation or appropriate flags.
- Output should support both human-readable and machine-readable (JSON) formats.
- Exit codes should be meaningful for scripting.
- The CLI should reuse the same correlation concepts (Workflow ID, etc.) as other interfaces.

---

## 6. Relationship with Other Components

- Uses the same backend APIs as the Dashboard where practical.
- Integrates with Authentication & Authorization.
- Can participate in multi-modal flows (e.g., start something via CLI, approve via Dashboard, check status via Voice).
- Observability still applies; CLI-initiated actions must be traceable.

---

## 7. Current Status

This document defines the baseline CLI design.

Detailed command structure, flags, output schemas, and packaging will be refined during implementation.

---

## 8. Final Authority

Order of precedence:

1. System Architecture  
2. Multi-modal Interaction Design  
3. CLI Design  
4. Source Code
