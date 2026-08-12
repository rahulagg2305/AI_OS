# Software Engineering Capability Pack

Autonomous software engineering capabilities for AI_OS
(`capability_pack_contract.md`'s own "Highest priority" pack).

## Status: five real agents, all five chained into one real workflow

**Last updated: 2026-07-30** (`requirements-analyst` wired into `se.delivery_pipeline` as its own first step — see the table below). Prior: 2026-07-29, pipeline composition relocated out of this pack's own source tree into `tests/integration/`, `platform_sdk_v1_scope.md` step 7.

This pack declares **five** real agents:

| Agent id | Module | In the pipeline? | Notes |
|---|---|---|---|
| `requirements-analyst` | [`agents/requirements_analyst.py`](src/ai_os_pack_software_engineering/agents/requirements_analyst.py) | Yes (step 1) | Analyzes/refines a raw requirement into a structured analysis. Matches `agents.md`'s documented id. Added 2026-07-28; wired into the pipeline 2026-07-30. |
| `architecture` | [`agents/architecture.py`](src/ai_os_pack_software_engineering/agents/architecture.py) | Yes (step 2) | Design proposal only, no code. Matches `agents.md`'s documented id. Now designs against `requirements-analyst`'s own real output, not the raw requirement directly. |
| `build` | [`agents/build.py`](src/ai_os_pack_software_engineering/agents/build.py) | Yes (step 3) | Writes exactly one file through the sandbox. A *new* entry added to `agents.md`'s Agent Catalog, since none of its 15 pre-existing documented agents fit a generic single-file writer. |
| `qa-test` | [`agents/verification.py`](src/ai_os_pack_software_engineering/agents/verification.py) | Yes (step 4) | Runs the file through the sandbox; pass/fail from the real exit code. **Makes no LLM call at all.** |
| `documentation` | [`agents/documentation.py`](src/ai_os_pack_software_engineering/agents/documentation.py) | Yes (step 5) | Records the Build+Test result as a Markdown file through the sandbox. |

And one real, declared workflow: **`se.delivery_pipeline`** ([`workflows/delivery_pipeline.yaml`](workflows/delivery_pipeline.yaml)), now chaining all five agents above. See `agents.md`'s "Currently Implemented Subset" section, and `workflows.md`'s, for why this is a distinct real workflow rather than a rename of `se.implement_task`.

**Sandbox:** two `SandboxExecutor` backends exist in the Kernel this pack depends on — `LocalSubprocessSandbox` (3 of 5 guarantees; no network or filesystem containment) and `DockerSandbox` (a real ADR-0016 Tier 1 backend: ephemeral container, no network, read-only root, non-root, resource-limited). **`DockerSandbox` is now this pack's real default**, selected via the `AIOS_SANDBOX_BACKEND` environment variable (`"docker"` unless set to `"local"`), and has been verified live against a real daemon. Set `AIOS_SANDBOX_BACKEND=local` for environments without Docker or for fast tests.

**Out of scope so far:** human-approval gating between steps, an HTTP route to trigger the pipeline, any manifest-declared Tool or Quality Gate, and 11 of `agents.md`'s other documented agents.

## Where things are

| What | Where |
|---|---|
| Manifest (agents, prompts, workflow, permissions) | [`manifest.yaml`](manifest.yaml) |
| Pack entry point (`CapabilityPack`) | [`src/ai_os_pack_software_engineering/pack.py`](src/ai_os_pack_software_engineering/pack.py) |
| Pipeline composition (real Kernel code — relocated out of this pack's shipped wheel in `platform_sdk_v1_scope.md` step 7, then promoted from test-harness code into `ai_os_kernel` itself 2026-07-30 once a real HTTP route needed the same composition) | [`../../kernel/src/ai_os_kernel/workflow_engine/delivery_pipeline.py`](../../kernel/src/ai_os_kernel/workflow_engine/delivery_pipeline.py) |
| HTTP trigger route (`POST /api/v1/workflows/se.delivery_pipeline`, added 2026-07-30) | [`../../kernel/src/ai_os_kernel/routes/delivery_pipeline.py`](../../kernel/src/ai_os_kernel/routes/delivery_pipeline.py) |
| Prompts | [`prompts/`](prompts/) — one per LLM-backed agent |
| Pack-local tests | [`tests/`](tests/) — deterministic, no database, no live LLM call |
| Kernel-side integration tests | `../../tests/integration/workflow_engine/` and `../../tests/integration/sandbox/` |

## Governing documents

- [`capability_pack_contract.md`](../../docs/03_architecture/capability_framework/capability_pack_contract.md) — the contract this pack implements, **including the dated exception permitting this pack's direct Kernel imports** (no `ai-os-sdk` package exists yet)
- [`manifest_schema.md`](../../docs/03_architecture/capability_framework/manifest_schema.md) + the machine-readable [`manifest.schema.json`](../../platform_sdk/schemas/manifest.schema.json) — what `manifest.yaml` is validated against
- [`agents.md`](../../docs/06_capability_packs/software_engineering/agents.md) — the pack's full intended 16-agent catalog and its "Currently Implemented Subset" section
- [`workflows.md`](../../docs/06_capability_packs/software_engineering/workflows.md) — the pack's intended workflows
- [`tools_quality_gates.md`](../../docs/06_capability_packs/software_engineering/tools_quality_gates.md) — intended tools/gates (this pack declares none yet)
- [`ADR-0016`](../../docs/18_decision_log/adr/ADR-0016-tool-execution-sandboxing.md) — the sandboxing decision every agent here depends on
- [`feature_inventory.md`](../../docs/19_roadmap/feature_inventory.md) — live build status

## Installation

Part of the AI_OS `uv` workspace — `uv sync` from the repository root
installs it alongside the Kernel.

## Registering and activating

There is no automated pack installer yet (a real, documented gap — see
`ai_os_kernel.capability_manager.pack_contract`'s own docstring): a pack's `catalog.packs`
row is written via `ai_os_kernel.capability_manager.SqlPackLifecycleRepository`, but the
`catalog.agents`/`catalog.prompts`/`catalog.workflow_definitions` rows this pack's agents,
prompts, and workflow need are not yet derived automatically from `manifest.yaml`.

The Kernel-side integration tests are the executable specification for how this pack is
registered, activated, and resolved end to end today — read them rather than inferring a
procedure:

| Test | Proves |
|---|---|
| [`test_requirements_analyst_agent_pack.py`](../../tests/integration/workflow_engine/test_requirements_analyst_agent_pack.py) | `requirements-analyst` resolves and runs standalone |
| [`test_architecture_agent_pack.py`](../../tests/integration/workflow_engine/test_architecture_agent_pack.py) | `architecture` resolves and runs |
| [`test_build_agent_pack.py`](../../tests/integration/workflow_engine/test_build_agent_pack.py) | `build` writes a real file through the sandbox |
| [`test_verification_agent_pack.py`](../../tests/integration/workflow_engine/test_verification_agent_pack.py) | `qa-test` runs a real command and reports a real exit code |
| [`test_documentation_agent_pack.py`](../../tests/integration/workflow_engine/test_documentation_agent_pack.py) | `documentation` writes a real Markdown record |
| [`test_delivery_pipeline.py`](../../tests/integration/workflow_engine/test_delivery_pipeline.py) | all five chained steps hand off through real workflow state |
| [`test_delivery_pipeline_docker.py`](../../tests/integration/sandbox/test_delivery_pipeline_docker.py) | the same pipeline against a **live Docker daemon**, with network isolation and filesystem containment proven for code the pipeline itself generated |

## Configuration

The Requirements Analyst, Architecture, Build, and Documentation Agents each need a real
`AIOS_DATABASE_URL` and a real Anthropic API key at `AIOS_SECRET_LLM_ANTHROPIC_API_KEY`
to genuinely complete — see [`agents/architecture.py`](src/ai_os_pack_software_engineering/agents/architecture.py)'s
docstring for why (it reuses the Kernel's real LLM Gateway composition directly, a
documented temporary compromise pending a real Platform SDK). The QA/Test Agent needs
neither — it makes no LLM call at all.

`AIOS_SANDBOX_BACKEND` selects the sandbox backend for the three agents that execute
anything (`docker` by default, `local` to opt out).

## Running this pack's own tests

From the repository root:

```sh
uv run pytest capability_packs/software-engineering/tests
uv run mypy --strict
uv run ruff check capability_packs/software-engineering
```

The pack-local tests are deterministic: no database, no live LLM call, no Docker. The
end-to-end proofs live in the Kernel-side integration tests listed above.

## Known, documented gaps (not silently deferred)

- **`SoftwareEngineeringPack.activate()` is under-wired.** It is a real, correct
  implementation of the (reduced) `CapabilityPack` Protocol, but nothing in the Kernel
  calls it yet, and it registers only the Architecture Agent.
- **This pack imports Kernel internals directly**, because no `ai-os-sdk` exists — see
  [`pyproject.toml`](pyproject.toml)'s dependency comment and
  [`capability_pack_contract.md`](../../docs/03_architecture/capability_framework/capability_pack_contract.md)'s
  dated exception note. This is the pack's single largest deviation from
  [ADR-0009](../../docs/18_decision_log/adr/ADR-0009-packaging-and-dependency-management.md).
- **No declared Tools and no declared Quality Gates.** The manifest declares agents,
  prompts, and one workflow only. [ADR-0006](../../docs/18_decision_log/adr/ADR-0006-quality-gates-are-mandatory.md)
  is not satisfiable by any pack yet — the Kernel's Quality Gate Engine is an empty stub.
- **No human-approval gating between steps.** The Kernel has no approval execution path
  ([ADR-0007](../../docs/18_decision_log/adr/ADR-0007-human-governance-for-critical-decisions.md)).
- **No `LICENSE` file, and no pack contract test suite to run.** `metadata.license:
  UNLICENSED` records the former honestly; the suite
  `capability_pack_contract.md`'s Testing Requirements and
  [ADR-0015](../../docs/18_decision_log/adr/ADR-0015-testing-and-ci.md) both specify
  (`ai_os_sdk.testing.pack_contract_suite`) does not exist anywhere in this codebase.
