# Folder Structure (Actual, Not Aspirational) – AI_OS

**Status:** Active | **Last Updated:** 2026-07-28 (consolidation audit — verified against `git ls-files`, not just the local filesystem)

`PROJECT_INDEX.md`'s own "Repository Structure" table lists the full, intended repository layout. This document records what actually has real content right now, so a fresh session doesn't waste time exploring an empty directory expecting to find something, or miss real content because a folder's name sounded aspirational.

## The single most important fact about this repository's structure

**Git does not track empty directories.** Every "planned" folder below has **zero tracked files**, which means it **does not exist at all in a fresh clone** — it is not an empty directory a reader will find and wonder about; it is simply absent. The only placeholder directories that survive a clone are `workspace/scratch/` and `workspace/temp/`, which are held open by real `.gitkeep` files.

Verified 2026-07-28 by `git ls-files <dir> | wc -l` for every directory named in `PROJECT_INDEX.md`. The repository has **458 tracked files** in total.

Practical consequence: if you are working in a fresh clone and a document references `platform_services/` or `dashboard/` or `ai_context/`, **do not create it speculatively and do not treat its absence as a mistake.** The directory arrives with the step that puts real content in it.

## What has real, tracked content

| Folder | Real content? | What's actually there |
|---|---|---|
| `docs/` | **Yes** | ~150 files — architecture, 25 ADRs, requirements, the roadmap/history, `process/` (this file's own home) |
| `kernel/` | **Yes** | The real `ai-os-kernel` package: Workflow Engine, LLM Gateway (+2 adapters), Prompt Engine, Context Manager, Capability Manager, Security Manager (minimal slice), Secrets Manager (`env` only), Sandbox (`LocalSubprocessSandbox` + `DockerSandbox`), persistence (all schemas), Observability, Manifest Loader, Configuration Manager, HTTP routes, 29 Alembic migrations |
| `capability_packs/` | **Yes** | `software-engineering/` — the real, reprioritized pack: **5 agents** (`requirements-analyst`, `architecture`, `build`, `qa-test`, `documentation`), 1 workflow (`se.delivery_pipeline`, chaining 4 of them), 4 prompts. Plus `_template/` (a documented scaffold: manifest + README + CHANGELOG, no code). |
| `tests/` | **Yes** | `unit/` and `integration/` — real Postgres/Docker-backed tests (see `coding_standards.md` on the one recorded mock exception). 849 passing, 11 skipped. |
| `config/` | Minimal | `llm.yaml`, `platform.yaml` — real, small, checked-in configuration |
| `infra/` | Minimal | `docker-compose.yml` + `environments/{local,dev,staging,production}.yaml`. **`infra/kubernetes/`, `infra/terraform/`, `infra/docker/` have no tracked content, and there is no Dockerfile anywhere in the repository.** |
| `platform_sdk/` | **Stub-level** | Exactly one real file: `schemas/manifest.schema.json`. No `ai-os-sdk` Python package exists — this is why Capability Packs still import Kernel internals directly (a documented, dated exception; see `../03_architecture/capability_framework/capability_pack_contract.md`). `contracts/`, `models/`, `sdk/`, `utilities/`, `prompts/` have no tracked content. |
| `workspace/` | Placeholder | `scratch/`/`temp/` with `.gitkeep` only — prototype scratch space, exempt from documentation-first (ADR-0003) |
| `.github/` | **Yes** | `workflows/ci.yml` — real CI (lint/types/unit/integration run for real; contract/security/image/frontend stages deliberately gated to no-ops pending prerequisites) |

## Planned — no tracked content, absent from a fresh clone

| Folder | Corresponding specification | Why it's empty |
|---|---|---|
| `platform_services/` | `../03_architecture/services/` (7 documents) | Storage, Notification, Caching, Git Integration, Document Processing, Speech Gateway — **all 0% built**. Redis is provisioned in Compose but **no Kernel code uses it**. |
| `dashboard/` | `../13_dashboard/` (3 documents) | No frontend project scaffolded at all |
| `tools/` | `../07_api/cli_design.md` | No `aios` CLI package, no entry-point script declared |
| `ai_context/` | `../ai_context/context_pack_structure.md` | Structure fully specified; zero packs written |
| `knowledge/` | `../knowledge/knowledge_base_structure.md` | Structure fully specified; zero content |
| `traceability/` | `../03_architecture/traceability/traceability_model.md` | No Traceability Engine exists to produce mappings |
| `experiments/` | `../06_capability_packs/benchmarking/overview.md` | No Evaluation Engine and no Benchmarking pack exist to produce artifacts |
| `specs/`, `manifests/`, `governance/`, `projects/`, `scripts/`, `assets/` | `PROJECT_INDEX.md` | Intended artifact areas, not yet started |
| `tests/security/`, `tests/performance/`, `tests/regression/`, `tests/benchmarks/` | `../10_testing/test_strategy.md` | Named in the test strategy and referenced by CI's gated stages; no tests written. **There is no `tests/contract/` directory at all.** |
| `capability_packs/{benchmarking,project_intelligence,voice_jarvis}/` | `../06_capability_packs/` | Three planned packs, all 0% built |
| `docs/01_product_definition/`, `docs/04_design/`, `docs/15_benchmarking/`, `docs/17_governance/`, `docs/03_architecture/diagrams/`, `docs/03_architecture/integrations/` | — | Numbered doc slots reserved by the original documentation plan that were never filled. Their content lives elsewhere: product definition in `PROJECT_INDEX.md`/`README.md`, benchmarking in `../06_capability_packs/benchmarking/overview.md`, governance in `../00_constitution/ai_governance_framework.md` and `../03_architecture/governance/`. **Do not create documents in these slots without a reason** — prefer the existing homes. |

## What this means practically

- If a task references "the Dashboard" or "the Voice/Jarvis pack" or "Project Intelligence" or "the CLI" — check this document first. None of them have any real code.
- `platform_sdk/` being nearly empty is a recurring, load-bearing fact: every Capability Pack module docstring saying "no `ai-os-sdk` exists yet, this is a documented temporary compromise" refers to exactly this.
- **One directory was removed during the 2026-07-28 consolidation audit**: `capability_packs/software_engineering/` (underscore) — a dead, never-tracked duplicate of the real hyphenated `capability_packs/software-engineering/`, referenced by nothing. This follows the `capability_packs/analytics/` precedent (investigated, confirmed dead, removed, recorded). See `../19_roadmap/history/025_documentation_consolidation_audit.md`.
- This table goes stale as real work lands. Update it in the same step that puts real content into a Planned row — alongside `PROJECT_INDEX.md`'s Status column and `../19_roadmap/feature_inventory.md`.

## Related Documents

- `PROJECT_INDEX.md` (repository root) — the intended full layout, with a Status column mirroring this document
- `../19_roadmap/feature_inventory.md` — per-module completion tracker; the authority on "how done is X"
- `../19_roadmap/implementation_status.md` — short current-state summary, read first every session
- `files_to_read_first.md` — what to read, and when, for a given task
- `standing_rules.md` — the documentation discipline that keeps this file accurate
