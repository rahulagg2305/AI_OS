# Changelog — Software Engineering Capability Pack

All notable changes to this pack are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/). This pack has
not yet cut a version past `0.1.0` — every increment below has landed
under that same, still-evolving pre-release version.

## [0.1.0] - 2026-07-27 (last updated 2026-07-28)

### Added

- **The Requirements Analyst Agent (`requirements-analyst`, added 2026-07-28).** Given a
  raw software requirement or ask, produces a structured, refined requirements analysis —
  no architecture design, no code generation. Matches
  `docs/06_capability_packs/software_engineering/agents.md`'s own documented id, so no
  catalog amendment was needed. Proven independently by
  `tests/test_requirements_analyst.py` and the Kernel-side
  `tests/integration/workflow_engine/test_requirements_analyst_agent_pack.py`; **not yet
  chained into `se.delivery_pipeline`**, following the same "prove alone first, chain
  later" sequencing every other agent here has used. Ships with its own prompt,
  `requirements.analyze@0.1.0` (`prompts/requirements_analysis.md`).
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
  (`workflows/delivery_pipeline.yaml`) chaining Architecture, Build, QA/Test, and
  Documentation — see
  `docs/06_capability_packs/software_engineering/workflows.md`'s own
  "Currently Implemented Subset" section for why this is a distinct,
  real workflow, not a fork of any of that document's own 7 documented
  ones.
- `manifest.yaml`, schema-valid against
  `platform_sdk/schemas/manifest.schema.json`.
- `SoftwareEngineeringPack` (`pack.py`), the manifest's `entryPoint`,
  implementing the (reduced) `CapabilityPack` Protocol.

### Changed

- **`DockerSandbox` is now this pack's real default sandbox (2026-07-28).** The Build,
  QA/Test, and Documentation Agents previously defaulted to `LocalSubprocessSandbox`
  (3 of 5 ADR-0016 guarantees). They now resolve their default through
  `ai_os_kernel.sandbox.default_executor.build_default_sandbox_executor()`, which reads
  `AIOS_SANDBOX_BACKEND` — `"docker"` unless explicitly set to `"local"`. This makes the
  pack ADR-0016 Tier 1 by default: ephemeral container, no network, read-only root,
  non-root user, resource-limited. Verified live against a real Docker daemon
  (`tests/integration/sandbox/test_delivery_pipeline_docker.py`), including proof that
  network isolation and filesystem containment hold for code the pipeline itself
  generated. Two real bugs were found and fixed by that verification: a `python_command`
  mismatch in `pipeline.py`'s own composition, and a hardcoded `sys.executable` in a
  Kernel-side test.
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

- 10 of `agents.md`'s own other documented agents (Technical Planning,
  Frontend Development, Database, API Design, DevOps, Security, Code
  Review, Release, Refactoring, Performance).
- All 7 of `workflows.md`'s own documented workflows
  (`se.product_creation`, `se.implement_task`, `se.feature_addition`,
  `se.bug_fix`, `se.code_review`, `se.refactoring`, `se.release`) —
  `se.delivery_pipeline` is a distinct, smaller, real workflow, not one
  of these under another name.
- `requirements-analyst` as a step of `se.delivery_pipeline` — the agent
  exists and is proven, but the pipeline still starts at `architecture`.
- Human-approval gating between any of this pack's own steps (the Kernel
  has no approval execution path at all — ADR-0007).
- Any Tool, Quality Gate, or Command declaration of this pack's own
  (nothing in the Kernel evaluates a quality gate yet — ADR-0006).
- An automated manifest -> catalog installer (`catalog.agents`/
  `catalog.prompts`/`catalog.workflow_definitions` rows are seeded
  directly by this pack's own tests).
- A dependency on `ai-os-sdk` instead of `ai-os-kernel` — no such
  package exists yet, so the direct Kernel import remains in place
  under a dated, documented exception (ADR-0009).
- A `LICENSE` file, and any run of the ADR-0015 pack contract suite —
  `ai_os_sdk.testing.pack_contract_suite` does not exist anywhere in
  this codebase.
