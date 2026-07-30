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
- **Step 15 (done)** — :mod:`pack_contract_suite`: checks 1-6, 8, 9
  (manifest validity, entry-point resolution, I/O-model matching,
  workflow step resolution, trust-tier consistency, permission
  vocabulary, prompt existence, clean activation/deactivation), plus
  :func:`~ai_os_sdk.testing.pack_contract_suite.run_pack_contract_suite`,
  which also wraps check 7 (unchanged) into one unified, 9-check report.
  Run end to end against the by-then-fully-migrated Software Engineering
  pack — see that module's own docstring for a discovered, corrected
  arithmetic note: this was "the remaining 7 checks," not 8 (check 1
  was never outstanding; only checks 2-6, 8, 9 were).

Every check now runs for real against the Software Engineering pack —
see ``tests/contract/test_pack_contract_suite.py`` for the executed
proof, wired into CI via the already-prepared
``hashFiles('tests/contract/**')``-gated step in ``.github/workflows/ci.yml``.
"""

from __future__ import annotations

from ai_os_sdk.testing.forbidden_imports import (
    ForbiddenImportCategory,
    ForbiddenImportViolation,
    group_by_category,
    scan_module_source,
    scan_pack_source,
)
from ai_os_sdk.testing.pack_contract_suite import (
    PackContractCheckResult,
    PackContractSuiteReport,
    check_1_manifest_is_valid,
    check_2_entry_points_resolve,
    check_3_io_models_match,
    check_4_workflow_steps_resolve,
    check_5_trust_tier_consistency,
    check_6_permission_vocabulary,
    check_7_no_forbidden_imports,
    check_8_required_prompts_exist,
    check_9_clean_activation,
    render_suite_report,
    run_pack_contract_suite,
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
    "PackContractCheckResult",
    "PackContractSuiteReport",
    "WaiverApplication",
    "WaiverFileError",
    "apply_waiver",
    "check_1_manifest_is_valid",
    "check_2_entry_points_resolve",
    "check_3_io_models_match",
    "check_4_workflow_steps_resolve",
    "check_5_trust_tier_consistency",
    "check_6_permission_vocabulary",
    "check_7_no_forbidden_imports",
    "check_8_required_prompts_exist",
    "check_9_clean_activation",
    "group_by_category",
    "load_waiver",
    "render_report",
    "render_suite_report",
    "run_pack_contract_suite",
    "scan_module_source",
    "scan_pack_source",
]
