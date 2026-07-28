# Folder Structure (Actual, Not Aspirational) – AI_OS

**Status:** Active | **Last Updated:** 2026-07-28

`PROJECT_INDEX.md`'s own "Repository Structure" table lists the full, intended repository layout — several of those folders exist today only as empty placeholders. This document records what actually has real content right now, so a fresh session doesn't waste time exploring an empty directory expecting to find something, or miss real content because a folder's name sounded aspirational.

| Folder | Real content? | What's actually there |
|---|---|---|
| `docs/` | **Yes** | ~108 files — architecture, ADRs, requirements, the roadmap/history, `process/` (this file's own home) |
| `kernel/` | **Yes** | ~300 files — the real `ai-os-kernel` package: Workflow Engine, LLM Gateway, Prompt Engine, Context Manager, Security Manager (minimal slice), Capability Manager, Sandbox (`LocalSubprocessSandbox` + `DockerSandbox`), persistence, alembic migrations |
| `capability_packs/` | **Yes** | ~37 files — `software-engineering/` (the real, reprioritized pack: 4 agents, 1 workflow) and `_template/` (a documented scaffold, not a real pack) |
| `tests/` | **Yes** | ~226 files — `unit/`, `integration/` (real Postgres/Docker-backed tests, see `docs/process/coding_standards.md` on mocks) |
| `config/` | Minimal | `llm.yaml`, `platform.yaml` — real, small, checked-in configuration |
| `infra/` | Minimal | Docker Compose and environment config, ~5 files |
| `platform_sdk/` | **Stub-level** | Exactly one real file: `schemas/manifest.schema.json`. No `ai-os-sdk` Python package exists yet — this is why Capability Packs still import Kernel internals directly (a documented, temporary compromise; see `capability_pack_contract.md`'s own dated exception note). |
| `workspace/` | Placeholder | `scratch/`/`temp/` with `.gitkeep` only — prototype scratch space, exempt from documentation-first (ADR-0003) |
| `ai_context/`, `assets/`, `dashboard/`, `experiments/`, `governance/`, `knowledge/`, `manifests/`, `platform_services/`, `projects/`, `scripts/`, `specs/`, `tools/`, `traceability/` | **Empty** | Directories exist (or are simply absent, depending on when last checked) but contain zero files. Each corresponds to a real, planned subsystem or artifact area (see `PROJECT_INDEX.md`) that has not been started. Do not assume any convention or content for these until a real step builds one. |

## What this means practically

- If a task references "the Dashboard" or "the Voice/Jarvis pack" or "Project Intelligence" — check this table first. As of this writing, none of them have any real code.
- `platform_sdk/` being nearly empty is a recurring, load-bearing fact: every Capability Pack module's own docstring that says "no `ai-os-sdk` exists yet, this is a documented temporary compromise" is referring to exactly this.
- This table will go stale as real work lands in previously-empty folders. Update it as part of whichever step first puts real content into one of the "Empty" rows above — the same discipline `implementation_status.md` already follows for subsystem status.
