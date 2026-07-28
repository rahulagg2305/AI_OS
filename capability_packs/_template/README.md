# Capability Pack Template — scaffold only, not a real pack

> **This directory is a template.** It declares no agents, no tools, and no workflows, and
> it must never be activated as a real pack. It exists so that manifest discovery and JSON
> Schema validation can be proven end to end (Implementation Roadmap Stage A), and as the
> starting point you copy when creating a pack.
>
> For a **real, working example**, read [`../software-engineering/`](../software-engineering/) —
> currently the only real pack in this repository.

## Creating a pack from this template

```sh
cp -r capability_packs/_template capability_packs/<your-pack-id>
```

Then edit [`manifest.yaml`](manifest.yaml):

1. Change `metadata.id`, `metadata.name`, `metadata.description`, and `metadata.owner`.
   `metadata.id` must match your directory name.
2. Choose a real `metadata.license` once the project owner has decided one. `UNLICENSED`
   here records honestly that no licence has been chosen — it is not a placeholder to
   leave in a real pack indefinitely.
3. Add `permissions`, `agents`, `tools`, `workflows`, `qualityGates`, `prompts`, and
   `commands` entries as your pack grows, following the field reference in
   [`manifest_schema.md`](../../docs/03_architecture/capability_framework/manifest_schema.md).
4. Validate against [`../../platform_sdk/schemas/manifest.schema.json`](../../platform_sdk/schemas/manifest.schema.json)
   — this is the authoritative machine-readable schema, and it is what
   `ai_os_kernel.manifest_loader.ManifestLoader` validates against at load time.

An `entryPoint` becomes **required** the moment `agents` or `workflows` gains an entry (a
conditional `allOf` in the JSON Schema enforces this). It names a class implementing the
`CapabilityPack` Protocol.

## What this template deliberately does not include

A real pack also needs a `pyproject.toml` (it is its own distribution — see
[ADR-0009](../../docs/18_decision_log/adr/ADR-0009-packaging-and-dependency-management.md)),
a `src/` package, a `tests/` directory, and a `CHANGELOG.md`. This template ships only
`manifest.yaml`, `README.md`, and `CHANGELOG.md` — copy the structure of
[`../software-engineering/`](../software-engineering/) for the rest.

## The contract your pack must satisfy

- [`capability_pack_contract.md`](../../docs/03_architecture/capability_framework/capability_pack_contract.md)
  — the authoritative pack contract: structure, lifecycle, testing requirements, and the
  prohibitions (no provider SDKs, no Kernel dependency, no direct provider credentials)
- [`manifest_schema.md`](../../docs/03_architecture/capability_framework/manifest_schema.md)
  — every manifest field, with the JSON Schema as its machine-readable form
- [`capability_pack_development_guide.md`](../../docs/06_capability_packs/capability_pack_development_guide.md)
  — the walkthrough
- [`platform_sdk.md`](../../docs/03_architecture/platform/platform_sdk.md) — the SDK
  Protocols a pack is supposed to consume, including `CapabilityPack` and `PackContext`

## Two honest caveats about the contract today (2026-07-28)

Both apply to any pack you create from this template, and both are tracked gaps rather
than intended design:

1. **There is no `ai-os-sdk` package yet.** `platform_sdk/` contains exactly one real
   file, `schemas/manifest.schema.json`; its `contracts/`, `models/`, `sdk/`,
   `utilities/`, and `prompts/` directories are empty. Until it exists, a pack that needs
   platform capabilities must import Kernel internals directly, as
   [`../software-engineering/`](../software-engineering/) does under a dated, documented
   exception in `capability_pack_contract.md`. That contradicts
   [ADR-0009](../../docs/18_decision_log/adr/ADR-0009-packaging-and-dependency-management.md)'s
   rule that a pack depends on `ai-os-sdk` **only**, and is temporary.
2. **The pack contract test suite does not exist.** `capability_pack_contract.md`'s
   Testing Requirements and [ADR-0015](../../docs/18_decision_log/adr/ADR-0015-testing-and-ci.md)
   both specify `ai_os_sdk.testing.pack_contract_suite`, which every pack must run against
   itself. Nothing in this codebase provides it yet, so contract compliance is currently
   verified by review and by each pack's own tests.

Current state of both: [`../../docs/19_roadmap/feature_inventory.md`](../../docs/19_roadmap/feature_inventory.md).
