# Standing Rules – AI_OS

**Status:** Active | **Last Updated:** 2026-07-28 (added the Platform SDK growth gate, a hard product-owner blocker)

The process rules this project has actually operated under, distilled from how every step so far has actually been approved and executed. These are binding unless the product owner explicitly says otherwise for a given step.

---

## 🛑 Capability Pack growth gate (hard blocker, recorded 2026-07-28)

**No new agent may be added to any Capability Pack, and no new Capability Pack may be added, until a real Platform SDK package (`ai-os-sdk`) exists.**

- This is a **product-owner decision**, not an engineering guideline — it does not bend for "just this once," a small agent, or a step that seems otherwise well-scoped.
- **Why:** the Software Engineering pack's direct-Kernel-import compromise (documented as a "dated exception" in `docs/03_architecture/capability_framework/capability_pack_contract.md`) was tolerable as a bounded, one-time exception for the pack that already exists. It stops being bounded the moment a *second* pack or a *sixth* agent repeats it — at that point the "temporary" exception has quietly become the load-bearing pattern, with no SDK ever built to replace it.
- **What is grandfathered, unaffected by this gate:** the five existing Software Engineering pack agents (`requirements-analyst`, `architecture`, `build`, `qa-test`, `documentation`) and the pack itself. Nothing about them needs to change today, and this gate does not require retrofitting them before the SDK exists.
- **What is blocked:** a sixth SE-pack agent; any code for `project_intelligence/`, `voice_jarvis/`, or `benchmarking/` (all currently empty); any other new pack.
- **Before starting any step that would add an agent or a pack**, check `docs/03_architecture/capability_framework/capability_pack_contract.md`'s Platform Interaction Rules and `docs/19_roadmap/feature_inventory.md` module 27 (Platform SDK) first — if module 27 is still not built, that step is out of scope regardless of what else was approved.
- **What lifts this gate:** a real Platform SDK package. Building it is itself a future step requiring its own scope fence (see `implementation_status.md` §6 for what that scoping should decide) — this rule does not authorize starting that build casually either.

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
- **Update `docs/19_roadmap/feature_inventory.md`'s completion table (Section 5) and overall weighted percentage (Section 6) at the end of every step** (recorded 2026-07-28). It is the living, per-module/per-phase tracker with a percentage and status per module; `implementation_status.md` stays short and links to it rather than duplicating it. A module whose real state changed but whose row wasn't updated in the same step is a gap to flag, not defer.
- **Big-file convention**: any document expected to grow indefinitely (a running history, a running log) gets split into a numbered folder once it exceeds a reasonable size, rather than growing into one unbounded file. `docs/19_roadmap/history/` (numbered by milestone, indexed by `INDEX.md`) is the reference implementation of this pattern, created 2026-07-28. Apply it again if another document (e.g. a future changelog, a future audit log) starts to grow the same way — split by logical grouping (milestone/subsystem), not by date, and always leave an `INDEX.md`.
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

## Environment quirks worth knowing (see `CLAUDE.md` for the short version)

- `uv sync --frozen --all-packages` removes the manually-`pip install`-ed `uv` binary from the venv (it's not a declared workspace dependency) — reinstall with `pip install uv` after every sync.
- Docker Desktop availability has been **intermittent across sessions** in this development environment — sometimes unavailable for many consecutive sessions, then available mid-session with no warning. Always check with `docker ps` at the start of any step that might need it, and re-check if a Docker-dependent operation behaves unexpectedly mid-step.
- Windows Docker Desktop uses named pipes (`npipe`), not TCP sockets, for the local Docker Engine API connection — this has real, non-obvious behavioral differences from Linux (see the `detach=True` stdin-EOF bug below).
- `tests/integration/_postgres_fixture.py`'s `postgres_container()` is the required pattern for any new Postgres-backed integration test fixture — it turns a missing Docker daemon into a clean `pytest.skip()` instead of a raw `docker.errors.DockerException`. Use it, don't duplicate the raw `PostgresContainer(...)` construction.

## Git and commits

- Once the repository has git history: **commit at the end of every step**, as part of the standard report (see `docs/process/reporting_format.md`).
- Follow the Git Safety Protocol: never force-push, never skip hooks, never destructive operations without being explicitly asked, never commit a file that might contain a secret without checking its contents first.
- Only push to a remote when explicitly asked to.
