# Changelog — Software Engineering Capability Pack

All notable changes to this pack are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/). This pack has
not yet cut a version past `0.1.0` — every increment below has landed
under that same, still-evolving pre-release version.

## [0.1.0] - 2026-07-27 (last updated 2026-07-28)

### Added

- The Architecture Agent (`architecture` — renamed from `architect`
  during a later documentation-reconciliation step, see below). Given a
  software requirement, proposes a concrete technical design — no code
  generation.
- The Build Agent (`build` — a new entry added to
  `docs/06_capability_packs/software_engineering/agents.md`'s own
  Agent Catalog during the same reconciliation step, since none of its
  15 pre-existing documented agents fit this agent's real, generic
  single-file-writer scope). Given a design or instruction, produces
  one concrete file and genuinely writes it through the sandbox.
- The QA/Test Agent (`qa-test` — renamed from `test`). Genuinely runs a
  command inside the sandbox and reports a real pass/fail — no LLM call
  at all.
- The Documentation Agent (`documentation` — already matched
  `agents.md`'s own documented id, no rename needed). Calls an LLM to
  record what was built and how it was verified, writing a real
  Markdown file through the sandbox.
- `se.delivery_pipeline`, a real, declared `WorkflowDefinition`
  (`workflows/delivery_pipeline.yaml`) chaining all four agents — see
  `docs/06_capability_packs/software_engineering/workflows.md`'s own
  "Currently Implemented Subset" section for why this is a distinct,
  real workflow, not a fork of any of that document's own 7 documented
  ones.
- `manifest.yaml`, schema-valid against
  `platform_sdk/schemas/manifest.schema.json`.
- `SoftwareEngineeringPack` (`pack.py`), the manifest's `entryPoint`,
  implementing the (reduced) `CapabilityPack` Protocol.

### Changed

- **Documentation reconciliation (2026-07-28):** agent ids `architect`
  and `test` were renamed to `architecture` and `qa-test` to match
  `agents.md`'s own Approved, authoritative Agent Catalog; `build` was
  kept and formally added to that catalog as a new entry instead
  (agents.md's own documented ids had no genuine fit for it); the
  workflow was kept as `se.delivery_pipeline` and documented as its own
  entry in `workflows.md` rather than force-renamed to
  `se.implement_task` (a different, incompatible, already-documented
  sub-workflow shape). Zero behaviour change — proven by this pack's
  own existing tests passing unmodified in substance (only id literals
  changed).

### Not included in this release

- 11 of `agents.md`'s own other documented agents (Requirements
  Analyst, Technical Planning, Frontend Development, Database, API
  Design, DevOps, Security, Code Review, Release, Refactoring,
  Performance).
- 6 of `workflows.md`'s own other documented workflows
  (`se.product_creation`, `se.implement_task`, `se.feature_addition`,
  `se.bug_fix`, `se.code_review`, `se.refactoring`, `se.release`).
- Human-approval gating between any of this pack's own steps.
- Any Tool, Quality Gate, or Command declaration of this pack's own.
- An automated manifest -> catalog installer (`catalog.agents`/
  `catalog.prompts`/`catalog.workflow_definitions` rows are seeded
  directly by this pack's own tests).
- A `DockerSandbox`-backed default for any agent (the Kernel now has a
  real ADR-0016 Tier 1 backend; no agent in this pack uses it yet).
