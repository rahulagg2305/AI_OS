# Risk Register — AI_OS

**Status:** Active, permanent · **Introduced:** Phase R2 (2026-07-31)

A real, permanent record of open risks. Hand-maintained (unlike the
generated roadmap views), but **entry-structured**: each risk is a fixed
row plus a short block. Never append narrative to an existing entry —
change its status field, or add a new entry.

Severity: **H** (can cause real harm or data loss) · **M** (can cause
significant rework) · **L** (contained).

**R-019 opened 2026-08-13** — the roadmap had 0 ready tickets while the
module table said 40% of the system did not exist. Substantially
addressed the same day: 19 partials re-verified, then Stage B planned
for its five deepest modules. **Ready-to-start 0 → 14.**
**R-006 re-measured 2026-08-13 (36 of 60 → 3 of 61 MUST untouched) after
a document-only audit found it 13 days stale.** Reviewed 2026-07-31
(R1–R4 final closeout); R-008 and R-009 closed 2026-08-01; R-014 opened and closed 2026-08-09; R-015 opened and closed
2026-08-09; R-016 opened 2026-08-10 and closed 2026-08-13; R-017 opened
and closed 2026-08-11; R-018 opened 2026-08-11; R-019 opened
2026-08-13.** 15 closed, **3 open** (R-006, an accepted baseline whose
count has now been genuinely recounted rather than carried forward;
R-018, the "proven but idle" sweep, now partly closed and — for its
remaining five packages — machine-checked rather than re-swept by hand;
R-019, the roadmap having run out of ready work, substantially addressed
by the 2026-08-13 Stage B planning step but not closed) plus R-001 (a permanent
standing rule, not a risk pending closure).

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
| R-006 | MUST requirements untouched — **re-measured 2026-08-13: 3 of 61, down from the 36 of 60 baseline** (A=0, B=0, C=0, D=1, E=1, F=1). Note "untouched" is a floor, not completeness: the honest figure is the 60% module-average now published in `STATUS.md` | H | **Open — substantially reduced, not closed**; FR-114 (replay), FR-058 (knowledge write-back — structurally blocked, no SDK Protocol), FR-097 (UI authorization gating) remain | Product owner, 2026-07-31; recounted 2026-08-13 |
| R-007 | `functional_requirements.md` status block drifts from reality | M | **Closed** 2026-07-31 | — |
| R-008 | No `AiOsError` hierarchy; error contract is per-module | M | **Closed** 2026-08-01 | — |
| R-009 | Audit log is schema-only — no writer, no hash chain | H | **Closed** 2026-08-01 | — |
| R-010 | CI type-checks only a subset of `[tool.mypy] files` | M | **Closed** 2026-07-31 | — |
| R-011 | `ai_os_kernel` ships no `py.typed` marker | L | **Closed** 2026-07-31 | Superseded by R-010 |
| R-012 | Ticket dependency graph had no recorded edges | M | **Closed** 2026-07-31 | — |
| R-013 | Two dependency edges were judgement calls | L | **Closed** 2026-07-31 | Both decided, no change |
| R-014 | No CI job ever ran any Capability Pack's own `tests/` | M | **Closed** 2026-08-09 | — |
| R-015 | Timing/scheduling test flakiness under real runners (local HTTP servers; worker-loop timing margins) | L | **5th occurrence FIXED 2026-08-13 (`P07-S03-M42-T03`)** — the deadline is now derived from the channel's own timeout rather than hand-picked, so the two cannot drift apart again; proven by A/B under identical real load (old failed, new 4/4). The occurrence was: `test_real_failure_and_completion_events_both_genuinely_notify` gives **two** sequential webhook deliveries a 2.0s deadline while `WebhookChannel`'s own per-delivery timeout is **5.0s**, so the assertion can fail while every component behaves as designed. 5/5 pass idle, fails under concurrent load. Previously **Closed** 2026-08-09; both worker-loop timing tests remediated (`P02-S01-M05-T16` 2026-08-11, 4th occurrence 2026-08-12); two further real root causes — an unclosed asyncio subprocess transport and 19 HTTP handlers never draining the request body — found and fixed 2026-08-12 | — |
| R-016 | No persisted terminal `failed` state; the worker loop retries every step failure unboundedly, forever | M | **Closed** 2026-08-13 (`P02-S01-M05-T17`) — bounded by a platform-default `RetryPolicy`, `failed` now genuinely written | Product owner, 2026-08-10 |
| R-017 | Manifest-declared Tools were unreachable in production — no caller ever passed a `ToolRegistry` | M | **Closed** 2026-08-11 (`P02-S05-M18-T04`) | — |
| R-019 | The roadmap ran out of work while the system was 60% built — 0 `todo` tickets across all 264, and the biggest real block (Stage B, 626 module-points) had none | M | **Open — substantially addressed 2026-08-13**: 19 partials re-verified (11 closed, 8 kept, 5 new `todo`), then Stage B planned for its five deepest modules (12 new `todo`, ~347 of 626 points, 7 flagged "expect a design fork"). Ready-to-start 0 → 14; ticket-weighted 96% → 92% as invisible work became counted. Closes when Stage B is planned in full — ~279 points across 11 further modules remain unticketed | Partial-ticket re-verification, 2026-08-13 |
| R-018 | "Proven but idle": real, tested subsystems with zero production reachability (items 1–3, 5 and 8 now closed; 5 further Kernel packages added 2026-08-11; item 8 added *and* closed 2026-08-12, and showed the sweep must measure per module, not per package) | M | **Open — items 4, 6 and 7 formally accepted as disclosed gaps; item 7's five packages re-verified 2026-08-13 and now enforced by `tests/contract/test_production_reachability.py`, which fails in both directions** | Health audit, 2026-08-11 |
| R-020 | A Task can be marked `done` without its verification ever having been run, and a ticket can claim behaviour the production code does not have. Found 2026-08-14 on the first Stage B batch, left uncommitted: `mypy --strict` failed (3 errors), a stale `assert duration_ms == 0` failed, and `P02-S06-M15-T11`'s own "the recorder reads outputs, then error" was false — `advance` built its error payload as `{type, message}`, so a blocking gate's measured duration was written and never read. Its integration test passed only because it hand-built an error dict production never produces | M | **Open** — all four defects fixed 2026-08-14 before landing, and a hand-built fixture standing in for a real produced shape is now the specific tell to look for. Uncommitted work is invisible to CI, so nothing caught any of it; closes when a `done` flip is gated on evidence rather than assertion | Verification step, 2026-08-14 |

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

### R-006 — MUST requirements untouched — **RE-MEASURED 2026-08-13: 3 of 61, down from 36 of 60**

Accepted as the real backlog baseline (product owner, 2026-07-31):
**36 of 60 MUST untouched, by stage A=0, B=1, C=8, D=11, E=7, F=9.**

**This entry sat unrevised for 13 days while dozens of Tasks closed.** A
document-only audit on 2026-08-13 flagged that as its own defect — a
severity-H risk whose headline count is 13 days stale is being stored,
not tracked — so it has now been genuinely recounted, not re-dated.

**Methodology, identical to the baseline's so the comparison is fair.**
Every MUST row in `functional_requirements.md` was re-read and
classified against current source, using that document's own `Stage`
column for the phase split. **"Untouched" means what it meant in 2026-07-31:
no real code anywhere implements any part of the requirement.** That is
also the exact test the 2026-08-11 audit applied when it reclassified
all of §5 and §6 from "untouched" to "partially built" on the strength
of backend code alone, with no UI in existence.

| Stage | Baseline 2026-07-31 | Now 2026-08-13 | Change |
|---|---|---|---:|
| A | 0 of 3 | **0 of 4** | 0 |
| B | 1 of 14 | **0 of 14** | −1 |
| C | 8 of 16 | **0 of 16** | −8 |
| D | 11 of 11 | **1 of 11** | −10 |
| E | 7 of 7 | **1 of 7** | −6 |
| F | 9 of 9 | **1 of 9** | −8 |
| **Total** | **36 of 60 (60.0%)** | **3 of 61 (4.9%)** | **−33** |

**The denominator moved too, and that is real, not a rounding trick:**
FR-117 (signed manifests) was added 2026-08-12 at Stage A, so there are
now **61** MUST requirements, not 60. `functional_requirements.md`'s own
header still says "60 MUST" and is stale by exactly that one row.

**The three still genuinely untouched, with what is missing:**

- **FR-114 (D) — workflow replay from the event log.** No replay
  mechanism exists anywhere. The run manifest it would replay *from* is
  real (`SqlRunManifestRecorder`); nothing consumes it to re-execute.
- **FR-058 (E) — write recovered knowledge back into the knowledge base
  with provenance.** Both halves exist separately and are not connected:
  the Project Intelligence pack has real provenance tagging
  (`provenance.py`, `P05-S02-M32-T06`) and the Kernel has a real
  knowledge writer (`persistence/knowledge_writer.py`), but no PI tool
  writes to it. A pack cannot import `ai_os_kernel`, and no SDK Protocol
  for knowledge write-back exists — a real structural blocker, not an
  oversight.
- **FR-097 (F) — show only actions the principal is authorized to
  perform.** No UI code gates actions anywhere in `dashboard/src`. The
  API enforces authorization on every route (`require_permission`), but
  that is enforcement, not presentation, and this requirement is a
  presentation requirement.

**Two marginal calls, disclosed rather than buried**, both resolved as
*touched* by the stated rule (real code implements part of it) with the
missing half named: **FR-093** (experiment comparison views) — the
comparison and per-run drill-down are real over HTTP
(`GET /experiments/{id}/comparison`, `.../runs`), no Dashboard view
exists; **FR-096** (stream live updates) — the WebSocket server is real
(`routes/stream.py`), the Dashboard does not consume it. If the product
owner prefers "presentation requirements need presentation code", both
become untouched and the total is **5 of 61**, not 3.

**A citation defect found while recounting, and fixed.** The 2026-08-11
correction table cited `replicate_management.py`, `cost_ceiling.py` and
`prompt_adaptation.py` under `evaluation_engine/`. Those three files do
not exist at that path — they are real, but live in
`capability_packs/benchmarking/src/ai_os_pack_benchmarking/`. The claims
were true, the paths were wrong; corrected in that table.

**What this number does NOT mean, stated plainly because it invites
exactly one misreading.** "4.9% untouched" is not "95% built". Untouched
is a floor — it asks only whether any code exists, not whether the
requirement is met. The honest completeness figure is the **60%
module-average** now published in `STATUS.md` alongside the
ticket-weighted 96%. R-006 measured whether the backlog had been
*started*; it has been. It never measured whether it is finished.

**Status: remains Open.** Three MUST requirements are still untouched
and the majority of the touched ones are partial, so the risk this entry
names — real v1 scope outstanding — has shrunk substantially but has not
gone. Re-measure at the same time as any future full-project audit,
using this same methodology.

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

**Third occurrence + remediation (2026-08-11, `P02-S01-M05-T16`)** — the
bar the entry above set for itself was met. CI run `31488950483`
(Integration tests job, the `P04-S01-M12-T12` experiments push) failed
on the real Ubuntu runner with the identical assertion —
`test_a_single_tick_genuinely_advances_multiple_real_instances_concurrently`,
`assert 0.456... < 0.4` — `gh run rerun --failed` again passed with no
code change. Three genuine CI occurrences across three separate pushes,
all the same tight 2x margin, none a real regression: this is now a
dedicated, root-caused fix rather than another disclosed retry.

**Root cause (measured, not guessed):** the assertion timed three real
0.2s concurrent steps against a `< 0.4s` bound, but the tick's *fixed*
per-instance overhead — three real DB round-trips to advance, a lease
acquire, the discovery query, event-loop scheduling — is itself ~0.25s,
*larger than the 0.2s step it was measuring*. That left only ~0.14s of
real headroom below 0.4s, so ordinary runner jitter could cross the
boundary while the code stayed genuinely concurrent (0.456s is still far
under the 0.6s a serialized tick would take). The signal was smaller
than the noise.

**Fix:** the step is now 0.5s and the bound is
`step_duration * instance_count * 0.7` (1.05s) against a 1.5s serialized
time, all as named constants with an explaining comment — the concurrent
result (~one step + overhead, ~0.75s) sits well below the bound, and a
genuinely serialized regression (1.5s) still trips it. The signal now
dominates the fixed overhead. **No production code changed** — the
worker loop's real concurrency guarantee is untouched; only the test's
timing margin widened. Proven: 5 consecutive `AIOS_ENV=ci` local runs of
the test pass, and the full worker-loop file passes 5/5. The
local-HTTP-server half of this entry (the original 2026-08-09 flakes) is
a distinct family, unchanged and still closed as before.

**Fourth occurrence — the *other* test, with a reliable local
reproduction (2026-08-12, `P02-S07-M17-T04`).** `P02-S01-M05-T16`'s fix
above remediated exactly one test,
`test_a_single_tick_genuinely_advances_multiple_real_instances_concurrently`.
Its sibling in the same file —
`test_run_worker_loop_genuinely_drives_a_real_instance_to_completion_on_its_own`,
the one the 2026-08-10 addendum recorded failing real CI once with
`assert ...RUNNING... == ...COMPLETED...` — was **never touched**, and it
still carries the same too-tight margin: it sleeps `0.05 * 8` (0.4s
total) and asserts the instance has reached `COMPLETED`, which needs two
real ticks at a 0.05s poll interval.

**New evidence this entry did not previously have: a deterministic local
trigger, and proof it is not a regression.** Running the whole
`tests/integration/workflow_engine` directory (33 files, ~4 minutes)
fails this test reliably on Windows, while the same test passes in
isolation and passes when only its own file runs (5/5). It was then
**reproduced on a genuinely clean tree** — `git stash push -u` to remove
every change from the step that found it, re-run the same directory:
identical result, `1 failed, 132 passed, 6 skipped`, the same test. So
the flake is independent of any code change, and specifically *not*
caused by the outbox insert that step added to the same completion path
(the plausible suspect, ruled out by measurement rather than argument).

**Fixed 2026-08-12** (remediation step, after being recorded above as
deliberately deferred from `P02-S07-M17-T04`).

**Root cause, measured over 12 real trials** against a real Postgres
container on an idle machine: completion took min 0.209s, median 0.234s,
max 0.282s against the bare 0.4s budget. The theoretical floor is 0.120s
(2 ticks x 0.05s poll + 2 x 0.01s step), so the genuine fixed overhead —
discovery query, lease acquire, advance, event-loop scheduling — is
**~0.089s per completion**. The observed maximum therefore sat at
**0.70x the bound on an unloaded machine**, leaving ~0.118s of headroom;
the whole `tests/integration/workflow_engine` directory reliably crossed
it. Identical pathology to the sibling: the margin did not dominate the
fixed overhead.

**Fix:** the blind `asyncio.sleep(0.05 * 8)`-then-assert-once was
replaced with a real condition wait (`_wait_for_completion`, bounded by
a named `_COMPLETION_TIMEOUT_SECONDS = 10.0` — ~35x the measured
maximum — polling every 10ms), the same `_wait_until` shape
`tests/integration/event_bus/test_outbox_relay.py` already establishes.
This is strictly stronger than widening the number: it still fails if
the loop genuinely never drives the instance to completion (the real
regression the test exists to catch), it cannot fail merely because the
machine was loaded, and it still finishes in ~0.23s because it returns
the moment the condition holds. **No production code changed.**

**Proven:** the test passes 5/5 consecutively, and
`tests/integration/workflow_engine` — the directory that reproduced the
failure on every prior attempt, including on a clean tree — now passes
**133 passed, 6 skipped, 0 failed**.

**Fifth occurrence family — two real root causes found and FIXED 2026-08-12.**
The `test_local_adapter.py` flake was investigated as its own issue and
turned out to be **two independent defects**, both real, both fixed —
not the "environment-only, accept it" outcome first suspected.

*Symptom.* Twice during full local Windows runs, an unrelated test in
`tests/unit/kernel/llm_gateway/adapters/test_local_adapter.py` failed —
a *different* test each time — with
`ValueError: I/O operation on closed pipe` raised inside CPython's own
`asyncio/windows_utils.py`. The file passes 27/27 in isolation.

**Root cause 1: an asyncio subprocess transport was never closed.**
Because an unraisable exception is raised during garbage collection,
pytest attributes it to whichever test happens to be running during that
GC pass — never to the code that created the handle, which is why it
appeared to strike innocent tests at random. Captured verbatim from a
real `tests/unit` run:

    Exception ignored in: <function _ProactorBasePipeTransport.__del__>
      File "asyncio/proactor_events.py", line 116, in __del__
        _warn(f"unclosed transport {self!r}", ResourceWarning, source=self)
      File "asyncio/proactor_events.py", line 80, in __repr__
        info.append(f'fd={self._sock.fileno()}')
      File "asyncio/windows_utils.py", line 102, in fileno
        raise ValueError("I/O operation on closed pipe")
    ValueError: I/O operation on closed pipe

asyncio is stating the defect outright — *unclosed transport* — and then
raising while formatting its own warning, because the pipe is already
closed. pytest listed
`tests/unit/kernel/sandbox/test_executor.py::test_execute_delivers_stdin_bytes_to_the_command`
among the active tests: `ai_os_kernel.sandbox.executor` is the only
production code that calls `asyncio.create_subprocess_exec`, and it never
closed the transport. **Fix:** close it explicitly once the process is
reaped (idempotent, exception-suppressed so a cleanup failure can never
fail a genuinely successful command).

*A disproved hypothesis, recorded so it is not retried.* A synthetic
script reproduced the leak (15 kill-path runs → 4 unraisable exceptions,
0 with an explicit close), but driving the **real** `LocalSubprocessSandbox`
across timeout, cap-breach, clean and `stdin=PIPE` paths — 44 runs —
produced 0 either way. That false negative briefly led to the fix being
reverted as unjustified. The real suite, not the synthetic harness, is
what settled it: the verbatim `unclosed transport` trace above came from
an actual `tests/unit` run.

**Root cause 2: every local HTTP test handler responded without draining
the request body.** All 19 `do_POST` handlers across 9 test files wrote a
response while the client's POST body still sat unread in the socket
receive buffer. Closing a socket in that state makes Windows send a TCP
**RST** rather than a graceful FIN, so the client can lose a response it
had already been sent. The adapter then classifies a connection failure
rather than the intended status — observed exactly as
`assert 'llm.network' == 'llm.rate_limited'` and
`assert <ErrorCategory.TRANSIENT> == <ErrorCategory.INFRASTRUCTURE>`.
This is the same *class* as this entry's original missing-`server_close()`
defect: a real protocol/resource bug in the fixtures, not ambient noise.
**Fix:** `self.rfile.read(int(self.headers.get("Content-Length") or 0))`
at the top of all 19 handlers — applied systemically across every
affected file, exactly as the original 23-call-site `server_close()` fix
was, not only to the tests seen failing.

Corroboration that this is the right cause: **every** file that has
flaked in this family appears in that list of 19 — `test_local_adapter.py`,
`test_anthropic_adapter.py`, `test_multi_provider_routing.py` (named in
this entry's own original 2026-08-09 investigation), and
`test_delivery_pipeline_knowledge.py`, whose single unexplained failure
earlier the same day had been recorded as an open observation.

**Proven, the same bar the original fix used:** `tests/unit` run **3
consecutive times** after both fixes — **1291 passed** every time, with
**zero** unraisable exceptions and zero `closed pipe`/`unclosed transport`
occurrences (warnings dropped 11 → 2). The two runs immediately before
the fixes each failed, on different tests
(`test_anthropic_adapter.py::…[401-…]` + `…[429-…]`, then
`test_local_adapter.py::…[429-…]`).

**One related observation, recorded and not fixed** (outside this step's
scope, and only reproducible under an artificial slowdown):
`test_anthropic_adapter.py::test_stream_delivers_real_events_incrementally_over_real_time`
failed under `-X tracemalloc=15` with
`assert (0.625 - 0.610) >= (0.05 * 3)` — streamed events arrived bunched
rather than spread out. Same R-015 family: a wall-clock assertion whose
margin does not dominate the environment's variability.

**The OTel compose-profile flake — root-caused and FIXED 2026-08-12.**
Worth reading as a correction: this entry previously offered two wrong
explanations before the real one was measured.

*What it was blamed on, and why both were wrong.* First recorded as
"Docker resource pressure after several container-heavy suite runs in
succession" — a local-laptop theory, which died when it failed on a
fresh Ubuntu CI runner (`31624893187`). Then escalated as an unexplained
CI-observable flake in the collector. **Also wrong: the collector was
never involved.** The CI log names the failing line outright:

    >   grafana_health = httpx.get(f"http://localhost:{grafana_port}/api/health", timeout=5.0)
    E   httpx.ReadError: [Errno 104] Connection reset by peer

*The real root cause, in two parts.* **(1) No observability service
declared a healthcheck.** `postgres` and `redis` do; `otel-collector`,
`prometheus`, `tempo`, `loki` and `grafana` did not.
`testcontainers.compose.DockerCompose.start()` already passes
`--wait` — but `docker compose up --wait` only gates on services that
*declare* a healthcheck, and treats one without as satisfied the moment
its container is *running*. So startup returned before Grafana was
serving. **(2) Proof #3 was the only assertion in the file left as a
one-shot read.** Proofs #1 and #2 poll, and the comment above proof #1
records this exact bug class being discovered and fixed *there* — the
fix was simply never applied to the third. Docker publishes the port
immediately, so the proxy accepts a connection and the connection then
dies because nothing is listening behind it yet.

*Measured, not argued.* Starting the profile without a readiness gate
and probing Grafana's published port immediately: the first probe fails
(`RemoteProtocolError: Server disconnected without sending a response`)
and Grafana becomes ready only after **11.9 seconds** — a real ~12s
window on an *idle* machine, wider on a loaded runner. That also
explains why two different exception spellings were observed
(`[Errno 104]` on Linux, `[WinError 10053]` locally,
`RemoteProtocolError` here): all three are the same transport-level
event, which is why the fix catches `httpx.HTTPError` rather than one
subclass.

*The fix, at both levels.* **Root cause:** `infra/docker-compose.yml`
now gives `grafana` a real healthcheck against `/api/health`
(`start_period: 15s`, since Grafana runs database migrations before
serving), so `docker compose up --wait` genuinely gates on readiness —
for this test *and* for any operator or orchestrator. **Second layer:**
proof #3 now polls with `_wait_until`, consistent with proofs #1 and #2.
The assertion itself is unchanged and still real (`database == "ok"`);
it simply no longer treats a startup window as a failure. **This is not
a longer sleep and not a retry wrapper around a broken assertion** — the
window is closed at its source, and the poll is defence in depth.

*Proof, both directions.* Without the gate: immediate probe fails, ready
after 11.9s. With it, from a genuinely cold start (volumes removed):
`up --wait` blocks **19.2s** until `grafana ... (healthy)`, and the
**first-attempt** probe returns `200 database=ok` with no retry. The
test itself passes **5/5 consecutive cold-start runs**, and the whole
`tests/integration/observability` directory passes.

*A methodological note worth keeping.* The first attempt at proving the
fix was invalid and was caught before publication: a `docker compose
down` ran from the wrong working directory, failed silently under a
redirect, and left the stack running — so `up --wait` "returned in 1.2s"
against an already-healthy stack. The 19.2s figure above is from a
verified-clean teardown. A proof that cannot fail is not a proof.

*The gap this left was closed the next day* (`P01-S05-M04-T07`,
2026-08-13). Prometheus, Tempo and Loki now declare healthchecks against
their own documented readiness endpoints, so `up --wait` gates on the
whole profile. **One service genuinely cannot**: `otel-collector`'s
image is distroless — no shell, no `wget`/`curl`/`nc`, verified by
inspecting the image — so no probe can execute inside it at all. That is
a real constraint, recorded in the compose file where a reader will look
for the missing healthcheck, not an oversight. Each command was checked
against its own image rather than copied: Loki ships busybox at
`/busybox/wget` rather than on `PATH`, and a copied command would have
marked it permanently unhealthy and hung `up --wait` — the exact failure
mode a careless systemic fix would have introduced while claiming to
prevent one.

**R-014 recurred in a second location — found and fixed 2026-08-13
(`P06-S04-M38-T01`).** The entry below records that
`capability_packs/*/tests/**` sat outside root `pyproject.toml`'s
`testpaths = ["tests"]` and no CI step ever named it, so those tests had
never run. **The identical defect existed for `tools/aios/tests`, and
was missed when R-014 was closed** — the fix added a step for pack tests
and stopped there, rather than asking what *else* lives outside
`testpaths`.

*Real impact.* The CLI's own suite — **49 tests** at the time of
discovery, covering pure logic, a real local uvicorn server, and one
real Postgres end-to-end pack lifecycle driven entirely through the CLI
— had never executed in CI. Any regression in `aios` would have gone
undetected by every green build.

*Fixed the same way R-014 was*, deliberately: a `pytest tools/aios/tests`
step in the `unit` job, guarded by the same
`hashFiles(...) != ''` condition, added directly beneath the pack-tests
step so the two are read together. Proven before adding: all 49 collect
and pass through that exact entry point.

*The generalisable lesson, worth more than the fix.* Closing a
"tests exist but never run" finding for one directory does not close it
for the repository. Anything outside `testpaths` is invisible by
default, and nothing warns you. The remaining directories were checked
at the same time — `tests/**` (the root suite), `capability_packs/*/tests`
and `tools/aios/tests` are now the complete set of test locations, and
all three are named by a CI step.

**A documented CLI convention that had never been implemented —
recorded and then FIXED 2026-08-13 (`P06-S04-M38-T01`).**
`cli_design.md` §4's conventions table has always stated that
destructive commands "require `--yes` or an interactive confirmation".
**No command in the real CLI implemented it**, which surfaced when
`aios experiment run` shipped able to synchronously execute one real
workflow per variant × replicate — every one a real, billable LLM call —
with no prompt whatsoever.

*Why it was not fixed in the same step that found it.* Gating
`experiment run` alone would have made the convention arbitrary: a user
would learn that running an experiment needs confirmation while
cancelling a workflow does not. The whole set had to be decided at once.

*The decision was the product owner's, and deliberately so.* What the
codebase settles is that exactly **eight** commands mutate server state
(POST/PATCH) — `approve decide`, `config set`, `experiment create`,
`experiment run`, `pack activate`, `pack deactivate`, `workflow start`,
`workflow cancel`. Which of those count as "destructive or high-impact"
is a judgement about users, not a fact derivable from source, so three
real options were presented (irreversible-or-costly / anything that
changes the platform / every mutating command) and the product owner
chose **irreversible or costly**:

| Gated | Why |
|---|---|
| `workflow cancel` | one-way terminal transition |
| `pack deactivate` | removes a live capability |
| `approve decide` | permanent, attributable, governance-critical (R-001) |
| `experiment run` | spends real money, synchronously |

**A disclosed consequence of that line, accepted explicitly rather than
discovered later:** `workflow start` triggers real agents making real
LLM calls, so one money-spending path remains unprompted. It was
excluded as the CLI's primary verb, where a prompt on every invocation
is friction that teaches users to reflexively pass `--yes`.

*Scriptability was the sharp edge.* This CLI exists to compose in
scripts, so a prompt on a pipe or in CI would block forever on stdin
that never answers. A non-TTY without `--yes` is therefore a real usage
error (exit 2) that names the flag, never a prompt. The test that proves
this **would hang rather than fail** if the gate ever called
`typer.confirm` unconditionally — which is precisely the regression it
exists to catch.

*Proven both ways.* Adding the gate immediately broke five existing
tests that drive these commands (`assert 2 == 3`, `assert 2 == 0`),
including the real end-to-end Postgres pack-lifecycle test — real
evidence the gate genuinely intercepts, not merely that it compiles.
Those now pass `--yes`. Nine new tests cover the gate itself, and
disabling `require_confirmation` was verified to fail all four
"refuses rather than hanging" cases before restoring it. 58 CLI tests
pass.

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

### R-016 — No persisted terminal `failed` state; the worker loop retries every step failure unboundedly, forever *(closed)*

**CLOSED 2026-08-13 (`P02-S01-M05-T17`).** The worker loop is now bounded and `failed` is genuinely written; the history below is preserved unchanged, and the resolution follows it.

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

**Resolved 2026-08-13 (`P02-S01-M05-T17`) — the dedicated design step
this paragraph called for.** The paragraph above read "Not closed — this
is a real, open, unaddressed gap… closing this needs its own, later,
dedicated design step"; that step happened, and its findings are worth
recording because two of them narrowed the question substantially before
any decision was needed.

**What the investigation found already decided.** The framing this
finding had acquired — "bounded attempts vs a time budget vs an
operator-only transition" — was **already settled by documentation**:
`error_handling_retry.md` §4 requires retries to be "bounded (maximum
attempts + maximum duration)", both and not either, and `RetryPolicy`
has modelled exactly that from the start and is already honoured by
`run_to_completion`. The shape was never open. It also found that the
data needed to enforce a bound *across polls* already existed:
`workflow_steps` carries `attempt` and `started_at`, and
`record_failed_attempt` has been writing failed rows since
`P02-S01-M05-T06`. **No schema change and no migration were required** —
which is why this closed in one step rather than the larger one feared.

**What was genuinely open, and went to the product owner.** Two
questions, neither derivable from source:

1. *What bounds a definition that declares no `retryPolicy`?* It is
   optional and **2 of the 3 real definitions declare none** — exactly
   the ones looping forever. Chosen: a **platform default** (2 attempts
   / 60s), overridable per definition, deliberately mirroring the one
   real policy any definition actually declares (`se.delivery_pipeline`)
   rather than inventing a figure. A retry is a billable LLM call, so
   the bound is also a cost ceiling.
2. *What does exhaustion produce?* Chosen: always `failed`. The
   alternative — honouring `failureHandling.onError` (`halt`/`escalate`),
   a **required field on every definition that no code has ever read** —
   was rejected as materially wider, since `escalate` has no defined
   meaning and inventing one would be exactly the unilateral design this
   finding existed to prevent.

**`failureHandling.onError` — the gap this entry disclosed rather than
absorbed — is now itself CLOSED (2026-08-13, `P02-S01-M05-T18`).** It
was a required field on every definition that no code had ever read, so
a definition could declare `escalate` and silently get `halt`, with no
error, no warning and no way for its author to find out. Product-owner
decision: close the vocabulary to `halt`, the only behaviour that
exists, and **reject `escalate` at load time rather than implement it**.
No document anywhere defines what `escalate` should do,
`error_handling_retry.md` §7 states human escalation does not exist, and
inventing semantics would have been exactly the unilateral design this
disclosure existed to prevent. Two alternatives were put up and declined:
tagging the outbox payload with an escalation discriminator (invents a
routing semantic), and transitioning to `waiting_for_human` (materially
larger, and non-terminal — it would have reopened the very rediscovery
loop R-016 closed). All three real pack workflows already declared
`halt`, so no production definition changed meaning. The sweep also
found a real, previously-invisible defect the old "must not be empty"
check could never catch: `bootstrap.py`'s demo definition declared the
key as `on_error`, not `onError`, and 32 test fixtures declared the
unimplemented `escalate`.

**What this unblocked, and what has since been built.** `POST
/workflows/{id}/retry` is **built as of 2026-08-13
(`P06-S01-M36-T05`)** — closing R-016 made `failed` real and, in the
same stroke, created a dead end where a workflow could fail for good
with no operator recourse. That route is the way out, and it needed one
thing this entry did not anticipate: a **retry epoch**
(`workflow_instances.retried_at`, migration `0039`). A `failed` instance
has by definition already spent both bounds this entry introduced, so a
retry that merely flipped the status would have granted exactly one
further attempt regardless of the declared `retryPolicy`. The epoch
makes `step_failure_stats` count only failures after the retry, so the
policy applies again in full. The CLI's `workflow retry` is **still not
built** — the route it needs now exists. `NotificationService`'s `failure` category is no longer
merely "available" — as of 2026-08-13 (`P02-S01-M05-T18`) `mark_failed`
writes a real `workflow.failed` row to `platform.event_outbox` inside
its own transaction, mirroring `workflow.completed` exactly, so that
category has a real producer for the first time and the whole ADR-0012
chain is proven end to end from the real worker loop's own retry
exhaustion.

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

1. **Traceability Engine** (module 16) — **the writer half is now
   closed (`P04-S02-M16-T04`, 2026-08-11); the read half is not.** When
   this risk opened, `P04-S02-M16-T01/T02/T03` were all `done` and stage
   P04-S02 reported 100%, yet there were zero production importers of
   `traceability_engine` outside its own package, zero production
   `SqlTraceLinkWriter` construction, and no `/api/v1/traceability/*`
   route — `persistence/trace_schema.py`'s own docstring admitted
   "nothing writes a traceability link yet either." T04 gave the writer
   its first real production call site: `routes/delivery_pipeline.py`
   now records a real `workflow_run --produced--> documentation` link
   (bootstrap-wired `app.state.trace_link_writer`), proven end to end
   against real Postgres through the real `build_app()` composition, with
   a test that fails if the wiring is reverted. **The read side landed
   too (`P04-S02-M16-T05`, 2026-08-11): `GET /api/v1/traceability/impact/
   {id}` and `.../coverage` are real thin routes over the already-real
   impact/coverage queries, proven over writer-seeded rows through the
   real `build_app()` composition.** This instance of R-018 is now
   **closed on both halves** — a real writer feeds real rows and a real
   HTTP consumer can read them. The only remaining Traceability gap is
   `GET /traceability/query` (the raw link graph, a separate shape
   decision) and any writer beyond the one delivery-pipeline link type —
   real, disclosed, smaller follow-ups, not the systemic "100% done yet
   totally unreachable" hollowness this item opened for.
2. **Benchmarking pack** (module 34) and **Project Intelligence pack**
   (module 32) had no `manifest.yaml` and no `pack.py`, so the Manifest
   Loader could never discover either. **Project Intelligence is now
   closed (`P05-S02-M32-T07`, 2026-08-11): a real, schema-valid
   `manifest.yaml` declares all five of its real Tools, and they
   genuinely register and resolve through the real `SqlToolRegistry`
   (proven end to end, incl. a real `language.detect` resolve+run) — a
   real, additive payoff, since `P02-S05-M18-T04` (R-017) had already
   wired the registry into production, so a declared Tool is now
   invocable, not merely catalogued. Two of the five (`architecture.
   recover`, `documentation.generate`) needed a real `inputSchema`
   Pydantic model added to be declarable at all (the schema requires
   one per tool); those were added, matching the existing 3-tool
   precedent, `execute` unchanged.** **Benchmarking is now closed too
   (`P04-S03-M34-T05`, 2026-08-12), and the honest framing matters: it
   is a *discoverability* fix, not an invocability one.** A real,
   schema-valid `manifest.yaml` means `ManifestLoader.scan()` finds this
   pack for the first time — it was previously absent from discovery,
   from health and status reporting, and could never become a
   `catalog.packs` row. But the pack still declares no agent, tool or
   workflow, because it genuinely has none: its four modules are pure
   validation and planning functions the Kernel's own tests import
   directly, not Tool entrypoints. Declaring them would have meant
   building entrypoints, input/output models and trust tiers that do
   not exist — new capability, not this ticket's scope. So unlike
   Project Intelligence, **nothing became invocable**, and the
   near-hollowness this entry predicted is real and is recorded in the
   manifest's own header rather than quietly glossed. No `pack.py`
   either: `manifest.schema.json`'s `allOf` requires `entryPoint` only
   alongside `agents`/`workflows`, proven by a test that adds an agent
   and watches the schema reject the manifest. A correction the audit
   itself made while filing: its first claim that this blocks
   `api_architecture.md` §6.3 (Experiments) is **wrong** —
   `evaluation.experiments`, `SqlExperimentRunRecorder` and
   `comparison_computer` are all real, and the Kernel's own integration
   tests already import the Benchmarking pack as a plain library. §6.3
   needs **routes**, not a manifest.
3. **`evaluation_engine/reporting_interface.py`** and
   **`comparison_computer.py`** — **fully closed (`P04-S01-M12-T14`,
   2026-08-11).** History: `T12` gave `evaluation.experiments` its first
   writer (`POST /experiments`); `T13` gave `experiment_runs` its first
   production caller (`POST /experiments/{id}/run`) — a correction to the
   `T12` note here: `experiment_runs` was never writer-less
   (`SqlExperimentRunRecorder`, `P04-S03-M34-T02`, was its tested writer);
   it lacked a *caller*. `T14` now exposes the readers themselves over
   HTTP: `GET /experiments/{id}/comparison` calls `SqlComparisonComputer`
   directly, and `GET /experiments/{id}/runs` a new `SqlExperimentRunReader`.
   So both readers now have real production callers, over real rows a real
   run produces — this instance of R-018 is closed end to end. (The
   comparison route is not *wired into a Dashboard view* yet, and the
   Benchmarking pack's own reporting/presentation layer is separate — but
   that is downstream product surface, not the "100% done yet unreachable"
   hollowness this item opened for.)
4. **`ParallelStepExecutor`/`SubWorkflowStepExecutor`** — zero
   production construction; `parallel`/`sub_workflow` used by 0 of 27
   real workflow steps. (`ForeachStepExecutor` **is** wired.) Accepted:
   ADR-0021 step types built ahead of a consumer, already disclosed.
5. **`voice_jarvis` — CLOSED 2026-08-13 (`P06-S06-M33-T02`).** When
   this entry opened it had zero production importers outside its own
   package, no route and no entry point: a whole subsystem, real and
   tested, unreachable from any running process. `POST
   /api/v1/voice/intent` is now its first real production entry point —
   a thin route assembling the already-real `PlatformIntentRouter` from
   already-bootstrapped collaborators, proven end to end through the
   real `build_app()` composition against real Postgres (5 tests), with
   a real `check_health` request genuinely returning the real
   `HealthService`'s own readiness report. `routes/voice.py` is now a
   real production importer, machine-checked by
   `tests/contract/test_production_reachability.py`.
   **The contract was invented, and that is disclosed, not glossed:**
   no document — not `voice_architecture.md`, not `api_architecture.md`
   §6 — specifies any voice endpoint, so path, request shape and status
   mapping were product-owner decisions (2026-08-13), each reusing an
   existing route precedent rather than inventing a second convention.
   **`speech_gateway` is deliberately *not* closed by this** and stays
   in item 7's table: the route accepts an already-structured intent,
   never audio. Wake word, STT and TTS remain genuinely unbuilt, so
   M25 stays `partial` for real reasons.
6. **7 of 16 Software Engineering agents** are referenced by no real
   workflow (`api-designer`, `database`, `frontend-developer`,
   `performance`, `refactoring`, `release`, `security-analysis`).
   Accepted: a pack catalogue legitimately ships more agents than any
   one workflow uses. **Re-verified 2026-08-11: still exactly 7 of 16** —
   only 9 distinct `agentId:` values are declared across every real
   workflow YAML (`architecture`, `build`, `code-review`,
   `documentation`, `git-push`, `lint`, `qa-test`,
   `requirements-analyst`, `technical-planner`). The three that *appear*
   to be referenced (`database`, `frontend-developer`, `release`) match
   only inside YAML **comments**, not real step declarations.
7. **Five further Kernel packages have real, tested code that no
   production composition constructs — added 2026-08-11 by the
   full-project audit, which swept all 30 kernel subpackages for
   production importers outside their own package.** Each was already
   disclosed individually in `feature_inventory.md`; what was missing is
   that they were never collected *here*, so this entry understated the
   real size of this risk class by five. None is a misdocumented module;
   this is an aggregation fix.

   | Package | Real code | Production importers | Where it is already disclosed |
   |---|---|---|---|
   | `caching` | 4 files (`ResponseCache`, `RedisSettings`) | **0** — `ResponseCache(` is never constructed in production | module 23: "Not wired into `llm_gateway.gateway`'s real call path yet" |
   | `document_processing` | 7 files, 8 classes | **0** | module 26: "not wired into any real production composition/route" |
   | `speech_gateway` | 5 files, 14 classes | **0** | module 25: "no real caller exists" |
   | `storage_service` | 3 files (`LocalFilesystemArtifactStore`) | **0** | module 21: "nothing in a real Kernel composition constructs this store yet" |
   | `memory_manager` | 1 file, **0 classes** — a docstring-only `__init__.py`; the real store is `persistence/memory_writer.py`'s `SqlMemoryStore` | **0** | `memory_manager.md`: "`memory_manager/` itself is still a docstring-only `__init__.py`" |

   **Re-verified 2026-08-13, and no longer only in prose.** All five
   were re-swept with an `ast`-based importer analysis (not `grep`: every
   apparent hit in the earlier sweeps was a docstring cross-reference
   like ``:class:`~ai_os_kernel.caching.response_cache.ResponseCache```,
   which a regular expression cannot distinguish from a real import).
   Result: **0 real production importers each**, unchanged. Control
   measurements from the same sweep, to show the detector detects:
   `workflow_engine` 35, `event_bus` 6, `notification` 1, and
   `voice_jarvis` 1 — that last one being item 5, closed the same day.

   That sweep is now a **checked invariant**, not a claim:
   `tests/contract/test_production_reachability.py` re-executes it on
   every CI run and fails in *both* directions. Wiring one of these five
   is good news and still fails the test, because the documentation here
   would then be wrong and must be updated in the same step. This
   directly addresses why R-018 kept needing rediscovery: three hand
   sweeps in two days, one of which (2026-08-11) got the answer wrong by
   measuring per package instead of per module, and every result living
   only in prose that no build could falsify.

   **Each of the five is formally re-affirmed as a disclosed, accepted
   gap — none can be wired without new feature development**, which is
   why none was wired here: `caching` needs `ResponseCache` in the
   `llm_gateway` call path, a behaviour and cost change requiring Redis;
   `storage_service` and `document_processing` both need an ingestion
   caller that does not exist; `speech_gateway` needs STT/TTS (see item
   5); and `memory_manager` is a docstring-only `__init__.py` with no
   classes at all — "wiring" it would mean building promotion logic,
   which `feature_inventory.md` already tracks as separately unbuilt.

   `bootstrap.py`'s apparent mentions of `caching` and `memory_manager`
   are **comments only**, not wirings. One package the same sweep flagged
   was checked and cleared as a false positive: `entrypoints` has zero
   importers because it *is* the top of the call graph — it is genuinely
   wired via `deploy/entrypoint.sh` (`exec uvicorn
   ai_os_kernel.entrypoints.api:app`, `exec python -m
   ai_os_kernel.entrypoints.worker`).

8. **The Outbox Relay and `platform.event_outbox` — CLOSED 2026-08-12
   (`P02-S07-M17-T04`).** Found while choosing the next step, and worth
   recording because **the 2026-08-11 sweep above structurally could not
   have caught it**: that sweep counted production importers per
   *package*, and `event_bus` is a wired package (`bus.py` has real
   publishers and subscribers). The idle code was two modules *inside*
   it, so a package-granularity query reported the package as reachable
   and moved on. Real code, zero production reachability, stated
   outright in the codebase's own docstrings:
   `ai_os_kernel.event_bus.__init__` said "No writer for
   `platform.event_outbox` exists yet", and `event_bus.md` §4 said "no
   continuously-running relay loop wired into `bootstrap.py` yet
   (`run_outbox_relay_loop` exists, unwired)". So `OutboxRelay` (4 real
   Postgres tests), its `run_outbox_relay_loop`, and the
   `platform.event_outbox` table and migration were all real, tested,
   and unreachable — the table had never held a production row.

   Closed by giving the table its first real writer
   (`outbox_writer.write_outbox_event`, joining the caller's
   transaction) and starting the relay loop in `bootstrap.py`. The
   payoff is the same shape as item 3's: a *second* idle component was
   waiting downstream — `NotificationService`'s `workflow.completed`
   category had been subscribed but unreachable since it was built, and
   is now genuinely reachable in a configured deployment.

   **Lesson for the next sweep:** measure reachability per *module*, not
   per package. A package can be wired while carrying dead modules, and
   this is now a confirmed instance, not a hypothetical.

**R-017 was originally the last item of this same list** (numbered 7 before the 2026-08-11 additions above renumbered it) and is now closed —
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

---

## R-019 — The roadmap ran out of work while the system was 60% built

Opened **2026-08-13** by the partial-ticket re-verification. **Open.**

**The finding.** All 264 tickets were `done`, `partial` or `blocked` —
**zero `todo`**. `STATUS.md`'s own Ready-to-start section read
"0 Task(s)". No module in the project had a ready ticket, and Stage B —
the 626 unticketed module-percentage-points that the 2026-08-13
document-only audit identified as the single biggest remaining block —
had nothing open at all except two product-owner-gated `blocked`
tickets. The ticket system said the work was finished; the module table
said 40% of the system did not exist.

**Why this is a risk and not just an empty queue.** A roadmap with no
ready work cannot be picked up. Every subsequent step would have had to
either invent scope on the spot or re-derive the backlog from scratch,
and the previous step's audit showed exactly how that goes: numbers get
carried forward instead of recounted. This is the tracking analogue of
R-018 — real work that no instrument could see.

**Partly addressed the same day.** Re-verifying all 19 `partial`
tickets closed 11 whose stated gaps were provably stale or formally
deferred, kept 8 with real unresolved gaps, and re-scoped the genuine
remainder into 5 new `todo` tickets. Ready-to-start is **0 → 5**.

**Stage B planning done 2026-08-13 — the substantive half is now
addressed.** The five deepest Kernel gaps had no ticket of any status;
each module's real code and its own architecture document were read to
establish what is genuinely missing, and the result is **12 new
executable `todo` tickets**:

| Module | New tickets | Verified gap they close |
|---|---|---|
| Memory Manager 18% | `M10-T04`, `T05` | The package is one 18-line docstring-only `__init__.py` with zero classes; `MemoryService.write()` (§6's only mediated write path) does not exist; `provenance` is write-through, never computed |
| Storage Service 25% | `M21-T02`, `T03` | No `StorageService` Protocol; zero production importers; no S3 adapter |
| Caching 30% | `M23-T03`, `T04` | No `Cache` Protocol, no in-memory adapter; `ResponseCache` never called by production |
| Knowledge Manager 40% | `M09-T07`–`T09` | ~~`IndexingService` produces no embeddings~~ (**closed 2026-08-14, `M09-T06`** — real opt-in in-line embedding, proven vector-searchable end to end); `index_document_file` has no production caller **and does not pass the three embedding parameters through, so nothing enables embedding in production yet**; no Access/Filter Layer; no Version Manager |
| Quality Gate Engine 40% | `M15-T10`, `T11` | The package emits zero logs/metrics/spans (§5's Observability Hook); `gate_results.duration_ms` is honestly always `0` |

Ready-to-start went **5 → 14**. **Ticket-weighted completion fell 96% →
92%** (258 of 269 → 258 of 281) — planning real work lowers that
number, because it converts invisible work into counted work. The
module-average stayed at 60%, correctly: nothing was built.

**Seven of the twelve carry an explicit "expect a design fork" warning**
in the ticket itself, so a batch-execution step stops and asks instead
of inventing scope: `M09-T06` (embedding cost/latency), `M09-T07`
(what triggers ingestion), `M09-T08` (no knowledge permission exists),
`M09-T09` (what a new index generation means — the largest),
`M10-T04` (Kernel-local vs SDK Protocol), `M21-T02` (which producer
writes artifacts), `M21-T03` and `M23-T04` (a new dependency; caching
changes billing).

**Still open, deliberately.** These 12 cover the five deepest modules,
roughly 347 of Stage B's 626 remaining module-points. The other ~279
points across the remaining 11 Stage B modules are still unticketed,
and the two `blocked` tickets remain product-owner-gated. This risk
closes when Stage B is planned in full, not when it is planned in part.

---

## Decisions taken and gaps formally deferred — 2026-08-13

A single step (product-owner directed) went through every open issue on
record and forced each to a real outcome, so that none stays in the
half-state — "known, unresolved, rediscovered every few sessions" — that
made R-016 and R-018 cost as much as they did. Recorded here because
four of these are decisions, not code, and a decision that lives only in
a commit message is a decision that will be re-litigated.

**Resolved.**

- **`failureHandling.onError`** → vocabulary closed to `halt`;
  `escalate` rejected at load time rather than implemented. Full
  reasoning and the two declined alternatives: R-016 above.
  (`P02-S01-M05-T18`.)
- **`workflow.failed` was durable but not outboxed** → `mark_failed`
  now writes the domain event in its own transaction, giving
  `NotificationService`'s long-subscribed `failure` category its first
  real producer. (`P02-S01-M05-T18`.)
- **`GET /usage/cost` duplicate surface** → the documentation is
  amended, not the code. The row is removed from `api_architecture.md`'s
  endpoint list and points at the already-real
  `GET /api/v1/evaluation/cost-and-quality`, which serves that exact
  capability over the identical `llm_calls` data. Building an alias was
  declined as duplicate surface; renaming the existing route was
  declined because it would break a path the Dashboard already consumes
  for no capability gain. **The documented endpoint count drops by one**
  — a real, deliberate contraction of the published contract.
- **`GET /gates/trends` timestamp** → `evaluation.gate_results` gained a
  server-defaulted, indexed `created_at` (migration
  `0038_gate_results_created_at`), exactly as `0035` did for `llm_calls`
  with the identical gap. Two no-migration alternatives were measured
  against real code and declined: joining `workflow_instances` yields
  `NULL` for precisely the runs a blocking gate halted, and decoding the
  ULID already inside `result_id` gives the true time but cannot be
  grouped in SQL at all. **The route itself is deliberately not built**
  — the blocker is removed, the work is not done. (`P04-S01-M12-T16`.)
- **Voice entry point** → built; see R-018 item 5. (`P06-S06-M33-T02`.)

**Formally deferred, with reasoning.**

- **PDF and DOCX parsing.** Both need a real new third-party runtime
  dependency (`pypdf`, `python-docx` or equivalent). Declined for now on
  one concrete ground, not general caution: `document_processing` has
  **zero production importers** (R-018 item 7, re-verified 2026-08-13
  and now machine-checked), so adding two supply-chain dependencies
  would extend the platform's licence and vulnerability surface for code
  no running process can reach. Routing extraction through the existing
  Docker sandbox was also considered and declined as far larger than an
  adapter — it needs an image, an I/O contract, and would make document
  parsing depend on Docker being available. The honest
  `UnsupportedDocumentFormatError` naming both formats stays, and the
  `DocumentParser` Protocol already exists so an adapter can slot in
  unchanged. **Revisit when a real ingestion caller exists** — at which
  point the dependency buys something reachable.
