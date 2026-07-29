# Platform SDK (`ai-os-sdk`)

The only sanctioned interface between a Capability Pack and AI_OS
(`docs/03_architecture/platform/platform_sdk.md`).

## Status: error taxonomy, shared boundary models, and five Protocols

**Last updated: 2026-07-29.**

This package is real, installable, and importable. It defines the platform
error taxonomy, the shared boundary models, and the `Agent`/`Tool`/
`LLMGateway`/`PromptRegistry`/`ToolInvoker` Protocols. `Agent`, `Tool`, and
`LLMGateway` are **narrowings of real Kernel shapes** — every one of the
five real Software Engineering pack agents, both real tools, and the real
production `DispatchingLLMGateway` already satisfy them without
modification (proven in
`tests/unit/platform_sdk/test_kernel_satisfies_sdk_contracts.py`).
`PromptRegistry` and `ToolInvoker` are **from-scratch designs** — no Kernel
class satisfies either directly, so each is proven differently:
`PromptRegistry`'s conversion to/from the real `PromptRenderRequest`/
`PromptRenderResponse` is proven **lossless in both directions**;
`ToolInvoker`'s `ToolResult` is proven against the **real, actually-executed**
`LocalSubprocessSandbox` (a genuine clean run, timeout, and output-cap
breach), which found and fixed two real bugs — an over-strict validator and
a circular import — before they could reach the Kernel-side adapter.
Steps 1, 2, 2a, 3, 4, 5, and 6 of the **18**-step build sequence in
[`../docs/03_architecture/platform/platform_sdk_v1_scope.md`](../docs/03_architecture/platform/platform_sdk_v1_scope.md)
are complete. *(The sequence was revised from 15 to 18 steps after an
independent architecture review — see that document's §6a.)*

| Subpackage | Holds | Status |
|---|---|---|
| `errors/` | `AiOsError` + 6 subclasses (`ErrorCategory`/`StructuredError` re-exported from `models.error`) | **Real** (step 2) |
| `models/` | `ArtifactRef`, `TraceContext`, `SecurityContext`, `StepBudget`, `LLMRequest`/`LLMResponse`/`UsageRecord`/`ProviderCapabilities` (13 fields), `RenderedPrompt`, `TrustTier`/`ToolDescriptor`/`ToolStatus`/`ToolResult`, `ErrorCategory`/`StructuredError` (`models.error`) | **Real** (steps 2, 4, 5, 6); context/pack step 7 |
| `contracts/` | `Agent`, `Tool`, `LLMGateway`, `PromptRegistry`, `ToolInvoker` | **Real** (steps 3, 4, 5, 6, at the shapes decided in 2a); `ContextService`/`CapabilityPack` step 7 |
| `sdk/` | Concrete helper implementations (proposed content, see the scope document §5) | Step 7 |
| `utilities/` | ids/hashing/canonical JSON — deliberately empty, no real caller exists yet | Not scheduled |
| `testing/` | `pack_contract_suite` | Step 8 (check 7 + waiver) and step 15 (the remaining 8) |

`SecretResolver` was **dropped** from v1.0.0: the one real pack declares
no secret permission, so granting it one would violate `platform_sdk.md`
§6. See the scope document §2.3.

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
