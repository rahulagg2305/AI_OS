# Standing Rules – AI_OS

**Status:** Active | **Last Updated:** 2026-07-30 (**5 efficiency rules added** — a concrete file-splitting size threshold, scoped-by-default test/lint runs with a periodic full-sweep cadence, trimmed report evidence, no re-verification of subsystems a step's diff didn't touch, and batched doc-tracker updates; see Efficiency discipline below. Prior, same day: 4 permanent reporting rules added: coding-standards confirmation, evidence-based claims, the phase/%/remaining-areas status block, and the optional efficiency note — see Reporting discipline below and `docs/process/reporting_format.md`. Prior: 2026-07-29, the Platform SDK growth gate is **lifted** — a hard product-owner decision, revising the gate's own previously-recorded lift condition; see below)

The process rules this project has actually operated under, distilled from how every step so far has actually been approved and executed. These are binding unless the product owner explicitly says otherwise for a given step.

---

## ✅ Capability Pack growth gate — LIFTED (product-owner decision, 2026-07-29)

**The gate recorded below on 2026-07-28 is now lifted.** A new agent may be added to the Software Engineering Capability Pack, and a new Capability Pack may be added, subject to every other standing rule in this document (scope discipline, documentation-first, real verification, etc.) — none of which this gate ever suspended.

- **Why it lifts now, not at step 15 as originally recorded:** `platform_sdk_v1_scope.md` step 14 (2026-07-29) completed the real substance the gate's own original condition named — "a real, migrated, and verified pack, not merely an importable SDK." All 5 real agents (`qa-test`, `requirements-analyst`, `architecture`, `build`, `documentation`) and the pack's own `CapabilityPack` entry point (`pack.py`) are migrated onto `ai-os-sdk`; `pack_contract_suite` check 7 (forbidden imports) now enforces **unconditionally, with zero exceptions** against this pack — `pack_contract_waiver.yaml` is deleted outright, not merely emptied, for the first time in this project's history. This is a **revised product-owner decision**, not a discovery that the old condition was secretly already satisfied: the original 2026-07-28 text below explicitly said "the gate lifts only after step 15," step 15 being the remaining 8 (of 9 total) `pack_contract_suite` checks beyond check 7. The product owner's 2026-07-29 decision is that a fully-migrated pack with unconditional import-boundary enforcement is sufficient to lift the *growth* gate now; the remaining 8 checks (step 15) are real, valuable completeness work, tracked and still to be done, but are no longer treated as a precondition for this specific gate.
- **What this does not change:** step 15 itself is still scoped and still the next, last step of `platform_sdk_v1_scope.md` — nothing about it is skipped or downgraded in importance, only decoupled from this particular gate.
- **What was grandfathered while the gate was active, now moot:** the five Software Engineering pack agents and the pack itself needed no retrofitting before the SDK existed — they are now genuinely, fully migrated regardless.

**Original gate text, recorded 2026-07-28, preserved verbatim below for the historical record — superseded by the lift above, not deleted, so a future reader can see exactly what changed and why:**

> **No new agent may be added to any Capability Pack, and no new Capability Pack may be added, until a real Platform SDK package (`ai-os-sdk`) exists.**
>
> - This is a **product-owner decision**, not an engineering guideline — it does not bend for "just this once," a small agent, or a step that seems otherwise well-scoped.
> - **Why:** the Software Engineering pack's direct-Kernel-import compromise (documented as a "dated exception" in `docs/03_architecture/capability_framework/capability_pack_contract.md`) was tolerable as a bounded, one-time exception for the pack that already exists. It stops being bounded the moment a *second* pack or a *sixth* agent repeats it — at that point the "temporary" exception has quietly become the load-bearing pattern, with no SDK ever built to replace it.
> - **What is grandfathered, unaffected by this gate:** the five existing Software Engineering pack agents (`requirements-analyst`, `architecture`, `build`, `qa-test`, `documentation`) and the pack itself. Nothing about them needs to change today, and this gate does not require retrofitting them before the SDK exists.
> - **What is blocked:** a sixth SE-pack agent; any code for `project_intelligence/`, `voice_jarvis/`, or `benchmarking/` (all currently empty); any other new pack.
> - **Before starting any step that would add an agent or a pack**, check `docs/03_architecture/capability_framework/capability_pack_contract.md`'s Platform Interaction Rules and `docs/19_roadmap/feature_inventory.md` module 27 (Platform SDK) first — if module 27 is still not built, that step is out of scope regardless of what else was approved.
> - **What lifts this gate:** a real, migrated, and verified pack — not merely an importable SDK. `docs/03_architecture/platform/platform_sdk_v1_scope.md` (scoped 2026-07-28) is the approved-able 15-step plan: 8 SDK-build steps, 6 agent-migration steps, 1 compliance-completion step. **The gate lifts only after step 15** (the full `pack_contract_suite` passing against the migrated Software Engineering pack) — an SDK existing with the pack not yet migrated onto it (steps 1–8 done, 9–15 not) is still "no compliant pack exists," not a satisfied gate.
> - **Sequencing discipline once step 1 of that plan is approved:** no unrelated feature work — and specifically no 6th SE-pack agent or new Capability Pack — is approved between the SDK-build steps and the agent-migration steps that must fast-follow them. Recorded 2026-07-28 specifically to prevent the gate from being technically-open-but-practically-satisfied for an extended window (SDK built, pack not migrated) — a worse, more confusing state than today's honestly-documented exception.

---

## 🔒 Rule 1 — What a development step may read (Phase R2, 2026-07-31)

**A normal development step reads ONLY its own Task ticket and its direct
dependencies' tickets. It does not read the dashboard, and it does not
read history.**

- **Read:** `docs/19_roadmap/tickets/P{nn}/<your-ticket>.md`, plus one file
  per id in that ticket's `depends_on`. Then the specific source files the
  ticket's Input/Output name. That is the whole reading list.
- **Do not read:** `docs/19_roadmap/STATUS.md` or `MODULE_BOARD.md` (both
  generated rollups, for the product owner's navigation — not step input),
  `docs/19_roadmap/history/**`, or any other module's tickets.
- **Exceptions** (only these): a step whose *approved scope is itself* a
  roadmap/planning/audit step; and a genuine cross-cutting conflict that
  the ticket cannot resolve — in which case **stop and report**, per Scope
  discipline below, rather than reading around it.

**Why, with real numbers.** Phase R1 measured the cost of the old rule
("read `implementation_status.md` first, every session"): that file is
151,729 bytes / ~37,900 tokens, of which a **single hand-typed paragraph
is 67,634 characters — 44% of the file**, and it grew by one append every
step. With `feature_inventory.md` (~25,300 tokens) the mandatory floor was
**~64,600 tokens before any work began**, nearly all of it irrelevant to
the step at hand. A Task ticket is capped at 24 lines.

**This rule replaces** the previous "Read `implementation_status.md` first,
every session, before anything else" rule in `CLAUDE.md` and the
`feature_inventory.md` update obligations under
Documentation discipline below — those two files are now **generated
output** (`python -m scripts.roadmap.generate`) and must never be
hand-edited. You update a **ticket's `status:` field**, not a tracker.

---

## Scope discipline

- Work proceeds in **small, individually-scoped steps**. Each step has an explicit scope fence from the product owner, usually with explicit "do NOT build X/Y/Z yet" exclusions.
- **Never expand scope beyond what was approved**, even when a natural next step seems obvious mid-work. Finish the approved step, report, recommend the next one, and wait.
- **Wait for explicit approval before starting the next step.** Do not chain steps together unprompted, even across a single long session.
- When an approved step's own framing offers a choice ("your call," "free hand," "decide and record which"), make the decision, record the reasoning in the code/docs, and report the decision — don't ask the product owner to make implementation-detail decisions that were explicitly delegated.
- When something the approved step needs turns out to be missing, inconsistent, or contradicted by another document, **stop and report it** rather than silently inventing architecture to fill the gap or silently working around it.

## Documentation discipline

- **Documentation is the source of truth.** On a conflict between code and docs, the docs govern unless the current step is explicitly the one correcting the doc.
- **Update your Task ticket's `status:` field in the same step as the code change it describes** (Phase R2, 2026-07-31). This is not a follow-up task. Set `done` only when every Definition-of-Done item in `docs/process/ticket_templates.md` holds; prefer an honest `partial` over a false `done`.
- **Never hand-edit a generated file.** `docs/19_roadmap/STATUS.md` and `MODULE_BOARD.md` are produced by `python -m scripts.roadmap.generate` from the tickets; `docs/07_api/openapi.json` by `python -m scripts.export_openapi`. Each carries a DO-NOT-EDIT banner, and a real test fails the build if one is stale or edited. **Superseded (2026-07-31):** the previous obligations to hand-update `implementation_status.md` every step and `feature_inventory.md`'s completion table and weighted percentage every step. Those two files are retired as trackers — see Rule 1 above for why (a 67,634-character hand-typed paragraph, read every session).
- **Big-file convention, with a concrete threshold (revised 2026-07-30):** any Markdown document exceeding **~500 lines** must be split rather than left to grow further. Two shapes, depending on the document's own nature:
  - **Actively growing** (a running history, a running log): split into a numbered folder alongside the original — `NNN_<topic>.md` files grouped by logical milestone/subsystem (not by date) plus an `INDEX.md`. `docs/19_roadmap/history/` (created 2026-07-28) is the reference implementation.
  - **A closed/completed document** (a finished plan, a finished audit) that merely grew too large while it was active: archive its full content as a new, verbatim numbered entry in the *existing* `docs/19_roadmap/history/` folder (added to `INDEX.md`), and shrink the original file, at its original path, to a short, permanent summary that links to the archived entry for full detail. Do not invent a second, parallel history folder for one document. `docs/03_architecture/platform/platform_sdk_v1_scope.md` (719 → 71 lines, full record archived as `history/027_platform_sdk_v1_scope_plan.md`, 2026-07-30) is the reference implementation of this shape.
  - Either way: **nothing gets deleted or shortened by dropping information** — only relocated, with a real, working link back to the full detail. Check the line count of any document a step edits; if it crosses the threshold as a result of that step's own edit, split it in the same step, don't defer it.
- **Nothing gets deleted when reorganizing documentation** — split, move, and re-link, but preserve full history.
- Record real, load-bearing decisions where a *fresh session* could find them — not only in a conversation. If it's not written down in a file, it doesn't count as decided.
- **Numeric claims in status documents (test counts, mypy/ruff results, coverage percentages, file counts) must be re-verified by actually running the command, every time a file containing them is touched for any reason — never carried forward, copied, or assumed still true.** Recorded 2026-07-28 after a hard-evidence audit found `implementation_status.md` §2 stating "849 tests passed" and "mypy --strict clean" when the real, fresh numbers were 803 passing and 15 mypy errors — stale since an earlier step, undetected because later steps edited nearby text without re-running the commands the numbers depended on. **How to apply:** before writing or leaving in place any sentence with a specific count in a status doc, run the command that produces it in the same step, and paste/derive the number from that real output — not from memory of a prior run, not from a neighboring paragraph, not from what "should still be true" because nothing relevant seemed to change.
- **The standard heading for a document's build-reality section is `## Implementation Status (YYYY-MM-DD)`.** Recorded 2026-07-28 (this convention existed in ~100 documents by repeated practice before it was ever written down anywhere, which is exactly how two undocumented exceptions crept in unnoticed until a hard-evidence audit caught them). One **permitted, intentional variant** exists: `docs/06_capability_packs/software_engineering/agents.md` and `workflows.md` use `## Currently Implemented Subset (YYYY-MM-DD)` instead — kept as-is rather than renamed, because the exact quoted phrase `"Currently Implemented Subset"` is a cross-reference target from at least six other live documents (`agent_catalog.md`, `agent_specifications.md`, `project_intelligence/agents_workflows.md`, `overview.md`, `files_to_read_first.md`, `implementation_roadmap.md`) plus several append-only `history/` files; renaming the heading without updating every quoted reference would trade one inconsistency for a wider one, and editing `history/` files to match is prohibited by this document's own "nothing gets deleted... preserve full history" rule. **How to apply:** use `## Implementation Status` for any new document. Do not invent further variants — if a genuinely good reason exists for a different heading, document it here, in this same list, the way this exception was.

## Engineering discipline

- No new features, subsystems, or architecture beyond the current step's own approved scope — including during "cleanup," "audit," or "infrastructure" steps, which are explicitly non-feature steps unless stated otherwise.
- `mypy --strict` and `ruff check`/`ruff format --check` clean before any step is reported done.
- Zero regressions — run the full relevant test suite (not just new tests) before reporting a step complete.
- Prefer a real fake or a real execution path over a mock; see `docs/process/coding_standards.md` for the one recorded exception and why.
- No hardcoded secrets, ever.
- **Every step's own coding-standards compliance is confirmed explicitly in that step's report, not just inferred from a clean `mypy`/`ruff` run** — and any deviation from `docs/process/coding_standards.md` found anywhere touched or read this step (including pre-existing code the step didn't write) is flagged, not silently passed over. Recorded 2026-07-30; full shape in `docs/process/reporting_format.md` item 5.

## Reporting discipline (added 2026-07-30)

Four permanent additions to every step's report, in full in `docs/process/reporting_format.md` (items 5–8) — summarized here so this document's own "what's binding" list stays complete:

1. **Coding standards confirmation** — see the Engineering discipline bullet above.
2. **Evidence-based claims, codified as a permanent rule.** This project already required real, re-run command output behind every numeric claim in a *status document* (the audit-born rule two bullets below). This extends the identical discipline to every claim in every *step report* — test results, "the pipeline ran end to end," anything else — as a standing rule, not something only status docs enforce.
3. **The status block** — phase (per `feature_inventory.md` §4), phase % complete, overall weighted % complete, one line naming what major feature areas remain. Ends every report, replacing the need to ask for this breakdown separately.
4. **The efficiency note** — optional, real findings only, never manufactured.

## Efficiency discipline (added 2026-07-30)

Process and hygiene rules aimed at reducing per-step time/cost **without reducing safety or evidence quality** — none of these relax the "real evidence, zero regression, docs are truth" rules above; they scope *where* that evidence is gathered each step.

1. **Test/lint runs are scoped by default.** A normal step runs tests only for the files/modules it touched plus their direct dependents (importers/callers) — not the entire suite, and not the full `mypy`/`ruff` sweep. A **full-suite + full `mypy --strict`/`ruff` sweep** still runs in exactly three cases, and is not optional in any of them:
   - **(a) Every 5 steps, as a checkpoint** — counted against the same "Nth normal feature/implementation step" counter `implementation_status.md` (**superseded**)'s own header already narrates (docs-only hygiene steps like this one don't advance that counter; feature and infrastructure steps do).
   - **(b) Before any commit that changes shared/core infrastructure** — `bootstrap.py`, anything under `persistence/`, `configuration_manager/`, cross-cutting Protocols, migrations, or anything else touched by more than one subsystem.
   - **(c) Whenever explicitly requested**, regardless of where the step count sits.
   This rule is easy to accidentally revert to "always full suite" out of caution — it is binding as written, not a suggestion to use judgment about; if a step's own scope is genuinely ambiguous about whether it's "core infrastructure," treat it as (b) and run the full sweep.
2. **Don't re-verify unchanged subsystems.** If a step's own diff doesn't touch a subsystem (e.g. the Sandbox, the LLM Gateway) and the change could not plausibly affect it (no shared import, no shared table, no shared config), that subsystem's own prior proof stands — it does not need a fresh test run or a fresh manual check just because the step happened to touch the same repository. Re-verify it only when the change plausibly reaches it, even indirectly.
3. **Report evidence defaults to bullets and short snippets, not full pasted output blocks.** See `docs/process/reporting_format.md`'s own item 6 for the exact shape — full detail (complete command output, long narrative) is preserved only when something surprising, a bug, or a real design decision occurred, matching the existing "judgment calls worth flagging" practice.
4. **`feature_inventory.md` edits stay to a few lines per step** — a status line, a percentage, a one-sentence pointer to where the real detail lives (a commit, a test file, a `history/` entry) — not a paragraph. Full narrative detail belongs in a `docs/19_roadmap/history/` entry (or the relevant architecture doc's own Implementation Status section), never duplicated into the live tracker. This reverses the pattern the last 10 feature-step entries in `implementation_status.md` actually used (each a long, self-contained paragraph) — those existing entries are left as historical record, not rewritten, but every step from 2026-07-30 onward follows this shorter shape.

## Environment quirks worth knowing (see `CLAUDE.md` for the short version)

- `uv sync --frozen --all-packages` removes the manually-`pip install`-ed `uv` binary from the venv (it's not a declared workspace dependency) — reinstall with `pip install uv` after every sync.
- Docker Desktop availability has been **intermittent across sessions** in this development environment — sometimes unavailable for many consecutive sessions, then available mid-session with no warning. Always check with `docker ps` at the start of any step that might need it, and re-check if a Docker-dependent operation behaves unexpectedly mid-step.
- Windows Docker Desktop uses named pipes (`npipe`), not TCP sockets, for the local Docker Engine API connection — this has real, non-obvious behavioral differences from Linux (see the `detach=True` stdin-EOF bug below).
- `tests/integration/_postgres_fixture.py`'s `postgres_container()` is the required pattern for any new Postgres-backed integration test fixture — it turns a missing Docker daemon into a clean `pytest.skip()` instead of a raw `docker.errors.DockerException`. Use it, don't duplicate the raw `PostgresContainer(...)` construction.

## Git and commits

- Once the repository has git history: **commit at the end of every step**, as part of the standard report (see `docs/process/reporting_format.md`).
- Follow the Git Safety Protocol: never force-push, never skip hooks, never destructive operations without being explicitly asked, never commit a file that might contain a secret without checking its contents first.
- Only push to a remote when explicitly asked to.
