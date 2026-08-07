# AI_OS — Instructions for Claude

Auto-read every session. Keep this short — detail lives in the linked files, not here.

## Core process rule (replaced 2026-07-31, Phase R2)

**Read ONLY your own Task ticket and its direct dependencies' tickets. Nothing else.**

- Your ticket: `docs/19_roadmap/tickets/P{nn}/P{nn}-S{nn}-M{nn}-T{nn}.md` (~10 lines, capped at 24).
- Then one file per id in its `depends_on`. Then the source files its Input/Output actually name. **That is the whole reading list.**
- **Do not read** `docs/19_roadmap/STATUS.md` or `MODULE_BOARD.md` (generated rollups — product-owner navigation, not step input), `docs/19_roadmap/history/**`, or other modules' tickets.
- **Exceptions, only these two:** a step whose approved scope *is* a roadmap/planning/audit step; or a genuine cross-cutting conflict the ticket cannot resolve — then **stop and report**, don't read around it.

**Why:** the old rule ("read `implementation_status.md` first, every session") cost ~64,600 tokens before any work began, 44% of it one hand-typed 67,634-character paragraph that grew every step. Full measurements: `docs/process/standing_rules.md` Rule 1.

**Update your ticket's `status:` field in the same step as the code change.** Never hand-edit a generated file — `STATUS.md`/`MODULE_BOARD.md` come from `python -m scripts.roadmap.generate`, `docs/07_api/openapi.json` from `python -m scripts.export_openapi`. A real test fails the build if one is stale or edited.

Do not rely on prior chat history; if something matters, it must be written down in this tree.

## Approval workflow

Work proceeds in small, explicitly-scoped steps, each approved by the product owner before it starts. Finish exactly the approved scope, report using the shape in `docs/process/reporting_format.md`, recommend the next step (one recommendation, not a menu), and **wait for explicit approval before starting it** — never chain into unapproved work. Full rules: `docs/process/standing_rules.md`.

**Every report also confirms `coding_standards.md` compliance (flagging any deviation found, even pre-existing), backs every claim with real command output, ends with a status block (phase / phase % / overall weighted % / what major areas remain), and includes an efficiency note when a real one exists.** Full shape: `docs/process/reporting_format.md`.

## Known environment quirks

- `uv sync --frozen --all-packages` removes the manually-installed `uv` binary from the venv — reinstall with `pip install uv` afterward.
- **Docker Desktop availability is intermittent across sessions** in this environment — sometimes unavailable for many consecutive sessions, then available mid-session without warning. Check with `docker ps` before relying on it.
- Windows Docker uses named pipes (`npipe`), not TCP — this caused a real bug (`detach=True` silently prevented stdin EOF from ever reaching a container, hanging until timeout; fixed with `detach=False` in `ai_os_kernel.sandbox.docker_executor`). Windows-specific Docker behavior is not always the same as Linux; verify, don't assume.
- Any new Postgres-backed integration test must use `tests/integration/_postgres_fixture.py`'s `postgres_container()` — it turns a missing Docker daemon into a clean `pytest.skip()` instead of a raw exception. Don't construct `PostgresContainer(...)` directly.

## Big-file convention

Any file expected to grow indefinitely (a running history, a running log) gets split into a numbered folder once it's grown too large for one file to serve its purpose, grouped by logical milestone/subsystem (not by date), with an `INDEX.md`. `docs/19_roadmap/history/` is the reference example — apply the same pattern again if another document starts growing the same way.

## Documentation-vs-reality discipline

This project is documentation-first (ADR-0003), so **most architecture documents were written before their code and many describe subsystems that do not exist yet.** "Approved" means the design is authoritative, not that it is built.

- Every `docs/03_architecture/` subsystem document carries an **Implementation Status** section near the top. Read it before assuming the document describes callable code.
- `docs/19_roadmap/feature_inventory.md` is the authority on how complete any module is. Update it every step (standing rule above).
- **Folders named in the docs frequently do not exist.** Git does not track empty directories, so every "planned" folder (`dashboard/`, `platform_services/`, `ai_context/`, `knowledge/`, `traceability/`, `specs/`, `manifests/`, `tools/`, and others) is absent from a fresh clone. `docs/process/folder_structure.md` is the definitive real-vs-planned list. Do not create a planned folder speculatively; it arrives with the step that fills it.
- The `ai-os-sdk` package (`platform_sdk/src/ai_os_sdk/`) is real as of Platform SDK v1.0.0 (contracts, errors, models, testing, utilities). Direct Kernel-internal imports from existing packs (pre-dating the SDK) are a documented, dated exception, not a pattern to copy in new work.
- **✅ Capability Pack growth gate — LIFTED (product-owner decision, 2026-07-29), now that the Platform SDK exists.** A new agent may be added to a Capability Pack, and a new Capability Pack may be added, subject to every other standing rule (scope discipline, documentation-first, real verification). Full statement, including the original 2026-07-28 gate text preserved for the record: `docs/process/standing_rules.md`.

## Process docs (read as needed, not all at once)

- `docs/process/files_to_read_first.md` — what to read, and when, for a given task
- `docs/process/standing_rules.md` — full approval/scope/documentation/git discipline
- `docs/process/reporting_format.md` — the exact report shape expected at the end of a step
- `docs/process/coding_standards.md` — the load-bearing subset of `docs/21_templates/CODING_STANDARDS_AND_BEST_PRACTICES.md` (that document remains the full authority)
- `docs/process/folder_structure.md` — what actually has real content on disk vs. what's still an empty placeholder

## Orientation

`docs/DOCUMENTATION_INDEX.md` is the master index for everything else. `PROJECT_INDEX.md` and `README.md` are the human-facing project overview.
