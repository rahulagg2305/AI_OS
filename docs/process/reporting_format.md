# Standard Report Format for an Implementation Step – AI_OS

**Status:** Active | **Last Updated:** 2026-07-30 (added 4 permanent rules: coding-standards confirmation, evidence-based claims, the phase/%/remaining-areas status block, and the optional efficiency note — see each item below and `docs/process/standing_rules.md`'s own pointer entry)

This is the report shape every approved implementation step in this project's history has ended with. Follow it unless the product owner's own approval message specifies a different format for that step (audits, infrastructure steps, and reconciliation steps have each asked for small variations — follow what was actually asked for that step; this is the default when nothing else is specified).

---

## The standard shape

1. **Files created/modified** — grouped if the step touched more than one category (e.g. "renames" vs. "doc updates" vs. "test-fixture fix").
2. **How to run the tests** — the exact command(s), split into deterministic vs. opt-in-live tiers if both exist. State plainly whether Docker/an external dependency was available this session, and if not, what was done instead to verify (a manual trace, `--collect-only`, direct code-path execution) — never silently claim a test suite "passes" without saying whether it was actually executed.
3. **How to verify manually** — a human-runnable path to confirm the feature works, independent of the automated tests.
4. **Confirmation that `docs/19_roadmap/implementation_status.md` was updated** — this is not optional. If the step is large enough to need its own detailed history entry, it goes in `docs/19_roadmap/history/` (see that folder's own `INDEX.md`), with only a short pointer left in `implementation_status.md` itself.
5. **Coding standards confirmation (added 2026-07-30).** Explicitly confirm the step's own changes comply with `docs/process/coding_standards.md` — don't just state that `mypy`/`ruff` are clean (that's a separate, narrower bar). Check the actual conventions that tooling can't: naming, no placeholder/speculative architecture, real fakes over mocks, no hardcoded config, discovered-gaps recorded rather than worked around. **Flag any deviation found — including in code the step didn't write**, if it was touched or read closely enough to notice. A clean "confirmed, no deviations found" is a sufficient one-line statement when true; don't manufacture verbosity when there's nothing to flag.
6. **Every claim backed by real, pasted command output (added 2026-07-30, codifying already-established practice as a permanent rule).** A test count, a mypy/ruff result, a file count, "the pipeline ran end to end" — none of these are asserted from memory, from a prior step's number, or from what "should" be true. Run the command in this step and paste/derive the number from its real output. This was already this project's actual practice (see `docs/process/standing_rules.md`'s own numeric-claims rule, born from a hard-evidence audit that caught stale test counts); this entry makes it a permanent, unconditional reporting rule so it is never dropped for a step that feels "too small" or "too quick" to bother.
7. **Status block (added 2026-07-30) — the report's own last section before the recommendation.** A short block, not prose:
   - **Phase:** the current phase from `feature_inventory.md`'s own Section 4 phase table (e.g. "B.5 — Multi-Agent Delivery Pipeline Proof").
   - **Phase % complete:** the phase's own real completion estimate, grounded in that section's basis, not a new vibe number.
   - **Overall weighted % complete:** `feature_inventory.md` Section 6's own current figure.
   - **Remaining:** one line naming the major feature areas still outstanding (not a full list — a pointer, e.g. "Dashboard/CLI/Voice (Phase F), remaining SE Pack agents/workflows, Quality Gate Engine").
   This replaces asking for this breakdown separately each time — it is now a standard part of every report, not a special request.
8. **Efficiency note (added 2026-07-30) — optional, include only if real.** One or two sentences on anything noticed this step that would make future steps faster or safer: a pattern worth generalizing, a repeated manual check that could be automated, a doc that's becoming unwieldy, a recurring source of friction. If nothing genuine surfaced, omit the section entirely rather than manufacturing a suggestion to fill it.
9. **Recommend the next small step only** — one recommendation, with reasoning for why it's next over the alternatives, not a menu. Wait for approval before starting it.
10. **Explicitly wait for approval before any further implementation.** Do not chain into the next step unprompted.

## Commit discipline (added 2026-07-28)

Once the repository has a git history (see `docs/process/standing_rules.md`), **commit at the end of every step**, as part of the report — state the commit hash and a one-line summary of what it captures. Follow the Git Safety Protocol already in force (no destructive operations, no force-push, never commit without being asked to push).

## What "thorough" does and doesn't mean

- Do quantify claims (`616 passed`, `218 passed, 10 skipped, 0 failed`) rather than saying "tests pass."
- Do state plainly when something could *not* be verified this session (a missing daemon, a missing API key) and what was done as the next-best substitute.
- Don't pad the report with narration of the investigation process — report findings and decisions, not the search for them.
- Don't recommend more than one next step. If several are genuinely live candidates, name them as alternatives under the one you're actually recommending, with the reasoning for the ranking.
- Items 5–8 above are meant to add a handful of lines, not double the report's length — a status block is four short lines, a coding-standards confirmation is one sentence when clean, and an efficiency note is skipped entirely when there's nothing real to say.
