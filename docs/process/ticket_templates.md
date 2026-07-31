# Task Ticket — Template, Definition of Ready, Definition of Done

**Status:** Active · **Introduced:** Phase R2 (2026-07-31)

A Task ticket is the *only* hand-authored unit of roadmap truth. Every
rollup (`STATUS.md`, `MODULE_BOARD.md`) is generated from tickets by
`python -m scripts.roadmap.generate`.

## Template

```markdown
---
id: P02-S01-M05-T07          # P{nn}-S{nn}-M{nn}-T{nn}, filename must equal id
title: <one line, imperative>
status: todo                  # done | partial | todo | blocked
depends_on: [P02-S01-M05-T06] # other ticket ids, may be empty
evidence: [path/to/real/file] # required once status is done or partial
module_path: kernel/src/ai_os_kernel/workflow_engine
---
**Goal:** <what changes about the system, in one sentence>
**Input:** <the exact thing this Task consumes>
**Output:** <the exact, observable thing this Task produces>
```

**`module_path:`** (added 2026-07-31) is where this Task's code lives.
It comes from the frozen registry in `scripts/roadmap/stages.py`
(`MODULE_PATHS`) and is validated against it — a ticket may not name a
path belonging to a different module. Added because the R3 pilot found
that without it a working session had to derive the location from the
module *number*, which only worked because the mapping happened to be
known. Some registry paths are marked PLANNED and do not exist on disk
yet; the Task that fills one creates it there.

### Hard structural limits (enforced, not advisory)

`scripts/roadmap/model.py` **rejects** any ticket over **24 lines** or
containing a line over **200 characters**, and
`tests/roadmap/test_generated_docs_are_current.py` fails CI if one slips
in. These exist because Phase R1 measured the real failure they prevent:
a single hand-typed 67,634-character paragraph in
`implementation_status.md` (44% of that file), read in full every
session. A ticket is a fixed-size unit of work — **never** append to one;
write the next Task instead.

## Definition of Ready

A Task may be started only when all of these hold:

1. **Frontmatter is complete and valid** — the generator parses it.
2. **Every `depends_on` ticket is `done` or `partial`.** The generated
   "Ready to start" list in `STATUS.md` is computed from exactly this.
3. **Goal / Input / Output are each one concrete sentence.** If the
   Output is not observable, the Task is not ready — split it.
4. **It fits one approved step.** If it needs more than one round of
   product-owner approval, it is a Stage, not a Task.
5. **No unresolved decision is embedded in it.** An open question goes to
   the product owner *before* the Task starts, never mid-step.

## Definition of Done

A Task may be marked `done` only when all of these hold:

1. **The stated Output genuinely exists** and is exercised by real code,
   not a stub or a plan.
2. **A real test proves it** — and the test fails if the change is
   reverted. Docker/DB-gated tests must skip cleanly, never error.
3. **`evidence:` names a real path** that substantiates the claim.
4. **`ruff check`, `ruff format --check`, `mypy --strict` are clean** for
   the touched set.
5. **Zero regression**, demonstrated by the suite, with real counts.
6. **Documentation is updated in the same step** — a doc that now
   contradicts reality is a defect, not follow-up work.
7. **Committed**, with the ticket id in the commit message.

`partial` is legitimate and preferred over a false `done`: use it when
the Output genuinely exists but is narrower than the Goal, and say what
is missing in the next Task.

## Related

- `docs/process/standing_rules.md` — what a step may read (Rule 1)
- `docs/process/acceptance_checkpoints.md` — Stage-level demo gates
- `docs/process/interface_stability.md` — changing a frozen module
