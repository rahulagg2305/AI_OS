# Risk Register — AI_OS

**Status:** Active, permanent · **Introduced:** Phase R2 (2026-07-31)

A real, permanent record of open risks. Hand-maintained (unlike the
generated roadmap views), but **entry-structured**: each risk is a fixed
row plus a short block. Never append narrative to an existing entry —
change its status field, or add a new entry.

Severity: **H** (can cause real harm or data loss) · **M** (can cause
significant rework) · **L** (contained).

**Reviewed 2026-07-31 (R1–R4 final closeout); R-008 closed 2026-08-01.**
10 closed, 1 open. Zero open process-defect risks: everything remaining
is a real product-development gap (R-006, R-009), not a defect in the
process itself.

| ID | Risk | Sev | Status | Owner decision |
|---|---|---|---|---|
| R-001 | Deploy capability shipping before the approval guardrail | H | **Open — permanent hard rule** | Product owner, 2026-07-31 |
| R-002 | Docker exception-catching inconsistency across test guards | L | **Closed** 2026-07-31 | — |
| R-003 | CI integration job red on Linux, green locally | M | **Closed** 2026-07-31 | — |
| R-004 | `gh` CLI unauthenticated — CI logs unreadable | M | **Closed** 2026-07-31 | Product owner ran `gh auth login` |
| R-005 | Generated-doc staleness not gated in CI | M | **Closed** 2026-07-31 | — |
| R-006 | 36 of 60 MUST requirements untouched | H | **Open — accepted baseline** | Product owner, 2026-07-31 |
| R-007 | `functional_requirements.md` status block drifts from reality | M | **Closed** 2026-07-31 | — |
| R-008 | No `AiOsError` hierarchy; error contract is per-module | M | **Closed** 2026-08-01 | — |
| R-009 | Audit log is schema-only — no writer, no hash chain | H | **Open** | Ready: `P01-S05-M04-T05` |
| R-010 | CI type-checks only a subset of `[tool.mypy] files` | M | **Closed** 2026-07-31 | — |
| R-011 | `ai_os_kernel` ships no `py.typed` marker | L | **Closed** 2026-07-31 | Superseded by R-010 |
| R-012 | Ticket dependency graph had no recorded edges | M | **Closed** 2026-07-31 | — |
| R-013 | Two dependency edges were judgement calls | L | **Closed** 2026-07-31 | Both decided, no change |

---

### R-001 — Deploy capability before the approval guardrail

**Rule (permanent, product-owner decision 2026-07-31): no deployment
capability may ship before the Human Approval guardrail exists.**

`functional_requirements.md` §10 puts "autonomous production deployment
without human approval" out of v1 scope. Phase R1 found this currently
reads as satisfied only because *both* halves are missing: there is no
deploy capability (no Dockerfile, no Kubernetes, no Helm, no Terraform,
no Git integration) **and** no approval guardrail (FR-013/FR-111 at 0%;
`governance.approvals` has no writer; `human_approval` steps complete as
no-ops). `se.delivery_pipeline` already runs fully autonomously.

The moment either P07-S01-M40-T01 (Kubernetes/Helm) or P03-S01-M24-T01
(Git integration) lands without P03-S05-M14-T04/T05, this line flips
from satisfied to violated silently. **Blocking dependency:** those two
Tasks each declare the approval Tasks as `depends_on`.

### R-002 — Docker exception-catching inconsistency *(closed)*

`_postgres_fixture.py` caught only `docker.errors.DockerException`, while
`test_docker_sandbox_live.py` caught `(DockerException, OSError)`. A
connection *establishment* failure surfaces as a raw `OSError`, so the
narrower guard could have errored instead of skipping. Closed in Phase
R2 by widening the postgres fixture to match. Same root cause as the
`registry.py` fix of 2026-07-31.

### R-003 — CI integration job red on Linux, green locally *(closed)*

Closed 2026-07-31. Root cause found from real, authenticated logs
(`gh run view 30611974824 --log-failed`), not guessed: `DockerSandbox`
runs its container as a fixed non-root UID (`65534:65534`, ADR-0016),
but the bind-mounted `working_directory` is created host-side and owned
by whatever real account created it — on the GitHub Actions Ubuntu
runner, an account with no relationship to that UID. The kernel's own
permission check on the bind mount genuinely refused the write
(`sh: cannot create output.txt: Permission denied`,
`PermissionError: [Errno 13]`) — a real Linux-vs-Windows difference:
Docker Desktop's bind-mount layer does not enforce host POSIX
permission bits the way a real Linux daemon does, so the identical test
passed unchanged in local development. Five failures in the real log
all traced to this one cause. Fixed by `chmod`-ing the mounted directory
to `0o777` before container creation — narrow, touches only that one
per-invocation directory, and does not weaken any other isolation
control. **Proof: Actions run
[30635476406](https://github.com/rahulagg2305/AI_OS/actions/runs/30635476406)
— `Integration tests` conclusion `success`** (was `failure` on
30611974824, identical command).

### R-004 — `gh` CLI unauthenticated *(closed)*

Closed 2026-07-31. Product owner ran `gh auth login` (account
`rahulagg2305`); `gh auth status` now confirms an active, keyring-backed
session. This is what made the real R-003 root cause readable at all.

### R-006 — 36 of 60 MUST requirements untouched

Accepted as the real backlog baseline (product owner, 2026-07-31). By
phase: B=1, C=8, D=11, E=7, F=9. Tracked as Tasks; visible in
`STATUS.md`.

### R-005 — Generated-doc staleness not gated in CI *(closed)*

Closed 2026-07-31. `ci.yml` runs `scripts.roadmap.generate --check` and
`pytest tests/roadmap`; both ran green on a real Ubuntu runner (Actions
run 30611974824). A hand edit to a generated rollup, or an oversized
ticket, now fails the build for real rather than only locally. The
tracking ticket `P01-S06-M43-T05` was stale at `todo` and was corrected
to `done` in this step — found by the R3c advisory check on its first run.

### R-007 — `functional_requirements.md` status block drift *(closed)*

Closed 2026-07-31. The three defects R1 found are fixed: the stale FR-012
classification refreshed, the three silently-omitted FRs (FR-030, FR-112,
FR-113) classified, and FR-030's misrepresentation corrected. The
document now points at the generated `STATUS.md`/`MODULE_BOARD.md` rather
than the retired hand-maintained trackers, so the *class* of drift this
risk described no longer has a place to accumulate.

### R-008 — No `AiOsError` hierarchy *(closed)*

Closed 2026-08-01. Verified, not assumed: `platform_sdk/src/ai_os_sdk/errors/taxonomy.py`
and `models/error.py` were checked field-by-field against
`error_handling_retry.md` §8's Structured Error Contract — the exact six
categories, the exact hierarchy (`AiOsError` → `TransientError`,
`PermanentError`, `QualityError`, `InfrastructureError`,
`BudgetExceededError`, `SecurityError`), the documented `Retriable`
table (§3) including `infrastructure`'s case-by-case override, and a
real 1:1 `to_structured_error()` mapping with no possibility of
category disagreement — all real and confirmed by 144 passing tests in
`platform_sdk/tests/test_error_taxonomy.py` (28 of which target this
module directly), `ruff check`, and `mypy --strict` clean. **Not** part
of this risk's closure, and remaining as separate, larger, already-
disclosed gaps (the module's own docstrings say so): the `error_code`
catalogue (§3) has no populated entries, and no existing Kernel
exception (`LLMProviderError`, etc.) yet inherits from this hierarchy —
both need real producers across the codebase, tracked as ongoing
`feature_inventory.md` module 44 work, not this risk.

### R-011 — `ai_os_kernel` ships no `py.typed` *(closed)*

Closed 2026-07-31 as **superseded by R-010**, not as fixed. The marker is
still absent. The practical consequence — that per-directory type-checking
is misleading — is entirely contained by R-010's finding that CI does not
type-check those directories anyway. Tracking it twice added no signal.
Reopen if a distribution outside this repository ever imports
`ai_os_kernel`.

### R-012 — Ticket dependency graph had no recorded edges *(closed)*

Closed 2026-07-31. R3b found only 2 of 219 tickets carried 2+
dependencies, so "ready to start" reported unrecorded sequencing rather
than genuine readiness — overstating it by roughly double. R3c recorded
160 real edges across 113 tickets; ready dropped 122 → 64. Guarded
permanently by an acyclicity test and an advisory empty-dependency
signal surfaced in `STATUS.md`.

### R-013 — Two dependency edges were judgement calls *(closed — both decided)*

Closed 2026-07-31. Both edges named in the R3c report were investigated
against real design documents, not left as a guess:

- **`P02-S01-M05-T13`** (scheduler for delayed workflow starts) → does
  **not** depend on `P02-S01-M05-T12` (multi-instance worker loop).
  **Decision, with reasoning:** T13's own stated Output is "a started
  instance at the right time" — the temporal decision of *when* to fire,
  not *how many* to drive concurrently. Every existing trigger in this
  codebase (`build_pipeline_trigger`, the platform demo trigger) already
  starts and drives one instance to completion synchronously, using
  `WorkflowAdvanceRunner.run_once`/`run_to_completion` — the exact
  mechanism T13's own dependency (`P02-S01-M05-T02`, instance management)
  already provides. A Scheduler can fire on a timer and drive each fired
  instance the same way, sequentially or via independent `asyncio.Task`s,
  with no need for T12's specific lease-scanning worker-pool concept.
  "When to start" and "how many run at once" are orthogonal; T13 needs
  the first, not the second. `depends_on` is correct unchanged.
- **`P06-S06-M25-T01`** (Speech Gateway) → does **not** depend on
  `P06-S01-M36` (the HTTP API surface). **Decision, with reasoning:**
  ADR-0019 is explicit that the Speech Gateway is "**structurally
  parallel to the LLM Gateway**" — a platform service exposed through
  the SDK (`SpeechGateway`) and consumed directly by the Voice Capability
  Pack, never through `/api/v1`. The LLM Gateway (M06), its own direct
  structural analogue, likewise has no dependency on M36. `depends_on`
  is correct unchanged.

Neither ticket was edited — both dependency lists were already correct;
what was missing was the recorded reasoning, now here rather than left
as an open question.

### R-010 — CI type-checks only a subset of the configured files *(closed)*

Closed 2026-07-31. `ci.yml`'s mypy step ran `mypy --strict kernel/src
kernel/alembic tests` under a comment claiming it *"Mirrors [tool.mypy]
files in pyproject.toml exactly"* — it did not: the configured list also
includes `platform_sdk/src`, `platform_sdk/tests`,
`capability_packs/software-engineering/src`, that pack's `tests`, and
`scripts`, none of which were type-checked in CI. Fixed by changing the
step to the canonical, no-argument invocation (`uv run mypy --strict`),
which reads `[tool.mypy] files` itself and therefore cannot silently
drift from that config again — proven locally, `Success: no issues
found in 378 source files`.

### R-011 — `ai_os_kernel` ships no `py.typed`

`ai_os_sdk` and `ai_os_pack_software_engineering` both ship a `py.typed`
marker; `ai_os_kernel` does not. Consequence: any module importing
`ai_os_kernel` cannot be strictly type-checked *in isolation* — mypy
resolves it as an installed, untyped package and reports
`import-untyped`. It only passes when `kernel/src` is inside the same
analysis set. This is why `mypy --strict scripts tests/roadmap` fails
while `mypy --strict` succeeds. Low severity (the canonical invocation is
correct and green), but it makes per-directory type-checking misleading.

### R-009 — Audit log schema-only

`governance.audit_log` exists with no writer, no hash computed, and no
verification job, so FR-110 ("tamper-evident audit log") has no
implementation. Rated **H** because several governance claims elsewhere
implicitly assume it exists.
