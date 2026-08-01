# ADR-0009: Packaging and Dependency Management — uv Workspace with Entry-Point Discovery

**Status:** Accepted
**Date:** 2026-07-25
**Decision Makers:** Chief Architect
**Related Documents:** `docs/03_architecture/platform/technology_stack.md`, `docs/03_architecture/kernel/manifest_loader.md`

---

## Context

Capability Packs must be independently installable, upgradable, and removable, and the Kernel must be able to discover them without hardcoding a list. The repository is a monorepo containing the Kernel, the SDK, shared services, and several packs, each of which needs its own dependency set and its own version.

## Decision

**`uv` workspace monorepo with PEP 621 `pyproject.toml` per distribution, and a single locked `uv.lock` at the repository root.**

Distributions:

| Distribution | Path | Depends on |
|---|---|---|
| `ai-os-sdk` | `platform_sdk/` | nothing internal (the dependency floor) |
| `ai-os-kernel` | `kernel/` | `ai-os-sdk` |
| `ai-os-services` | `platform_services/` | `ai-os-sdk` |
| `ai-os-pack-<name>` | `capability_packs/<name>/` | `ai-os-sdk` **only** |
| `ai-os-cli` | `tools/cli/` | `ai-os-sdk` |

**The dependency rule is enforced mechanically, not by convention:** a Capability Pack may declare a dependency on `ai-os-sdk` and third-party libraries. A pack that declares a dependency on `ai-os-kernel`, `ai-os-services`, or another pack fails CI. This is what makes [ADR-0001](ADR-0001-modular-capability-pack-architecture.md) real rather than aspirational.

**Pack discovery uses two mechanisms, in this order:**
1. **Entry points** — installed packs register under the `ai_os.capability_packs` entry-point group. This is the production mechanism and supports packs installed from outside the repository.
2. **Filesystem scan** — configured directories are scanned for `manifest.yaml`. This is the development mechanism and supports packs not yet installed.

In both cases the `manifest.yaml` remains the single source of truth for what the pack provides; the entry point only says *where the pack is*. A pack discovered by either route is validated identically ([ADR-0003](ADR-0003-documentation-first-development.md) requires no exception path).

Version pinning: exact pins in `uv.lock`, checked in. Ranges in `pyproject.toml`. Reproducible installs via `uv sync --frozen` in CI and in container builds.

## Alternatives Considered

- **Poetry** — Mature and widely known; rejected because workspace support for a monorepo of independently versioned distributions is weaker, and resolution/install speed matters in a CI matrix that installs many times per run.
- **pip + requirements.txt** — Rejected: no lockfile guarantees, no workspace concept, and multi-distribution management becomes manual.
- **PDM / Hatch** — Both viable; `uv` chosen for install speed, a single tool covering Python version management, locking, and running, and reproducible `--frozen` installs.
- **One monolithic distribution** — Simplest; rejected because it makes packs non-removable and non-independently-versionable, contradicting the Capability Pack Contract.
- **Discovery by filesystem scan only** — Rejected: prevents installing a pack from a package index, which is the eventual distribution model.

## Consequences

### Positive
- Packs are genuinely independent artifacts with their own versions and dependency sets.
- The pack→kernel dependency prohibition is CI-enforceable.
- Reproducible builds across dev, CI, and production images.

### Negative
- Contributors must learn `uv` and the workspace layout.
- Dependency conflicts between packs sharing one environment are possible; detected at lock time. If two packs ever require genuinely incompatible versions, that is the trigger to reconsider process isolation ([ADR-0020](ADR-0020-deployment-topology-and-scaling.md)) — recorded here as a known future decision point rather than solved prematurely.

### Neutral
- `uv.lock` conflicts on concurrent dependency changes require regeneration rather than manual merge.

## Compliance

Complies with the Capability Pack Contract (independently installable, versioned, removable) and semantic versioning requirements.

## References

- `docs/06_capability_packs/capability_pack_development_guide.md`

---

## Implementation Status (appended 2026-07-28, updated 2026-08-01 — not part of the Accepted decision)

**Status in code:** Partially implemented

The `uv` workspace is real, with a committed `uv.lock` and shared tool configuration at the root. **`ai-os-sdk` now exists** (`platform_sdk/`, built under a separate Platform SDK initiative) alongside `ai-os-kernel` and `ai-os-pack-software-engineering`; `ai-os-services` and `ai-os-cli` still do not. **Both decided discovery mechanisms are now built** (`P01-S03-M02-T03`, 2026-08-01): the filesystem scan for `manifest.yaml`, and the `ai_os.capability_packs` entry-point group (`kernel/src/ai_os_kernel/manifest_loader/discovery.py`, `discover_entry_point_manifests()`), combined and validated identically by `ManifestLoader.scan()`. No pack in this repository registers under that entry-point group yet — proven against a real, synthetic installed distribution in tests, not yet exercised by a real published pack.

Live status: [`feature_inventory.md`](../../19_roadmap/feature_inventory.md) · Build history: [`history/INDEX.md`](../../19_roadmap/history/INDEX.md)
