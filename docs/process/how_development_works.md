# How Development Works Now

**For the product owner.** Plain language, no jargon. Written 2026-07-31
at the end of the R1–R4 restructuring. This is the document to refer
back to.

---

## The short version

Work is broken into small **Tasks**. Each Task is one small file (about
ten lines) that says what it is, what it needs, and what it produces.
When I do a Task, I read **only that file and the files it points to** —
not the whole project history. That is the whole change.

Everything else — progress tables, percentages, what's ready to start —
is **generated automatically** from those Task files. Nobody types a
progress report by hand any more.

## Why we changed

The old way required reading two large tracker documents at the start of
every session. We measured them: **about 64,600 words of reading before
any actual work began**, and 44% of one file was a single paragraph that
grew a little longer every single step. Most of it had nothing to do with
the task at hand.

Now the reading is about a **tenth** of that, and all of it is relevant.

## What a Task looks like

```
id: P02-S03-M07-T04
title: Prompt resolver by role or alias
status: done
depends_on: [P02-S03-M07-T01, P02-S03-M07-T02]
evidence: [kernel/src/ai_os_kernel/prompt_engine/resolver.py]
module_path: kernel/src/ai_os_kernel/prompt_engine

Goal:   Resolve a prompt without a caller hardcoding its id.
Input:  A role or alias.
Output: The resolved prompt.
```

The ID reads left to right as **Phase → Stage → Module → Task**:

- **Phase** — which broad delivery stage (the eight the roadmap already
  had, A–H, plus one for process work).
- **Stage** — a named chunk of work inside that phase.
- **Module** — which part of the system (the 43 we already tracked). These
  numbers never change.
- **Task** — the individual piece of work.

`depends_on` is what must exist first. `evidence` is the real file that
proves it's done. `module_path` is where the code lives.

## What you'll look at

Two files, both generated — never edit them by hand:

- **`docs/19_roadmap/STATUS.md`** — progress by phase and stage, plus a
  **"Ready to start"** list of Tasks whose prerequisites are all met.
- **`docs/19_roadmap/MODULE_BOARD.md`** — progress per module.

Plus two you *do* maintain by hand:

- **`docs/19_roadmap/risk_register.md`** — open risks and permanent rules.
- **`docs/19_roadmap/tickets/`** — the Task files themselves.

## How a normal step now goes

1. You pick a Task from the **Ready to start** list (or ask me to
   recommend one) and approve it.
2. I read that Task's file, the files it depends on, and the code it
   names. Nothing else.
3. I do the work, with real tests that genuinely fail if the change is
   reverted.
4. I change that Task's status to `done`, regenerate the two progress
   files, and commit.
5. I report, recommend the next Task, and **wait for your approval**.

That last point hasn't changed and won't.

## The guardrails that are now automatic

These aren't promises to be careful — they're checks that fail the build:

- **A Task file can't grow into an essay.** Hard caps: 24 lines, 200
  characters per line. This is what stops the old problem coming back.
- **Progress files can't be hand-edited.** They're compared against what
  the generator produces; any hand edit fails.
- **"Done" needs real evidence.** A Task can't be marked done or partial
  without naming a real file.
- **A Task can't be done if what it depends on isn't.**
- **No circular dependencies** — checked every build.
- **Nothing can deploy before human approval exists.** This is your
  standing rule (R-001), and it's now wired in as a real dependency, not
  just written down.

## One thing to know about the numbers

**Percentages are for navigation, not for planning.** A partly-finished
Task counts as half. It tells you roughly where effort has gone; it is not
an estimate to hold anyone to.

The **"Ready to start" count is the number worth trusting** — it means
"these Tasks genuinely have nothing blocking them". It's currently 64.
It dropped from 122 when we recorded the real dependencies, which was the
point.

## If something looks wrong

Tell me. Three times during this restructuring the system caught its own
gaps — a missing file path, a mostly-empty dependency graph, and a Task
marked unfinished that was actually done. It's designed to surface
problems rather than hide them, so a suspicious number probably *is*
worth asking about.
