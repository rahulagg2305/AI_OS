# Changelog — Platform SDK (`ai-os-sdk`)

All notable changes to this package are documented here. Format
loosely follows [Keep a Changelog](https://keepachangelog.com/). This
package has not yet cut a version past `0.1.0`.

## [0.1.0] - 2026-07-28

### Added

- **Packaging scaffold only** (`platform_sdk_v1_scope.md` step 1). Real,
  installable `ai-os-sdk` PEP 621 distribution; `src/ai_os_sdk/` package
  with six stub subpackages (`contracts/`, `models/`, `errors/`,
  `sdk/`, `utilities/`, `testing/`), each a docstring-only `__init__.py`
  naming what it will hold and which future step fills it in. Added to
  the root workspace's `[tool.uv.workspace]` members and
  `[tool.uv.sources]`. No Protocol, model, or error class exists yet;
  nothing consumes this package yet.
