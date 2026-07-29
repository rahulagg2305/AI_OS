# Platform SDK (`ai-os-sdk`)

The only sanctioned interface between a Capability Pack and AI_OS
(`docs/03_architecture/platform/platform_sdk.md`).

## Status: packaging scaffold only

**Last updated: 2026-07-28.**

This package is real, installable, and importable — `import ai_os_sdk`
works — but defines **no Protocol, no boundary model, and no error
class yet**. It is Step 1 of the 15-step build sequence in
[`../docs/03_architecture/platform/platform_sdk_v1_scope.md`](../docs/03_architecture/platform/platform_sdk_v1_scope.md).

| Subpackage | Holds | Filled in by |
|---|---|---|
| `errors/` | `AiOsError` hierarchy, `StructuredError` | Step 2 |
| `models/` | Pydantic boundary models | Steps 2–3, 4, 5, 6, 7 |
| `contracts/` | Protocol definitions | Steps 3–7 |
| `sdk/` | Concrete helper implementations (proposed content, see the scope document §5) | Step 7 |
| `utilities/` | ids/hashing/canonical JSON — deliberately empty, no real caller exists yet | Not scheduled |
| `testing/` | `pack_contract_suite` | Steps 8 (check 7) and 15 (the remaining 8) |

No pack depends on this package yet. The Software Engineering pack
(`capability_packs/software-engineering/`) still imports `ai_os_kernel`
internals directly — a documented, hard-gated exception
(`docs/03_architecture/capability_framework/capability_pack_contract.md`)
that steps 9–14 of the scope document close.

`schemas/manifest.schema.json` is unrelated to this package's Python
code and predates it — the Capability Pack manifest JSON Schema,
already real and enforced by the Manifest Loader. Its path
(`platform_sdk/schemas/manifest.schema.json`) is referenced by string
literal in over a dozen places across the Kernel and test suite; it
does not move as part of this or any future SDK step.

## Related documents

- [`../docs/03_architecture/platform/platform_sdk.md`](../docs/03_architecture/platform/platform_sdk.md) — the full specification this package implements
- [`../docs/03_architecture/platform/platform_sdk_v1_scope.md`](../docs/03_architecture/platform/platform_sdk_v1_scope.md) — the build sequence this README's table mirrors
- [`../docs/03_architecture/capability_framework/capability_pack_contract.md`](../docs/03_architecture/capability_framework/capability_pack_contract.md) — the growth gate this package's completion (step 15) lifts
