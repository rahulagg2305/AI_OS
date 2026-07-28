# Standard Report Format for an Implementation Step – AI_OS

**Status:** Active | **Last Updated:** 2026-07-28

This is the report shape every approved implementation step in this project's history has ended with. Follow it unless the product owner's own approval message specifies a different format for that step (audits, infrastructure steps, and reconciliation steps have each asked for small variations — follow what was actually asked for that step; this is the default when nothing else is specified).

---

## The standard shape

1. **Files created/modified** — grouped if the step touched more than one category (e.g. "renames" vs. "doc updates" vs. "test-fixture fix").
2. **How to run the tests** — the exact command(s), split into deterministic vs. opt-in-live tiers if both exist. State plainly whether Docker/an external dependency was available this session, and if not, what was done instead to verify (a manual trace, `--collect-only`, direct code-path execution) — never silently claim a test suite "passes" without saying whether it was actually executed.
3. **How to verify manually** — a human-runnable path to confirm the feature works, independent of the automated tests.
4. **Confirmation that `docs/19_roadmap/implementation_status.md` was updated** — this is not optional. If the step is large enough to need its own detailed history entry, it goes in `docs/19_roadmap/history/` (see that folder's own `INDEX.md`), with only a short pointer left in `implementation_status.md` itself.
5. **Progress report** — stages complete/remaining, a completion percentage, and the concrete basis for that number (test counts, subsystem inventory) — not a vibe.
6. **Recommend the next small step only** — one recommendation, with reasoning for why it's next over the alternatives, not a menu. Wait for approval before starting it.
7. **Explicitly wait for approval before any further implementation.** Do not chain into the next step unprompted.

## Commit discipline (added 2026-07-28)

Once the repository has a git history (see `docs/process/standing_rules.md`), **commit at the end of every step**, as part of the report — state the commit hash and a one-line summary of what it captures. Follow the Git Safety Protocol already in force (no destructive operations, no force-push, never commit without being asked to push).

## What "thorough" does and doesn't mean

- Do quantify claims (`616 passed`, `218 passed, 10 skipped, 0 failed`) rather than saying "tests pass."
- Do state plainly when something could *not* be verified this session (a missing daemon, a missing API key) and what was done as the next-best substitute.
- Don't pad the report with narration of the investigation process — report findings and decisions, not the search for them.
- Don't recommend more than one next step. If several are genuinely live candidates, name them as alternatives under the one you're actually recommending, with the reasoning for the ranking.
