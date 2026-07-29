"""``pack_contract_suite`` — the compliance test suite every Capability
Pack must run and pass (``platform_sdk.md`` §9).

This directory did not exist at all before step 8 (§1a: "neither the
module nor the ``platform_sdk/testing/`` directory that would hold it"
existed).

Filled in across two steps, split deliberately — see
``platform_sdk_v1_scope.md`` §4 for the full reasoning:

- **Step 8 (done)** — :mod:`forbidden_imports` (check 7 alone: no
  provider SDK, no ``ai_os_kernel``, no other pack, no database driver,
  no direct HTTP client) and :mod:`waiver` (the documented, expiring
  exception mechanism that lets check 7 be wired into CI today without
  turning it red for six steps — see that module's own docstring). This
  one check has no dependency on ``PackContext`` or any migrated pack,
  and is exactly the mechanism that would have caught the Software
  Engineering pack's current, hand-recorded direct-Kernel-import
  exception — the highest-leverage, lowest-dependency piece of this
  suite, so it shipped first.
- **Step 15** — the remaining 8 checks (manifest validation is already
  real elsewhere, via the Manifest Loader; checks 2–6, 8, 9: entry-point
  resolution, I/O-model matching, workflow step resolution, trust-tier
  consistency, permission vocabulary, prompt existence, and clean
  activation/deactivation), run end to end against the by-then-migrated
  Software Engineering pack.

No pack is fully compliant, and none is checked by anything beyond
manifest JSON Schema validation plus check 7, until step 15 completes.
"""

from __future__ import annotations

from ai_os_sdk.testing.forbidden_imports import (
    ForbiddenImportCategory,
    ForbiddenImportViolation,
    group_by_category,
    scan_module_source,
    scan_pack_source,
)
from ai_os_sdk.testing.waiver import (
    ImportWaiver,
    WaiverApplication,
    WaiverFileError,
    apply_waiver,
    load_waiver,
    render_report,
)

__all__ = [
    "ForbiddenImportCategory",
    "ForbiddenImportViolation",
    "ImportWaiver",
    "WaiverApplication",
    "WaiverFileError",
    "apply_waiver",
    "group_by_category",
    "load_waiver",
    "render_report",
    "scan_module_source",
    "scan_pack_source",
]
