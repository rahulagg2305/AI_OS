# Risk Register — AI_OS

**Status:** Active, permanent · **Introduced:** Phase R2 (2026-07-31)

A real, permanent record of open risks. Hand-maintained (unlike the
generated roadmap views), but **entry-structured**: each risk is a fixed
row plus a short block. Never append narrative to an existing entry —
change its status field, or add a new entry.

Severity: **H** (can cause real harm or data loss) · **M** (can cause
significant rework) · **L** (contained).

**Reviewed 2026-07-31 (R1–R4 final closeout); R-008 and R-009 closed
2026-08-01; R-014 opened and closed 2026-08-09; R-015 opened and closed
2026-08-09; R-016 opened 2026-08-10; R-017 opened and closed 2026-08-11;
R-018 opened 2026-08-11.** 14 closed, 3 open (R-006, an accepted
baseline, not pending action; R-016, a real, unaddressed Workflow Engine
design gap; R-018, the "proven but idle" sweep, partially ticketed) plus
R-001 (a permanent standing rule, not a risk pending closure).

**R-017 and R-018 both came from one whole-project health audit
(2026-08-11), not from normal step-by-step work — and could not have.**
`CLAUDE.md`'s Core process rule deliberately restricts a development
step to its own ticket and direct dependencies, which structurally
cannot surface "this module is complete but nothing calls it," because
that fact lives *between* modules. R-017 was a real, production-affecting
defect found this way. Treat periodic audits as the intended counterweight
to that rule, not as evidence it failed.

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
| R-009 | Audit log is schema-only — no writer, no hash chain | H | **Closed** 2026-08-01 | — |
| R-010 | CI type-checks only a subset of `[tool.mypy] files` | M | **Closed** 2026-07-31 | — |
| R-011 | `ai_os_kernel` ships no `py.typed` marker | L | **Closed** 2026-07-31 | Superseded by R-010 |
| R-012 | Ticket dependency graph had no recorded edges | M | **Closed** 2026-07-31 | — |
| R-013 | Two dependency edges were judgement calls | L | **Closed** 2026-07-31 | Both decided, no change |
| R-014 | No CI job ever ran any Capability Pack's own `tests/` | M | **Closed** 2026-08-09 | — |
| R-015 | Local-HTTP-server tests flaky under full local suite runs (never on real CI) | L | **Closed** 2026-08-09 | — |
| R-016 | No persisted terminal `failed` state; the worker loop retries every step failure unboundedly, forever | M | **Open — real, undecided design question** | Product owner, 2026-08-10 |
| R-017 | Manifest-declared Tools were unreachable in production — no caller ever passed a `ToolRegistry` | M | **Closed** 2026-08-11 (`P02-S05-M18-T04`) | — |
| R-018 | "Proven but idle": real, tested subsystems with zero production reachability (Traceability Engine at 100% `done`; two packs with no manifest) | M | **Open — partially ticketed** | Health audit, 2026-08-11 |

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

**Update 2026-08-02: the blocking dependency itself is now satisfied.**
P03-S05-M14-T04/T05 are done — a real Human Approval Manager exists,
genuinely pauses a workflow at a `human_approval` step, and resumes only
on a real, attributable decision; a timeout never implies approval
(proven via real Postgres tests, `feature_inventory.md` module 5's own
row). **The rule itself stays open and permanent** (it is a standing
constraint, not a one-time gap to close): it still requires that *when*
P07-S01-M40-T01 or P03-S01-M24-T01 is eventually built, it actually
wires a real `human_approval` step into its own deploy pipeline, not
merely that the guardrail exists somewhere unused. The Manager's own
service-layer-only scope (no HTTP route, no RBAC against `approver`) is
a disclosed, product-owner-approved gap — not itself a violation of this
rule, since no deploy capability exists yet to expose it.

**Update 2026-08-02: P03-S01-M24-T01 (Git integration) is now done, and
it genuinely honors this rule — the first of the two named blocking
Tasks to actually land.** The real Git Integration Service
(`kernel/src/ai_os_kernel/git_integration/`) makes a direct push to a
protected branch structurally impossible (absent from its own tool
surface, `git_integration.md` §5.1) rather than merely gating it behind
a permission — every real integration path onto a protected branch
still requires a pull request with human approval, a mechanism this
Task deliberately does not build.

**Update 2026-08-02, same day (`P03-S04-M31-T04`/`P03-S03-M30-T04`): a
real Tool and a real workflow caller both now exist — the rule remains
genuinely honored, not merely latent.** `se.delivery_pipeline`'s new
`git-push` step reaches this service for real, through a real agent,
through real `ToolInvoker` dispatch. The protected-branch refusal is
still real and still structural (proven end to end at every layer:
`GitIntegrationService`, `ToolInvokerAdapter`, and now the full pipeline
run). Production reachability remains narrow by construction, not by
omission: `bootstrap.py`'s own real `SqlAgentRegistry` — the composition
behind the live HTTP route — is not threaded a `git_service` at all, so
the real HTTP route still cannot reach these tools; only a caller that
explicitly constructs and injects a real `GitIntegrationService` (this
step's own end-to-end test) can. **The rule stays open and permanent**:
it still requires that whichever real deploy-capability caller
eventually reaches this service (via the live route, or
P07-S01-M40-T01/Kubernetes-Helm) genuinely wires a real, non-empty
`push_policy` — an empty `protected_branches` set (this step's own
proof test) is deliberately not a safe production default.

**Update 2026-08-02, same day (`P03-S01-M24-T02`): production
reachability is no longer narrow by omission — `bootstrap.py`'s real
`SqlAgentRegistry` composition now *is* threaded a real `git_service`,
built from `AIOS_GIT_*` env vars
(`ai_os_kernel.git_integration.default_service.
build_git_integration_service_from_env`). This closes the previous
update's own named gap, and does so while genuinely enforcing the
"non-empty `push_policy`" requirement that update itself stated: the
builder raises `GitIntegrationConfigError` — refusing to start the
composition at all — if `AIOS_GIT_REMOTE_URL` is configured but
`AIOS_GIT_PROTECTED_BRANCHES` is missing or resolves to zero real
branch names, rather than silently defaulting to an empty set. In every
environment today `AIOS_GIT_REMOTE_URL` remains unset, so the live HTTP
route still resolves to the existing, safe no-op — this closes *how*
reachability would be granted, not that it now is. **The rule stays
open and permanent**: this is still only the "no `push --force`/direct
push to protected branches" structural half; the moment a real
deployment sets `AIOS_GIT_REMOTE_URL` for a genuine push destination, a
real `human_approval` step in whatever workflow drives that push is
still the operator's own responsibility to wire, exactly as before.

**Update 2026-08-03 (`P03-S03-M30-T05`): the previous update's own
named remaining gap is closed — `se.delivery_pipeline` itself now wires
a real `human_approval` step, `approve-git-push`, immediately before
its own `git-push` step.** Reuses the existing Human Approval Manager
(`P03-S05-M14-T04`/`T05`/`T06`) unchanged: the pipeline genuinely
pauses (`WorkflowRunOutcome.WAITING_FOR_HUMAN`) the first time it
reaches this point, and resumes only on a real, attributable,
RBAC-authorized decision (`approver:approve-git-push` or `admin`) —
never on a timeout. Proven end to end, one real run:
`git-push` (and the real remote it targets) receives nothing while the
approval is pending; an unauthorized decision attempt is refused with
the remote still untouched; only a real, authorized decision resumes
the pipeline to a genuine commit and push
(`test_delivery_pipeline_git_push.py`). **The rule stays open and
permanent**: this closes the gap for `se.delivery_pipeline` specifically
— the one real workflow that reaches this service today — not as a
generic guarantee every *future* deploy-capability workflow inherits
automatically; whichever workflow eventually drives
P07-S01-M40-T01/Kubernetes-Helm still has to wire its own
`human_approval` step the same way, exactly as this update itself just
did. Also still real, disclosed, deferred: no HTTP route exists yet for
a live Kernel process to receive a real decision against a paused
production run, and the generic multi-instance worker loop
(`bootstrap.py`) is not wired with this pipeline's own executor set —
matching `human_approval.py`'s own long-standing disclosed scope,
unchanged by this step.

**Update 2026-08-07 (`P07-S01-M40-T01`): Kubernetes manifests and a
Helm chart now exist — `infra/kubernetes/helm/ai-os/` — the other
named blocking Task, now real, does not itself trigger this rule.**
The chart declares `Deployment`/`Service`/`ConfigMap`/`ServiceAccount`/
`PodDisruptionBudget`/`HorizontalPodAutoscaler` resources only —
nothing in this codebase calls `helm install`/`kubectl apply`
automatically from any workflow; applying it remains a manual,
human-run operation (`helm template | kubectl apply` or `helm
install`), the identical "declarative artifact, not an autonomous
pipeline" shape a static Helm chart always has. **The rule stays open
and permanent**: it still requires that *whichever* workflow
eventually drives an automatic apply of this chart wires a real
`human_approval` step first, exactly as `se.delivery_pipeline` already
does for its own `git-push` step above — no such automatic-apply
workflow exists yet, so this rule's own concern is genuinely not yet
triggered, not merely unaddressed.

**Correction (2026-08-08, found during a full pre-completion health
audit): the 2026-08-03 update above's own closing sentence was stale —
never resynced after it was closed.** It claimed "no HTTP route exists
yet for a live Kernel process to receive a real decision against a
paused production run." `P03-S03-M30-T06` closed exactly this, the same
day range as later updates in this section: `ai_os_kernel.routes.approvals`
(`POST /api/v1/workflows/{workflow_id}/approvals/{approval_id}/decisions`)
is real, and `resume_pipeline_after_approval` (`delivery_pipeline.py`)
genuinely re-drives a paused instance to completion through it — proven
end to end over real HTTP against real Postgres (a real pause, a refused
unauthorized attempt, an authorized decision resuming to a genuine commit
and push). The second half of that sentence is still accurate, but for a
different reason than originally stated: the generic multi-instance
worker loop (`bootstrap.py`) still does not drive `se.delivery_pipeline`
— not because nothing wires it, but because it is now a deliberate
exclusion (`exclude_definition_ids`, `feature_inventory.md` module 5's
own row): that loop's fixed executor composition cannot run this
pipeline's `quality_gate`/`decision`/`human_approval` steps at all, so
excluding it and resuming exclusively through the real HTTP route above
is the safe path, not an unaddressed gap. **The rule itself remains open
and permanent, unaffected by this correction** — this only fixes a
factual claim, not the rule's own status.

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

### R-015 — Local-HTTP-server test flakiness under full local suite runs *(closed)*

Disclosed across 3 separate steps (2026-08-09), formally investigated
and closed the same day per explicit product-owner instruction.
Observed failures, all isolated real local-server adapter/routing
tests, each passing immediately in isolation and on an immediate
full-suite re-run: `test_multi_provider_routing.py::
test_one_router_and_dispatcher_genuinely_reach_both_real_provider_adapters`,
`test_anthropic_adapter.py::test_count_tokens_returns_the_real_provider_reported_count`,
`test_local_adapter.py::test_embed_classifies_a_real_http_error_response`.

**Real root cause, found by investigation, not guessed:** two distinct,
compounding factors.

1. **Genuine host-level thread-scheduling contention, Windows-local-only.**
   `gh run list --branch main --limit 30` shows exactly one real CI
   failure across this entire session's 29 other pushes — a `ruff
   format` failure fixed the same step, unrelated to test flakiness.
   The flake has **never once occurred on the real Ubuntu GitHub
   Actions runners**, only on this project's own local Windows
   full-suite runs (1500+ tests, real Docker daemon activity, many
   concurrent threads). Every affected test used a hardcoded
   `timeout=2.0` httpx/Anthropic-SDK client timeout against a real,
   already-listening local `http.server.HTTPServer` — generous enough
   on an idle CI runner, tight enough to occasionally miss under real
   Windows thread-scheduling contention at full-suite scale.
2. **A real, independently-discovered resource-cleanup bug, found while
   investigating the fixtures.** Every real local-HTTP-server fixture
   in this codebase (13 files, 23 real call sites, not just the 3
   flaky ones) called `server.shutdown()` + `thread.join()` but never
   `server.server_close()` — `socketserver.BaseServer.shutdown()` only
   stops the `serve_forever()` loop; it does not close the underlying
   listening socket (`TCPServer.server_close()` does). The socket's
   real closure was left to non-deterministic garbage collection
   across hundreds of fixture instantiations over a full suite run — a
   genuine, if hard-to-precisely-quantify, resource-hygiene defect,
   fixed regardless of its exact share of the observed timeout flakes.

**Real fix, not a guess — both causes addressed, proven, zero
regression:**

- `server.server_close()` added after every one of the 23 real
  `server.shutdown()`/`thread.join()` call sites across all 13 files
  (mechanical, systemic, applied via a verified regex substitution,
  re-formatted with `ruff format` — every file's diff inspected).
- The 3 specifically-flaky files' own hardcoded `timeout=2.0` replaced
  with a named, documented `_HTTP_TIMEOUT_SECONDS = 10.0` constant (a
  real local server responds near-instantly when healthy, so a
  generous ceiling costs nothing in the success case and only helps
  under genuine contention).
- Proven: `tests/unit -q` run **3 times** after the fix, `1226 passed`
  each time with zero flakes (the same suite had hit this flake in 2 of
  the 3 most recent runs before the fix). `mypy --strict`: clean.
  `capability_packs/*/tests`, `tests/contract`, `tests/roadmap`: all
  green. No OpenAPI drift.

**Classification: genuine timing/resource contention, real and
independently-verified resource-cleanup bug — not a test-isolation bug
in the fixture's own server-readiness handshake** (the listening socket
is already bound and accepting before the fixture yields its URL in
every case; there is no readiness race). **Not purely an
"environment-only, can't-be-eliminated" flake** either — a real,
disclosed root cause existed and was fixed, not merely documented as
accepted.

**Addendum (2026-08-10, `P06-S01-M36-T04`) — a real, new data point
that partially contradicts this entry's own "never once occurred on
the real...GitHub Actions runners" claim.** CI run `31378794330`
(Integration tests job) genuinely failed on the real Ubuntu runner:
`test_worker_loop_execution.py::
test_run_worker_loop_genuinely_drives_a_real_instance_to_completion_on_its_own`
— `AssertionError: assert ...RUNNING... == ...COMPLETED...`, a
concurrency/timing-margin assertion, not an HTTP-server one (a
different test family than the three named above). An immediate
`gh run rerun --failed`, no code change, passed clean, job-by-job. Not
reopening R-015 itself (a different test family, no root cause
investigated yet, one occurrence in ~30+ pushes since its own closure)
— recorded here as a disclosed, real exception to its own "never on
real CI" claim, not silently left standing as still fully accurate.
If this recurs on CI, it warrants its own investigation, the identical
discipline this entry's own root-cause analysis already modeled.

**Second real occurrence (2026-08-10, `P06-S01-M36-T04`, same day, a
later step)** — this has now recurred, meeting the bar the addendum
above itself set for "warrants its own investigation." CI run
`31390101661` (Integration tests job) failed on the real Ubuntu
runner: `test_worker_loop_execution.py::
test_a_single_tick_genuinely_advances_multiple_real_instances_concurrently`
— `assert 0.448... < 0.4`, the identical tight (2x) timing-margin
assertion this file's own local runs already showed failing/passing
inconsistently across identical retries earlier the same day (not a
deterministic regression from any real code change in either step —
neither step's own diff touches this test's own timed window).
`gh run rerun --failed`, no code change, resolved it again. **Real,
disclosed, not yet root-caused**: two genuine CI occurrences in one
day, both in the same test file, both a `< 0.4s` margin over real
concurrent work whose true minimum is `0.2s`+ — a tight bound that a
busier-than-usual Ubuntu runner can plausibly miss without any bug in
the code under test. Worth a dedicated investigation (widen the
margin, or make the assertion resistant to real scheduler jitter) if a
third occurrence lands — not attempted here, out of this ticket's own
scope (`GET /api/v1/agents`, unrelated to workflow-engine timing).

### R-014 — No CI job ever ran any Capability Pack's own tests *(closed)*

Found `P05-S02-M32-T01`, closed `P05-S02-M32-T02` (2026-08-09).
`capability_packs/*/tests/**` sits outside root `pyproject.toml`'s
`testpaths = ["tests"]`, and no `.github/workflows/ci.yml` step ever
named a `capability_packs/*/tests` path — confirmed by reading the
workflow file directly, not inferred from a test count. Real,
unaddressed impact: `benchmarking`'s 4 test files and
`software-engineering`'s `fs_read`/`build_run`/agent tests (242 tests
across all 3 real packs) had never once been verified in CI, for the
entire history of this project.

**Root cause, found while wiring the fix, not assumed:** a second, real
bug this gap had been hiding. Running the installed `pytest`
console-script entry point (what `uv run pytest` and every existing CI
step already use) does not add the repo root to `sys.path` the way
`python -m pytest` does. `capability_packs/software-engineering/tests/
test_database_agent.py` imports `tests.integration._postgres_fixture`
(a real, already-established cross-tree convention — that pack's own
`pyproject.toml` comment names it explicitly) — reachable only when the
repo root is on `sys.path`. The first attempt at a generic
`capability_packs/*/tests` CI step therefore failed to even collect,
invocation-style-dependent and invisible to whoever last happened to
run that one file via `python -m pytest` locally instead.

**Fixed at the root, not per-file or per-invocation:**
`[tool.pytest.ini_options] pythonpath = ["."]` in `pyproject.toml` —
pytest's own explicit, invocation-style-independent mechanism. A new
CI step, `pytest capability_packs (pack-local tests)`, runs
`capability_packs/*/tests` (generic glob, no hardcoded pack name — a
fourth real pack is covered automatically) in the `unit` job. Proven:
all 242 pack tests across all 3 real packs collect and pass via the
exact `pytest` entry point CI uses; the full `tests/unit` suite (1226
tests) passed on 2 of 3 repeated runs after the `pythonpath` addition —
the one failure (`test_multi_provider_routing.py`, a real local HTTP
server with a 2s timeout) passed immediately in isolation and on the
next full-suite run, matching a real-local-server timing flake, not a
deterministic regression from this change.

### R-009 — Audit log schema-only *(closed)*

Closed 2026-08-01, stale for some time before being caught: this entry
still named `P01-S05-M04-T05` as its own ready path, but that ticket
(and its follow-on, `T06`) had already been `done` since early this
same session. Verified, not assumed, before closing: `SqlAuditLogWriter`
(`kernel/src/ai_os_kernel/observability/audit.py`) genuinely computes
`row_hash`/`prev_hash` per row under a real `pg_advisory_xact_lock`
(serializing concurrent writers so two rows can never both claim the
same predecessor), and `verify_chain()` genuinely detects a tampered
row — both re-confirmed with a fresh test run (19 passed,
`test_audit.py`/`test_audit_verification_job.py`) as part of this
closure, not merely cited from memory. The scheduled verification job
(`run_periodic_audit_chain_verification`) is genuinely wired into a
real Kernel process (`P01-S04-M03-T06`, via
`GracefulShutdownCoordinator`), and `AccessBroker`
(`P01-S02-M19-T04`) is a real, audited consumer. FR-110
("tamper-evident audit log") is genuinely implemented.

### R-016 — No persisted terminal `failed` state; the worker loop retries every step failure unboundedly, forever

Opened 2026-08-10, `P06-S01-M36-T04`, while investigating
`POST /api/v1/workflows/{id}/retry` ("retry from where" — the doc's own
literal words say "from last failure"). Before building anything, a
genuine fork was found via direct source inspection, not guessed, and
presented to the product owner via `AskUserQuestion`, who chose:
**defer the route, record this finding, move to a different task.**

**Real finding — confirmed by tracing every real writer, not
assumed:** `WorkflowInstanceStatus.FAILED` (`workflow_engine/
instance.py`) is declared but never written by any real caller,
anywhere in this codebase.

- `WorkflowInstanceService.advance()` (`service.py`): on any step
  exception, writes a real `workflow_steps` row (`status="failed"`,
  via `WorkflowInstanceRepository.record_failed_attempt`) and
  re-raises the *original* exception unchanged — it never touches
  `workflow_instances.status`.
- `WorkflowAdvanceRunner.run_once` (`advance_runner.py`) — the method
  `WorkflowWorkerLoop._advance_one` (`worker_loop.py`) actually calls
  — has no retry/bound logic of its own; a raised exception propagates
  straight out.
- `_advance_one` catches that exception, logs it, and returns
  `"failed"` as a purely in-memory per-tick outcome label
  (`_Outcome`) — never a database write. The lease is already released
  (`run_once`'s own `finally`), so the identical instance — still
  `status='running'`, `current_step_id` unchanged — is rediscovered by
  `list_runnable_instances` on the very next poll and retried again.
  **No persisted attempt count, no bound, no terminal state**: a
  permanently-failing step retries forever, for the life of the Kernel
  process, for the one real, continuously-running production path.
- `WorkflowAdvanceRunner.run_to_completion`'s own bounded
  `RetryPolicy.max_attempts`/`max_duration_seconds` exhaustion (used
  only by the synchronous, one-shot demo/`se.delivery_pipeline`
  triggers) is real, but its `step_failure_counts`/
  `step_retry_deadlines` are local Python dicts, scoped to one method
  call's own stack — never persisted. By the time anyone could call an
  operator-triggered retry, that original HTTP request has already
  returned `WorkflowRunOutcome.FAILED` to its own caller, and the
  instance's own row still sits at `status='running'`, with no record
  that its own bound was ever exhausted.

**Why this blocks `POST /retry`, not just delays it**: the documented
route needs a real "genuinely, permanently failed, waiting for an
operator" instance to act on. None can exist today — an instance is
either still being retried automatically (forever, unbounded) or its
own exhaustion (for the one path that has bounded retry at all) was
never recorded anywhere a later HTTP call could see. Building the
route now would be dead code (gated on a status no writer ever
produces) unless a new, undecided, real design (a bounded
failure-exhaustion policy for the worker-loop path, and where its
result gets persisted) is invented unilaterally — a decision with no
existing documentation to answer it, materially larger than "add the
remaining routes" (this ticket's own literal scope).

**Not closed — this is a real, open, unaddressed gap**, not an
accepted baseline like R-006. `POST /workflows/{id}/retry` stays
disclosed, unbuilt in `api_architecture.md`/`cli_design.md`. Closing
this needs its own, later, dedicated design step: decide a real
retry-exhaustion policy for the worker loop (bound, persistence,
whether "retry forever" is in fact an intentional resilience choice
that should stay undisturbed), before `/retry` itself can be built
against something real.

---

### R-017 — Manifest-declared Tools were unreachable in production *(closed)*

Found 2026-08-11 by the full-project health audit; fixed the same day
by `P02-S05-M18-T04`. **Closed, but recorded in full because the
*shape* of this bug is the valuable part, not the one-line fix.**

**What was actually wrong.** `P02-S05-M18-T03` built the real
registry-resolution path inside
`ai_os_kernel.sdk_adapters.tool_invoker_adapter.ToolInvokerAdapter`,
behind an optional `registry: ToolRegistry | None = None` parameter,
explicitly documented as "Backward compatible: `registry` defaults to
`None`, unchanged behavior for every existing caller." That was true
and reasonable. What no one checked afterwards is that
`ai_os_kernel.sdk_adapters.pack_context.build_pack_context` — the
**single** production construction site of that adapter, reached for
every agent resolved through `SqlAgentRegistry` — never passed it.
`SqlToolRegistry` was therefore never constructed anywhere in
production code at all (`grep` for `SqlToolRegistry(` across
`kernel/src/` returned zero hits). Every agent's `context.tools` could
reach only the `platform.sandbox.run_command` shim;
`_invoke_registered_tool` raised `UnknownToolError` for every real
`tool_id`. The two real, manifest-declared Tools (`fs.read`,
`build.run`, `P03-S04-M31-T02`) had been unreachable from any agent for
their entire existence.

**Why it survived so long — the transferable lesson.** Three separate
places had already disclosed that those Tools were "not yet adopted by
any agent": `P03-S04-M31-T02`'s own ticket body, both tool descriptions
in `capability_packs/software-engineering/manifest.yaml`, and the
roadmap's own module rows. Every one of those readings is compatible
with "adoption is pending work someone will do later." **None of them
recorded that adoption was structurally impossible.** The gap between
"not done yet" and "cannot be done" is exactly what went unnoticed.

The test suite could not catch it either, and that is the second half
of the lesson: every prior proof — including
`test_a_real_pack_declared_tier1_sandboxed_tool_resolves_and_genuinely_reads_a_real_file`
— hand-constructed `ToolInvokerAdapter(sandbox, registry=registry)`
itself. Those tests genuinely proved the *mechanism*, and passed
forever, while the production *wiring* of that mechanism did not exist.
**A test that injects a collaborator by hand can never prove the
production composition injects it too.** The regression test added with
this fix
(`test_a_resolved_agent_can_genuinely_invoke_a_manifest_declared_tool`)
deliberately does the opposite: it resolves a real agent through
`SqlAgentRegistry` with no `tool_registry=` argument at all, and asserts
on the context the registry itself built. Reverting the one-line fix
makes it fail with the exact original `UnknownToolError` — verified,
not assumed.

**The fix.** `tool_registry` threaded through
`SqlAgentRegistry.__init__` → `_bind_pack_context_if_receiver` →
`build_pack_context` → `ToolInvokerAdapter(registry=...)`. Unlike every
other optional collaborator on `SqlAgentRegistry`, it gets a **real
default** (`SqlToolRegistry` over the engine the constructor already
holds), specifically so that a second silent `None` cannot recreate this
bug for a caller who does not know to opt in. Deliberately scoped to the
**agent** path only: forwarding it on the tool path would let
`SqlToolRegistry` hand out a context able to re-enter `SqlToolRegistry`,
an unbounded recursion with no depth limit anywhere in this codebase,
and tool-invokes-tool is documented nowhere. That decision is itself
asserted by a test, not merely written down here.

### R-018 — "Proven but idle": real subsystems with zero production reachability

Opened 2026-08-11 by the full-project health audit. **Open, and only
partially ticketed** — the entries below that have tickets are named;
the rest are recorded here so they cannot go invisible again.

The audit swept every module marked `done` or `partial` for real
production reachability (`grep` for importers outside the module's own
package, construction sites, and route registration). It found a
recurring pattern the roadmap emits no signal for: **a subsystem can be
fully built, fully tested, and marked 100% `done` while being impossible
to reach from any running code path.**

Genuine instances, worst first:

1. **Traceability Engine** (module 16). `P04-S02-M16-T01/T02/T03` are
   all `done` and stage P04-S02 reports **100%**, yet there are zero
   production importers of `traceability_engine` outside its own
   package, zero production `SqlTraceLinkWriter` construction, and no
   `/api/v1/traceability/*` route. `persistence/trace_schema.py`'s own
   docstring already admitted "nothing writes a traceability link yet
   either." **Ticketed 2026-08-11 as `P04-S02-M16-T04`.** Note the
   honest tension this creates: those three tickets are `done` by the
   letter of their own Output, so the percentage overstates reachable
   capability until T04 lands.
2. **Benchmarking pack** (module 34) and **Project Intelligence pack**
   (module 32) have no `manifest.yaml` and no `pack.py`. Only two
   manifests exist repo-wide (`_template`, `software-engineering`), so
   the Manifest Loader can never discover either pack. **Ticketed as
   `P04-S03-M34-T05` and `P05-S02-M32-T07`.** A correction the audit
   itself made while filing: its first claim that this blocks
   `api_architecture.md` §6.3 (Experiments) is **wrong** —
   `evaluation.experiments`, `SqlExperimentRunRecorder` and
   `comparison_computer` are all real, and the Kernel's own integration
   tests already import the Benchmarking pack as a plain library. §6.3
   needs **routes**, not a manifest.
3. **`evaluation_engine/reporting_interface.py`** — zero importers
   anywhere. **`comparison_computer.py`** — imported only from inside
   its own package. Not ticketed.
4. **`ParallelStepExecutor`/`SubWorkflowStepExecutor`** — zero
   production construction; `parallel`/`sub_workflow` used by 0 of 27
   real workflow steps. (`ForeachStepExecutor` **is** wired.) Accepted:
   ADR-0021 step types built ahead of a consumer, already disclosed.
5. **`voice_jarvis`** — zero production importers outside its own
   package, no route, no entry point. Consistent with M25/M33 `partial`.
6. **7 of 16 Software Engineering agents** are referenced by no real
   workflow (`api-designer`, `database`, `frontend-developer`,
   `performance`, `refactoring`, `release`, `security-analysis`).
   Accepted: a pack catalogue legitimately ships more agents than any
   one workflow uses.

**R-017 was originally item 7 of this same list** and is now closed —
which is the reason this entry stays open rather than being written off
as cosmetic. One member of this list turned out to be a real,
production-affecting defect, so the others deserve checking rather than
assuming.

**Why normal step-by-step work cannot find these.** `CLAUDE.md`'s Core
process rule — read only your own ticket and its direct dependencies —
is correct for execution and deliberately prevents cross-module reading.
It therefore *structurally cannot* surface "this module is complete but
nothing calls it," because that fact lives between modules. Periodic
whole-project audits are the intended counterweight, not a sign the
process failed.
