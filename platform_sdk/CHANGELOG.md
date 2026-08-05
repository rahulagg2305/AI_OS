# Changelog — Platform SDK (`ai-os-sdk`)

All notable changes to this package are documented here. Format
loosely follows [Keep a Changelog](https://keepachangelog.com/). This
package has not yet cut a version past `0.1.0`.

## [0.1.0] - 2026-07-28 (last updated 2026-08-05)

### Added

- **`TraceContext.prompt_id`/`prompt_version`** (`P04-S01-M12-T10`), two new
  optional fields (§8: a new optional field is a minor bump, never breaking).
  Closes a real gap found wiring call recording into the SDK-native agent
  path: `evaluation.llm_calls` requires `prompt_id`/`prompt_version` together
  with `agent_id` (real foreign keys, never optional at the storage layer),
  but the documented §4.1 shape had no carrier for which prompt a given
  `LLMRequest` rendered. Every agent in the one real pack that calls the LLM
  already has both values locally (read from its own `inputs` to render the
  prompt) — each now also passes them into the `TraceContext` it already
  builds. **No existing caller supplying neither is affected** — both default
  to `None`, the identical "absent means unaffected" shape `agent_id` already
  established. `platform_sdk.md` §4.1's documented shape updated to match.

- **The `ToolInvoker` Protocol, `ToolDescriptor`, `ToolStatus`, `ToolResult`, and
  the `platform.sandbox.run_command` tool concept** (`platform_sdk_v1_scope.md`
  step 6), at the from-scratch shape decided in step 2a:
  `invoke(tool_id, inputs, *, timeout_seconds) -> ToolResult` +
  `available_tools() -> tuple[ToolDescriptor, ...]`, grounded in a real,
  platform-provided tool id (`PLATFORM_SANDBOX_RUN_COMMAND_DESCRIPTOR`) since
  the one real pack declares zero tools and the one real sandboxed tool
  ignores its own inputs. `ToolResult` narrows `stdout_ref`/`stderr_ref` to
  inline strings and drops `artifacts` (no `StorageService`), and **extends**
  the documented shape with `timed_out`/`truncated` — two real outcomes the
  original spec cannot express. **Proven against the real, actually-executed
  `LocalSubprocessSandbox`** (a genuine clean run, timeout, and output-cap
  breach), not hand-built values — which found and fixed two real bugs
  first: `ToolResult`'s own validator wrongly required `exit_code` whenever
  `timed_out` was `False` (disproven — a cap breach kills the process before
  it can exit, leaving `exit_code=None` with `timed_out=False` too), and a
  real circular import between `ai_os_sdk.errors` and `ai_os_sdk.models`
  (fixed by relocating `ErrorCategory`/`StructuredError` into a new
  `ai_os_sdk.models.error` module; both remain fully public via
  `ai_os_sdk.errors`). `TrustTier` also relocated from
  `ai_os_sdk.contracts.tool` to `ai_os_sdk.models.tool` for the same
  layering reason, re-exported unchanged. **No Kernel or pack source was
  modified.**

- **The `PromptRegistry` Protocol and `RenderedPrompt`** (`platform_sdk_v1_scope.md`
  step 5), kept at the documented pack-facing keyword call style
  (`render(prompt_id, variables, *, version)`) rather than the Kernel's own
  request-object envelope — the one deliberate reversal in the specification's
  favour from step 2a, since a pack-facing Protocol should be shaped for its
  caller, not its implementer (ADR-0004). `version` is keyword-only and
  required — nothing resolves a default on a caller's behalf. `RenderedPrompt`
  narrowed to `prompt_id`/`version`/`content`, matching the real
  `PromptRenderResponse` exactly; `get()`/`PromptDefinition` and two
  `RenderedPrompt` fields (`variables_used`, `cache_boundary_index`) stay
  deferred — no implementation exists at any layer. **No real Kernel class
  satisfies this Protocol** (it's a from-scratch call convention, not a
  narrowing), so instead of an `isinstance` proof, the conversion to/from the
  real `PromptRenderRequest`/`PromptRenderResponse` is proven lossless in both
  directions — the reference conversion functions are test-local and
  illustrative, not shipped SDK code. **No Kernel or pack source was modified.**

- **The `LLMGateway` Protocol and its model set** (`platform_sdk_v1_scope.md`
  step 4), narrowed to `complete()` + `capabilities()` — the only two methods
  the real, working `DispatchingLLMGateway` implements. `ai_os_sdk.models.llm`
  adds `Message`/`MessageRole`/`LLMRequest`/`StopReason`/`UsageRecord`/
  `LLMResponse` as field-for-field mirrors of the real Kernel models, and
  `ProviderCapabilities` extended to the real 13-field shape (the working
  `StaticCapabilityNegotiator` already implements all 13; its own docstring
  names `platform_sdk.md` as the discrepancy it "implements past"). **Proven
  against the real `DispatchingLLMGateway`**, constructed with an empty router
  and no providers (zero I/O); `EchoLLMGateway` correctly does *not* satisfy
  the SDK Protocol, since it implements only `complete()`. **No Kernel or pack
  source was modified.**

- **The `Agent` and `Tool` Protocols, plus `TrustTier`** (`platform_sdk_v1_scope.md`
  step 3), at the narrowed shapes decided in step 2a: dict-based
  `execute(inputs) -> outputs` with a declared `output_schema`, and `trust_tier`
  on `Tool`. Both `@runtime_checkable`. `TrustTier` is defined here rather than
  imported from the Kernel — the SDK is the dependency floor (`platform_sdk.md`
  §2 rule 1) — and both enums independently mirror `manifest.schema.json`'s
  `tools[].trustTier`. **Structural compatibility is proven against real classes,
  not mocks:** all five pack agents and `EchoAgent` satisfy `Agent`; `EchoTool`
  and `SandboxedCommandTool` satisfy `Tool`; **no Kernel or pack source was
  modified.** `AgentRequest`/`AgentResult`/`ToolRequest` are deliberately absent
  (no consumer under the narrowed shapes); `ToolResult` arrives in step 6 with
  `ToolInvoker`.

- **The `AiOsError` hierarchy, `StructuredError`, and the four shared boundary
  models** (`platform_sdk_v1_scope.md` step 2). `ai_os_sdk.errors` now holds
  `ErrorCategory` (all six documented categories), `StructuredError`, and
  `AiOsError` → `TransientError`/`PermanentError`/`QualityError`/
  `InfrastructureError`/`BudgetExceededError`/`SecurityError`, each mapping 1:1
  onto a `StructuredError` via `to_structured_error()`. `ai_os_sdk.models` now
  holds `ArtifactRef`, `TraceContext` (the canonical §4.1 shape the Kernel's two
  partial versions both cite), `SecurityContext`, and `StepBudget`. All frozen;
  `max_cost_usd` is a `Decimal`, never a float, per `data_model.md` §2. A
  `py.typed` marker was added so consuming packages get these types — the same
  omission that cost 15 mypy errors in the Software Engineering pack.
  **Consumed by nothing yet**; no existing code changed.

- **Packaging scaffold only** (`platform_sdk_v1_scope.md` step 1). Real,
  installable `ai-os-sdk` PEP 621 distribution; `src/ai_os_sdk/` package
  with six stub subpackages (`contracts/`, `models/`, `errors/`,
  `sdk/`, `utilities/`, `testing/`), each a docstring-only `__init__.py`
  naming what it will hold and which future step fills it in. Added to
  the root workspace's `[tool.uv.workspace]` members and
  `[tool.uv.sources]`. No Protocol, model, or error class exists yet;
  nothing consumes this package yet.
