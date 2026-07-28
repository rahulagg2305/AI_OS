# Changelog — Template Capability Pack

**Template only — not a real pack.** See [`README.md`](README.md). This file exists so that
a pack copied from this template starts with a changelog in place; replace its content
entirely with your own pack's first entry.

Format loosely follows [Keep a Changelog](https://keepachangelog.com/). Packs use semantic
versioning, as required by
[`capability_pack_contract.md`](../../docs/03_architecture/capability_framework/capability_pack_contract.md).

## [0.1.0] - 2026-07-25

### Added

- Initial minimal, schema-valid [`manifest.yaml`](manifest.yaml) — identity only: no
  `permissions`, `agents`, `tools`, `workflows`, `qualityGates`, `prompts`, or `commands`,
  and therefore no `entryPoint`.

## Unreleased

### Changed

- 2026-07-28 — `README.md` expanded: marked unambiguously as a scaffold, linked to the
  authoritative contract and schema documents and to the one real example pack
  ([`../software-engineering/`](../software-engineering/)), and recorded the two current
  contract caveats (no `ai-os-sdk` package exists; no pack contract test suite exists).
  No change to `manifest.yaml`, so the version is unchanged.
