# Changelog — Platform SDK (`ai-os-sdk`)

All notable changes to this package are documented here. Format
loosely follows [Keep a Changelog](https://keepachangelog.com/). This
package has not yet cut a version past `0.1.0`.

## [0.1.0] - 2026-07-28 (last updated 2026-07-29)

### Added

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
