# aios — the AI_OS CLI

Scriptable, low-latency access to the Kernel HTTP API (`docs/07_api/cli_design.md`).

## Status: 5 of 8 documented command groups real

**First real increment (`P06-S04-M38-T01`).** A pure client of the
platform API (ADR-0014) — no Kernel import, no database credential,
ever. `--output human` (Rich, default when a TTY) / `--output json`
(default when piped); the documented exit-code table (0 success, 1
general error, 2 usage error, 3 authorization denied, 4 not found, 5
gate/conflict, 6 timeout) is real, driven by the actual HTTP response,
not guessed.

**Real, backed by a real HTTP endpoint:**

- `auth` — `login`/`logout` (stores a bearer token locally; no real
  `/auth/login` endpoint exists to exchange credentials for one — the
  Kernel only ever verifies a token someone else issued), `whoami`
  (decodes the stored token's own claims locally — genuinely correct,
  since a JWT's claims are readable without verifying its signature —
  disclosed as a local decode, not a server round trip: no `/whoami`
  endpoint exists)
- `health` — `live`, `ready`
- `workflow` — `start`, `list`, `show`, `events`
- `approve` — `decide`
- `pack` — `list`, `show`, `activate`, `deactivate`
- `config` — `get`, `set`, `flags`

**Not built — no HTTP endpoint exists yet, disclosed rather than
faked (every one of these commands exits `1` with a clear message
naming the real gap):**

- `workflow cancel`/`retry`/`manifest` — no cancel/retry/manifest-read
  route exists
- `approve list`/`show` — `ApprovalRepository` has no method that
  lists approvals at all (the identical gap Dashboard's own
  `P06-S03-M39-T02` report disclosed for its own Pending Approvals
  view)
- `experiment` (all subcommands) — the Benchmarking Pack is still 0%
  built; no experiment submission/read path exists in production
- `logs` (all subcommands) — Observability has no log-query endpoint
- `health detail` — no distinct endpoint; `health ready` already
  returns full per-component detail

## Configuration

`~/.config/aios/config.toml` (`[api] base_url`, `[auth] token`) plus
`AIOS_API_URL`/`AIOS_TOKEN` environment variables, which always win
over the file — the identical "env overrides file" precedent
`ai_os_kernel.configuration_manager`'s own layered precedence
establishes elsewhere in this project.
