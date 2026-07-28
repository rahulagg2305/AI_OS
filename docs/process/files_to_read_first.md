# Files to Read First – AI_OS

**Status:** Active | **Last Updated:** 2026-07-28

For any new session (human or AI) picking up work on this repository. Read in this order; stop once you have what the current task needs — do not read the whole documentation tree "to be safe."

---

## 1. Always read first, every session

1. `docs/19_roadmap/implementation_status.md` — the living record of what is *actually built*, right now. This is the single most important document in the repository for continuing work correctly. It is short by design (2026-07-28 restructuring) and links to `docs/19_roadmap/history/INDEX.md` for the full, detailed, chronological build history if you need it.
2. `docs/DOCUMENTATION_INDEX.md` — the master index. Use it to find the authoritative document for whatever the current task touches.

That's it for "always." Everything below is "read only if the task needs it."

---

## 2. Read only if you need architectural/design context

- `docs/00_constitution/project_constitution.md` and `ai_governance_framework.md` — governing rules, rarely needed mid-task.
- `docs/18_decision_log/README.md` — the ADR index. Check this before making any decision that smells like an architecture choice (a new dependency, a new pattern, a new interface) — it may already be decided.
- `docs/03_architecture/platform/system_architecture.md`, `platform_sdk.md` — only if the task touches cross-cutting platform structure.
- The specific subsystem doc under `docs/03_architecture/kernel/` for whichever Kernel component the task touches (e.g. `context_manager.md`, `llm_gateway.md`, `workflow_engine.md`).
- `docs/06_capability_packs/software_engineering/agents.md` and `workflows.md` — if the task touches the `software-engineering` pack. **Read their own "Currently Implemented Subset" sections first** — the full documented agent/workflow catalog is much larger than what is actually built.

## 3. Read only if you need process/convention context

- `docs/process/coding_standards.md` — the load-bearing subset of `docs/21_templates/CODING_STANDARDS_AND_BEST_PRACTICES.md`, which remains the full authority.
- `docs/process/standing_rules.md` — approval workflow, scope discipline, commit discipline.
- `docs/process/reporting_format.md` — the report shape expected at the end of an implementation step.
- `docs/process/folder_structure.md` — what actually exists on disk vs. what is only planned.

## 4. Never rely on prior chat history

Every one of the documents above exists specifically so that a session with zero memory of previous conversations can continue correctly. If something in a prior conversation seems to matter but isn't written down anywhere in this tree, that is a gap — flag it and write it down, do not silently carry it forward as unwritten tribal knowledge.
