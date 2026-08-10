# CLI Design – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** CLI Design  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## Implementation Status (2026-08-10, `P06-S04-M38-T01`, revisited)

**Built: a real `aios` CLI, 5 of 8 documented command groups fully real, `approve` now fully real too.** `tools/aios` is a real, installable `ai-os-cli` distribution (Typer + Rich, exactly this document's own §4 tech choice), a pure client of the platform API — no Kernel import, no database credential, ever. `auth` (login/logout/whoami — see below), `health` (live/ready), `workflow` (start/list/show/events), `approve` (decide/list/show — `list`/`show` closed this step), `pack` (list/show/activate/deactivate, fully real), `config` (get/set/flags, fully real) all call real HTTP endpoints. `--output human`/`--output json` and this section's own §4 exit-code table are both real, driven by the actual HTTP response.

**`auth login`/`whoami` do not round-trip through a real server** — there is no `/auth/login` endpoint anywhere to exchange credentials for a token (the Kernel only ever *verifies* a token someone else already issued: a pre-shared HS256 secret or a real OIDC provider). `login` stores a token the caller already has; `whoami` decodes that token's own claims locally, correct without a server round trip since a JWT's claims are readable without verifying its signature.

**Updated: `approve list`/`show` are real.** The blocker disclosed here through `P06-S04-M38-T01` (`ApprovalRepository` had no method that lists approvals) closed at `P06-S03-M39-T02` (Dashboard's Pending Approvals view: `list_pending()`/`GET /api/v1/approvals`) — this step wires `approve list` onto that same route and adds the one further real route `approve show` needed, `GET /api/v1/approvals/{approval_id}`, over the already-existing `SqlApprovalRepository.get_by_id` read (previously used only internally by the decide route).

**Not built — no HTTP endpoint exists yet, disclosed rather than faked** (every command below is still discoverable via `--help`, and fails with the real, specific reason when run): `workflow cancel`/`retry`/`manifest`, `experiment` (Benchmarking Pack still 0% built), `logs` (no log-query route), `health detail` (no distinct endpoint — `ready` already returns full per-component detail).

Authoritative, always-current status: the per-module completion table in `feature_inventory.md` and `implementation_status.md`; build history in `history/INDEX.md` (all under `docs/19_roadmap/`).

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
| Destructive commands | Require `--yes` or an interactive confirmation |
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
