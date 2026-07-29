"""The ``AiOsError`` exception hierarchy and ``StructuredError`` model —
one taxonomy for the whole platform (``platform_sdk.md`` §4.4,
matching ``docs/03_architecture/workflow/error_handling_retry.md`` §3/§8).

Real as of ``platform_sdk_v1_scope.md`` step 2. Everything lives in
:mod:`ai_os_sdk.errors.taxonomy` and is re-exported here, so callers
import from ``ai_os_sdk.errors`` and never need to know the module
layout underneath.

Consumed by nothing yet: the Protocols and boundary contracts that carry
these types land in steps 3–7, and the pack migrations that raise them
in steps 9–14.

Every other subsystem in this codebase still defines its own local,
unrelated exceptions (for example ``ai_os_kernel/llm_gateway/errors.py``,
inheriting from plain ``Exception``). **None of them migrate onto this
hierarchy as part of the Platform SDK build** — that is Kernel-side
work, tracked separately (``docs/19_roadmap/feature_inventory.md``
module 44).
"""

from __future__ import annotations

from ai_os_sdk.errors.taxonomy import (
    AiOsError,
    BudgetExceededError,
    ErrorCategory,
    InfrastructureError,
    PermanentError,
    QualityError,
    SecurityError,
    StructuredError,
    TransientError,
)

__all__ = [
    "AiOsError",
    "BudgetExceededError",
    "ErrorCategory",
    "InfrastructureError",
    "PermanentError",
    "QualityError",
    "SecurityError",
    "StructuredError",
    "TransientError",
]
