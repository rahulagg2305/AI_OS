# AI_OS — Instructions for Claude

Auto-read every session. Keep this short — detail lives in the linked files, not here.

## Core process rule

**Read `docs/19_roadmap/implementation_status.md` first, every session, before anything else.** It is short by design and links to `docs/19_roadmap/history/INDEX.md` for full chronological detail. Read any other document only when the current task specifically needs it — see `docs/process/files_to_read_first.md` for what to reach for and when. Do not rely on prior chat history; if something matters, it must be written down somewhere in this tree.

**Update `docs/19_roadmap/feature_inventory.md`'s completion table and overall percentage at the end of every step**, alongside `implementation_status.md` — it is the living, granular tracker for every feature/module/phase (44 modules as of 2026-07-28); `implementation_status.md` stays short and links to it.

## Approval workflow

Work proceeds in small, explicitly-scoped steps, each approved by the product owner before it starts. Finish exactly the approved scope, report using the shape in `docs/process/reporting_format.md`, recommend the next step (one recommendation, not a menu), and **wait for explicit approval before starting it** — never chain into unapproved work. Full rules: `docs/process/standing_rules.md`.

## Known environment quirks

- `uv sync --frozen --all-packages` removes the manually-installed `uv` binary from the venv — reinstall with `pip install uv` afterward.
- **Docker Desktop availability is intermittent across sessions** in this environment — sometimes unavailable for many consecutive sessions, then available mid-session without warning. Check with `docker ps` before relying on it.
- Windows Docker uses named pipes (`npipe`), not TCP — this caused a real bug (`detach=True` silently prevented stdin EOF from ever reaching a container, hanging until timeout; fixed with `detach=False` in `ai_os_kernel.sandbox.docker_executor`). Windows-specific Docker behavior is not always the same as Linux; verify, don't assume.
- Any new Postgres-backed integration test must use `tests/integration/_postgres_fixture.py`'s `postgres_container()` — it turns a missing Docker daemon into a clean `pytest.skip()` instead of a raw exception. Don't construct `PostgresContainer(...)` directly.

## Big-file convention

Any file expected to grow indefinitely (a running history, a running log) gets split into a numbered folder once it's grown too large for one file to serve its purpose, grouped by logical milestone/subsystem (not by date), with an `INDEX.md`. `docs/19_roadmap/history/` is the reference example — apply the same pattern again if another document starts growing the same way.

## Process docs (read as needed, not all at once)

- `docs/process/files_to_read_first.md` — what to read, and when, for a given task
- `docs/process/standing_rules.md` — full approval/scope/documentation/git discipline
- `docs/process/reporting_format.md` — the exact report shape expected at the end of a step
- `docs/process/coding_standards.md` — the load-bearing subset of `docs/21_templates/CODING_STANDARDS_AND_BEST_PRACTICES.md` (that document remains the full authority)
- `docs/process/folder_structure.md` — what actually has real content on disk vs. what's still an empty placeholder

## Orientation

`docs/DOCUMENTATION_INDEX.md` is the master index for everything else. `PROJECT_INDEX.md` and `README.md` are the human-facing project overview.
