# Software Engineering Capability Pack

Autonomous software engineering capabilities for AI_OS
(`capability_pack_contract.md`'s own "Highest priority" pack).

## Status: four real agents, chained into one real workflow

This pack declares four real agents — **Architecture** (`architecture`,
agent_architecture.md's "Agent Categories (Initial Target)" #2, and
`docs/06_capability_packs/software_engineering/agents.md`'s own
documented `software-engineering/architecture` id), **Build**
(`build` — a new entry added to `agents.md`'s own Agent Catalog this
step, since none of its 15 pre-existing documented agents fit a
generic single-file writer; see `agents.md`'s own "Currently
Implemented Subset" section for the reasoning), **QA/Test**
(`qa-test`, matching `agents.md`'s own documented id), and
**Documentation** (`documentation`, matching `agents.md`'s own
documented id) — and one real, declared workflow, **`se.delivery_pipeline`**
(chains all four; see `workflows.md`'s own "Currently Implemented
Subset" section for why this is a distinct, real, smaller workflow
from any of that document's own 7 documented ones, not a rename of
`se.implement_task`).

Two `SandboxExecutor` backends exist in the Kernel this pack depends
on: `LocalSubprocessSandbox` (every agent's own current default) and
`DockerSandbox` (a real ADR-0016 Tier 1 backend — not yet wired in as
any agent's own default; see `implementation_status.md` for why).

Human-approval gating between steps, an HTTP route to trigger the
pipeline, and 11 of `agents.md`'s own other documented agents remain
out of scope.

## Installation

Part of the AI_OS `uv` workspace — `uv sync` from the repository root
installs it alongside the Kernel.

## Registering and activating

There is no automated pack installer yet (a real, documented gap — see
`ai_os_kernel.capability_manager.pack_contract`'s own docstring): a
pack's `catalog.packs` row is written via
`ai_os_kernel.capability_manager.SqlPackLifecycleRepository`, but the
`catalog.agents`/`catalog.prompts`/`catalog.workflow_definitions` rows
this pack's own agents/prompts/workflow need are not yet derived
automatically from `manifest.yaml`. See
`tests/test_architecture_agent_pack.py`, `test_build_agent_pack.py`,
`test_verification_agent_pack.py`, `test_documentation_agent_pack.py`,
and `test_delivery_pipeline.py` under the Kernel's own
`tests/integration/` tree for exactly how this pack is registered,
activated, and resolved end to end today.

## Configuration

The Architecture/Build/Documentation Agents each need a real
`AIOS_DATABASE_URL` and a real Anthropic API key at
`AIOS_SECRET_LLM_ANTHROPIC_API_KEY` to genuinely complete — see
`agents/architecture.py`'s own docstring for why (it reuses the
Kernel's own real LLM Gateway composition directly, a documented
temporary compromise pending a real Platform SDK). The QA/Test Agent
needs neither — it makes no LLM call at all.

## Running this pack's own tests

```sh
pytest capability_packs/software-engineering/tests
mypy --strict capability_packs/software-engineering/src capability_packs/software-engineering/tests
```

## Known, documented gaps (not silently deferred)

- No automated manifest -> `catalog.agents`/`catalog.prompts`/
  `catalog.workflow_definitions` installer exists yet — this pack's own
  tests seed those rows directly.
- `SoftwareEngineeringPack.activate()` is a real, correct implementation
  of the (reduced) `CapabilityPack` Protocol, but nothing in this
  Kernel calls it yet, and it still only registers the Architecture
  Agent (a pre-existing gap, not touched by the naming reconciliation
  that renamed `architect`/`test` to `architecture`/`qa-test`).
- This pack imports Kernel internals directly (no `ai-os-sdk` exists
  yet) — see `pyproject.toml`'s own dependency comment and
  `capability_pack_contract.md`'s own dated exception note.
- No agent's own default sandbox has been switched to `DockerSandbox`
  yet — blocked on a real, portable interpreter-invocation convention
  (see `implementation_status.md`).
- A real `LICENSE` file and the full SDK pack contract test suite
  (`capability_pack_contract.md`'s own "Testing Requirements") are
  deferred — `metadata.license: UNLICENSED` records the former
  honestly; the contract suite itself does not exist yet anywhere in
  this codebase to run.
