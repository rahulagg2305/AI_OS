# Project Intelligence Capability Pack

Understand, analyse, and document existing or legacy codebases
(`docs/06_capability_packs/project_intelligence/overview.md`).

## Status: four real Tools, all with real, structural provenance tagging

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

**Second real increment (`P05-S02-M32-T02`, 2026-08-09).**
[`language_detection.py`](src/ai_os_pack_project_intelligence/tools/language_detection.py)
consumes the first Tool's own `files` output and detects languages,
build systems, and frameworks with real, disclosed confidence per
finding (FR-051). **`tier2_trusted`, not `tier1_sandboxed`** — a real,
disclosed classification distinct from `repository.ingest`: this Tool
never touches a filesystem, network, or executes anything; its only
operation is pattern-matching well-known basenames against an
already-extracted path list. Proven by 12 deterministic tests (no
sandbox/fake needed at all — pure computation).

**Third real increment (`P05-S02-M32-T03`, 2026-08-09).**
[`dependency_graph.py`](src/ai_os_pack_project_intelligence/tools/dependency_graph.py)
consumes the first Tool's own `files` output (filtered to Python) and
constructs a real, queryable module/dependency graph via the stdlib
`ast` module (FR-052) — real import edges, not a heuristic or an
edge-free artifact (design fork resolved via `AskUserQuestion`). Back
to **`tier1_sandboxed`** — reading and parsing real file *content* is
"processing untrusted repository content" per ADR-0016, unlike
`language.detect`'s path-only pattern matching. Scoped to Python only;
other languages are real, disclosed, deferred work. Proven by 11 tests
including 2 real, unmocked Docker tests (a real relative-import
package resolved correctly; a real syntax error reported without
failing the whole graph).

**Fourth real increment (`P05-S02-M32-T06`, 2026-08-09).** Every one
of the three Tools' outputs now carries a real, top-level
`trust: "untrusted"` field
([`provenance.py`](src/ai_os_pack_project_intelligence/provenance.py),
FR-059) — mirrors ADR-0016's own control 1 and the Context Manager's
already-real `ContextItem.trust`, independently defined here since
this pack cannot import `ai_os_kernel` at all (the identical
independent-mirroring precedent `ai_os_sdk.models.tool.TrustTier`
already establishes). Structural, not caller-configurable: no code
path in this pack could ever honestly produce `"trusted"`. Proven by 3
new tests (one per Tool), including a real, unmocked Docker test
confirming the tag survives the real sandboxed round trip.

**Fifth real increment (`P05-S02-M32-T04`, 2026-08-09).**
[`architecture_recovery.py`](src/ai_os_pack_project_intelligence/tools/architecture_recovery.py)
consumes `dependency.graph`'s own `nodes`/`edges` and performs real
deterministic graph analysis (FR-053) — module-level boundary
aggregation, real DFS-based circular-dependency detection, and real
fan-in/fan-out coupling metrics. **`tier2_trusted`** — the identical
reasoning `language.detect` already establishes (no filesystem/
execution, only traversal over already-derived structural data).
Deliberately not LLM-driven narrative documentation (design fork
resolved via `AskUserQuestion`): that remains real, disclosed, deferred
work for the eventual `existing-project-analyzer` agent. Proven by 12
deterministic tests, including real 2- and 3-module dependency cycles.

None of the four Tools is yet wired into any real agent, workflow, or
manifest — that is later, separate work (the documented
`existing-project-analyzer` agent's own eventual scope), the identical
"prove standalone first, wire in later" precedent every real Tool in
this project has followed.
