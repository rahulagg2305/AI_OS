# Interface Stability and Versioning Policy

**Status:** Active · **Introduced:** Phase R2 (2026-07-31)

How a module whose interface other code depends on gets changed *after*
it is declared stable. Short on purpose.

## Stability levels

Every module carries exactly one level. Absent a declaration, a module
is **experimental**.

| Level | Meaning | Change rule |
|---|---|---|
| **experimental** | Interface may change without notice. | Change freely; update callers in the same step. |
| **stable** | Other modules or packs depend on the shape. | Additive changes only. A breaking change needs the procedure below. |
| **frozen** | Published outside the repo boundary (the SDK, the manifest schema, the HTTP API). | Breaking change requires a version bump *and* a deprecation window. |

Currently **frozen**: `ai-os-sdk` public contracts (M27),
`manifest.schema.json` (M28), the `/api/v1` HTTP surface (M36).
Currently **stable**: Workflow Engine executor/repository Protocols
(M05), LLM Gateway `LLMGateway` Protocol (M06).

## What counts as breaking

Removing or renaming a public name; adding a required parameter;
narrowing an accepted input; widening a raised error type; changing a
persisted shape or a wire shape. Adding an **optional** parameter with a
default that preserves existing behaviour is *not* breaking — this is the
pattern already used repeatedly (`quality_gate_executor=None`,
`gate_result_recorder=None`, `pack_root=None`).

## Changing a frozen module

1. **Prefer additive.** An optional parameter defaulting to today's
   behaviour is always the first option considered, and usually correct.
2. **If genuinely breaking:** bump the published version (SemVer major
   for `ai-os-sdk`; `schemaVersion` for the manifest; a new path prefix
   for the HTTP API — never a silent change to `/api/v1`).
3. **Deprecation window.** The old shape keeps working for at least one
   full Stage, emitting a deprecation warning naming the replacement.
4. **Record it** as its own Task ticket, and add a Risk Register entry if
   any consumer outside this repo could be affected.
5. **Prove both shapes** with real tests during the window.

## Enforcement

- `scripts/check_import_boundaries.py` (CI) prevents packs from reaching
  past the frozen SDK boundary into Kernel internals.
- `tests/contract/` runs the 9-check pack contract suite against the real
  pack on every push.
- The published OpenAPI artifact plus its drift check
  (`docs/process/api_contract_boundary.md`) is the equivalent gate for
  the HTTP surface.
