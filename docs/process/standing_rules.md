# Standing Rules – AI_OS

**Status:** Active | **Last Updated:** 2026-07-28

The process rules this project has actually operated under, distilled from how every step so far has actually been approved and executed. These are binding unless the product owner explicitly says otherwise for a given step.

---

## Scope discipline

- Work proceeds in **small, individually-scoped steps**. Each step has an explicit scope fence from the product owner, usually with explicit "do NOT build X/Y/Z yet" exclusions.
- **Never expand scope beyond what was approved**, even when a natural next step seems obvious mid-work. Finish the approved step, report, recommend the next one, and wait.
- **Wait for explicit approval before starting the next step.** Do not chain steps together unprompted, even across a single long session.
- When an approved step's own framing offers a choice ("your call," "free hand," "decide and record which"), make the decision, record the reasoning in the code/docs, and report the decision — don't ask the product owner to make implementation-detail decisions that were explicitly delegated.
- When something the approved step needs turns out to be missing, inconsistent, or contradicted by another document, **stop and report it** rather than silently inventing architecture to fill the gap or silently working around it.

## Documentation discipline

- **Documentation is the source of truth.** On a conflict between code and docs, the docs govern unless the current step is explicitly the one correcting the doc.
- **Update `docs/19_roadmap/implementation_status.md` in the same step as the code change it describes.** This is not a follow-up task.
- **Big-file convention**: any document expected to grow indefinitely (a running history, a running log) gets split into a numbered folder once it exceeds a reasonable size, rather than growing into one unbounded file. `docs/19_roadmap/history/` (numbered by milestone, indexed by `INDEX.md`) is the reference implementation of this pattern, created 2026-07-28. Apply it again if another document (e.g. a future changelog, a future audit log) starts to grow the same way — split by logical grouping (milestone/subsystem), not by date, and always leave an `INDEX.md`.
- **Nothing gets deleted when reorganizing documentation** — split, move, and re-link, but preserve full history.
- Record real, load-bearing decisions where a *fresh session* could find them — not only in a conversation. If it's not written down in a file, it doesn't count as decided.

## Engineering discipline

- No new features, subsystems, or architecture beyond the current step's own approved scope — including during "cleanup," "audit," or "infrastructure" steps, which are explicitly non-feature steps unless stated otherwise.
- `mypy --strict` and `ruff check`/`ruff format --check` clean before any step is reported done.
- Zero regressions — run the full relevant test suite (not just new tests) before reporting a step complete.
- Prefer a real fake or a real execution path over a mock; see `docs/process/coding_standards.md` for the one recorded exception and why.
- No hardcoded secrets, ever.

## Environment quirks worth knowing (see `CLAUDE.md` for the short version)

- `uv sync --frozen --all-packages` removes the manually-`pip install`-ed `uv` binary from the venv (it's not a declared workspace dependency) — reinstall with `pip install uv` after every sync.
- Docker Desktop availability has been **intermittent across sessions** in this development environment — sometimes unavailable for many consecutive sessions, then available mid-session with no warning. Always check with `docker ps` at the start of any step that might need it, and re-check if a Docker-dependent operation behaves unexpectedly mid-step.
- Windows Docker Desktop uses named pipes (`npipe`), not TCP sockets, for the local Docker Engine API connection — this has real, non-obvious behavioral differences from Linux (see the `detach=True` stdin-EOF bug below).
- `tests/integration/_postgres_fixture.py`'s `postgres_container()` is the required pattern for any new Postgres-backed integration test fixture — it turns a missing Docker daemon into a clean `pytest.skip()` instead of a raw `docker.errors.DockerException`. Use it, don't duplicate the raw `PostgresContainer(...)` construction.

## Git and commits

- Once the repository has git history: **commit at the end of every step**, as part of the standard report (see `docs/process/reporting_format.md`).
- Follow the Git Safety Protocol: never force-push, never skip hooks, never destructive operations without being explicitly asked, never commit a file that might contain a secret without checking its contents first.
- Only push to a remote when explicitly asked to.
