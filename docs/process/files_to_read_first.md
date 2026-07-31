# Files to Read First – AI_OS

**Status:** Active | **Last Updated:** 2026-07-31 (Phase R2 — §1 replaced)

For any new session (human or AI) picking up work on this repository. Read in this order; stop once you have what the current task needs — do not read the whole documentation tree "to be safe."

---

## 1. A normal development step: read your ticket, and nothing else

1. **Your own Task ticket** — `docs/19_roadmap/tickets/P{nn}/P{nn}-S{nn}-M{nn}-T{nn}.md` (~10 lines).
2. **One file per id in its `depends_on`.**
3. **The specific source files its Input/Output name.**

**That is the entire reading list.** Do **not** read `docs/19_roadmap/STATUS.md` or `MODULE_BOARD.md` (generated rollups — product-owner navigation, not step input), and do not read `docs/19_roadmap/history/**`.

**Superseded 2026-07-31:** this section previously said to always read `implementation_status.md` first, every session. Phase R1 measured that at ~37,900 tokens — 44% of it a single hand-typed 67,634-character paragraph that grew every step. Both that file and `feature_inventory.md` are retired as trackers, replaced by the generated `STATUS.md`/`MODULE_BOARD.md`. Full rationale: `standing_rules.md` Rule 1.

**Two exceptions only:** a step whose approved scope *is* a roadmap/planning/audit step (read `STATUS.md` freely), or a genuine cross-cutting conflict your ticket cannot resolve — in which case **stop and report**, don't read around it.

---

## 2. Read only if you need architectural/design context

- `docs/00_constitution/project_constitution.md` and `ai_governance_framework.md` — governing rules, rarely needed mid-task.
- `docs/18_decision_log/README.md` — the ADR index. Check this before making any decision that smells like an architecture choice (a new dependency, a new pattern, a new interface) — it may already be decided.
- `docs/03_architecture/platform/system_architecture.md`, `platform_sdk.md` — only if the task touches cross-cutting platform structure.
- The specific subsystem doc under `docs/03_architecture/kernel/` for whichever Kernel component the task touches (e.g. `context_manager.md`, `llm_gateway.md`, `workflow_engine.md`).
- `docs/06_capability_packs/software_engineering/agents.md` and `workflows.md` — if the task touches the `software-engineering` pack. **Read their own "Currently Implemented Subset" sections first** — the full documented agent/workflow catalog is much larger than what is actually built.

## 3. Read only if you need process/convention context

- `docs/process/coding_standards.md` — the load-bearing subset of `docs/21_templates/CODING_STANDARDS_AND_BEST_PRACTICES.md`, which remains the full authority.
- `docs/process/standing_rules.md` — **Rule 1 (what a step may read)**, approval workflow, scope discipline, commit discipline.
- `docs/process/ticket_templates.md` — the Task ticket template, Definition of Ready, Definition of Done.
- `docs/process/reporting_format.md` — the report shape expected at the end of an implementation step.
- `docs/process/folder_structure.md` — what actually exists on disk vs. what is only planned.
- `docs/process/interface_stability.md` — before changing anything another module or pack depends on.
- `docs/process/api_contract_boundary.md` — if the task touches the HTTP surface, or is a Dashboard/CLI task.
- `docs/process/acceptance_checkpoints.md` — what Stage-level "done" must demonstrate.
- `docs/19_roadmap/risk_register.md` — open risks, including the **hard deploy/approval rule (R-001)**.

## 4. Never rely on prior chat history

Every one of the documents above exists specifically so that a session with zero memory of previous conversations can continue correctly. If something in a prior conversation seems to matter but isn't written down anywhere in this tree, that is a gap — flag it and write it down, do not silently carry it forward as unwritten tribal knowledge.
