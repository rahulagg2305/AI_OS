# Capability Pack Template

Copy this directory to start a new Capability Pack:

```sh
cp -r capability_packs/_template capability_packs/<your-pack-id>
```

Then edit `manifest.yaml`:

1. Change `metadata.id`, `metadata.name`, `metadata.description`, and `metadata.owner`.
2. Choose a real `metadata.license` once the project owner has decided one.
3. Add `agents`, `tools`, `workflows`, `qualityGates`, `prompts`, and `commands` entries
   as your pack grows, following
   `docs/03_architecture/capability_framework/manifest_schema.md`.
4. Validate against `platform_sdk/schemas/manifest.schema.json`.

An `entryPoint` is required once you declare any `agents` or `workflows` — implement the
`CapabilityPack` Protocol described in the Platform SDK Specification
(`docs/03_architecture/platform/platform_sdk.md` §7).

## Status

This template intentionally has **no agents, tools, or workflows**. It exists only to
prove manifest discovery and schema validation end to end (Implementation Roadmap
Stage A). Do not activate it as a real pack.
