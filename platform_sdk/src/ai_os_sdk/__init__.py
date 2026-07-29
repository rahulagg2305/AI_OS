"""``ai_os_sdk`` — the Platform SDK: the only sanctioned interface
between a Capability Pack and AI_OS (``docs/03_architecture/platform/
platform_sdk.md``).

**Packaging scaffold only, as of this step
(``docs/03_architecture/platform/platform_sdk_v1_scope.md`` step 1).**
This package imports cleanly and is installable, but defines no
Protocol, no boundary model, and no error class yet. Six subpackages
exist as stubs, each filled in by its own future, individually-approved
step per the scope document's ordered sequence:

- :mod:`ai_os_sdk.errors`     — step 2 (``AiOsError`` hierarchy)
- :mod:`ai_os_sdk.models`     — steps 2–3, 4, 5, 6, 7 (boundary models,
  added incrementally alongside the Protocol each belongs to)
- :mod:`ai_os_sdk.contracts`  — steps 3–7 (the Protocol definitions)
- :mod:`ai_os_sdk.sdk`        — step 7 (concrete, non-Protocol helpers,
  e.g. a ``PromptedAgent`` base — see the scope document §5 for why
  this subpackage's purpose is a proposal awaiting confirmation, not
  yet a settled design)
- :mod:`ai_os_sdk.utilities`  — deliberately empty in v1.0.0; no real
  pack code generates its own ids/hashes/canonical JSON today (checked
  directly against ``capability_packs/software-engineering/src/``), so
  there is nothing to build yet (scope document §5)
- :mod:`ai_os_sdk.testing`    — step 8 (``pack_contract_suite`` check 7,
  the forbidden-import scanner); the remaining 8 checks land in step 15

No pack depends on this package yet. Migrating the five real Software
Engineering pack agents onto it is steps 9–13 of the same scope
document; nothing consumes ``ai_os_sdk`` until then.
"""

from __future__ import annotations
