# Project Intelligence Capability Pack

Understand, analyse, and document existing or legacy codebases
(`docs/06_capability_packs/project_intelligence/overview.md`).

## Status: one real Tool — repository ingestion and structural model

**First real increment (`P05-S02-M32-T01`, 2026-08-09).** This pack
declares no agents or workflows yet and has no `manifest.yaml` —
nothing here needs pack activation. It contains one real Tool,
[`repository_ingestion.py`](src/ai_os_pack_project_intelligence/tools/repository_ingestion.py):
walks a real repository directory and builds a real module/file
inventory (FR-050) — file counts per language, per-file classification,
top-level module grouping.

**`tier1_sandboxed`, genuinely** — ADR-0016's own Decision text is
unconditional: "Any tool that ... processes untrusted repository
content is Tier 1." The walk itself runs as a real script through a
directly-injected `sandbox` (mirrors
`ai_os_pack_software_engineering.tools.fs_read`'s own exact shape:
`self.sandbox: Any = None`, injected post-construction by a real caller
— this pack cannot import `ai_os_kernel` at all, so it never
constructs a real `SandboxExecutor` itself). Proven end to end against
a real Docker daemon in `tests/integration/sandbox/
test_repository_ingestion_live.py`, plus fast, mocked-Docker
construction/validation tests in `tests/test_repository_ingestion.py`.

Not yet wired into any real agent, workflow, or manifest — that is
later, separate work (the documented `existing-project-analyzer`
agent's own eventual scope), the identical "prove standalone first,
wire in later" precedent every real Tool in this project has followed.
