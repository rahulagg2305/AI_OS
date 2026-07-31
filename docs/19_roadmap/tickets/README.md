# Task Tickets

**The only hand-authored source of roadmap truth.** Everything in
`../STATUS.md` and `../MODULE_BOARD.md` is generated from these files.

## Layout

```
tickets/P{nn}/P{nn}-S{nn}-M{nn}-T{nn}.md
```

- **P** — Phase, `P01`–`P08` ≡ roadmap Stages **A–H**. Frozen.
- **S** — Stage, a named work-slice inside a Phase. See
  `scripts/roadmap/stages.py`.
- **M** — Module, `M01`–`M44`, the numbers `feature_inventory.md` §5 has
  always used. Frozen. **M35 is permanently retired** (Analytics Pack,
  removed 2026-07-28) and is never reused.
- **T** — Task, sequential within a (Phase, Stage, Module).

Uniqueness is on the full four-tuple, so `S01` under `P02` is a different
Stage from `S01` under `P03`, and the same Module may legitimately carry
Tasks in several Phases (M36 has Tasks in both `P02` and `P06`).

## If you are doing a development step

Read **only** your own ticket and the tickets named in its `depends_on`.
Do not read `STATUS.md`, `MODULE_BOARD.md`, or `history/`. That is
`CLAUDE.md`'s Core process rule and `docs/process/standing_rules.md`
Rule 1.

## Commands

```bash
python -m scripts.roadmap.generate           # rewrite the rollups
python -m scripts.roadmap.generate --check   # verify (CI does this)
pytest tests/roadmap -q                      # enforce every invariant
```

## Rules

- A ticket is **capped at 24 lines and 200 chars per line**, enforced by
  the parser and by CI. Never append to a ticket — write the next Task.
- `done` or `partial` **requires** a real `evidence:` path.
- A `done` ticket may not depend on a not-done ticket.
- See `docs/process/ticket_templates.md` for the template, Definition of
  Ready, and Definition of Done.
