"""``pack_contract_suite`` — the compliance test suite every Capability
Pack must run and pass (``platform_sdk.md`` §9).

This directory did not exist at all before this step (§1a: "neither the
module nor the ``platform_sdk/testing/`` directory that would hold it"
existed). It now exists, still empty of real content.

Filled in across two steps, split deliberately — see
``platform_sdk_v1_scope.md`` §4 for the full reasoning:

- **Step 8** — ``forbidden_imports.py``: check 7 alone (no provider
  SDK, no ``ai_os_kernel``, no other pack, no database driver, no HTTP
  client to a provider). This one check has no dependency on
  ``PackContext`` or any migrated pack, and is exactly the mechanism
  that would have caught the Software Engineering pack's current,
  hand-recorded direct-Kernel-import exception — the highest-leverage,
  lowest-dependency piece of this suite, so it ships first.
- **Step 15** — the remaining 8 checks (manifest validation is already
  real elsewhere, via the Manifest Loader; checks 2–6, 8, 9: entry-point
  resolution, I/O-model matching, workflow step resolution, trust-tier
  consistency, permission vocabulary, prompt existence, and clean
  activation/deactivation), run end to end against the by-then-migrated
  Software Engineering pack.

No pack is compliant, and none is checked by anything beyond manifest
JSON Schema validation, until step 15 completes.
"""

from __future__ import annotations
