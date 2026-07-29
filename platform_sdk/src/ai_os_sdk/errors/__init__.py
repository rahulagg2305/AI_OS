"""The ``AiOsError`` exception hierarchy and ``StructuredError`` model —
one taxonomy for the whole platform (``platform_sdk.md`` §4.4,
matching ``docs/03_architecture/workflow/error_handling_retry.md`` §3/§8).

This directory did not exist at all before this step (``platform_sdk.md``
§1a: "``platform_sdk/errors/`` ... do[es] not exist at all, not even as
an empty director[y]"). It now exists, still empty of real content.

Filled in by ``platform_sdk_v1_scope.md`` step 2:

- ``taxonomy.py`` — ``AiOsError`` and its six subclasses
  (``TransientError``, ``PermanentError``, ``QualityError``,
  ``InfrastructureError``, ``BudgetExceededError``, ``SecurityError``),
  plus ``StructuredError``, the Pydantic model each exception maps to
  1:1.

Every other subsystem in this codebase currently defines its own local,
unrelated exceptions (for example ``ai_os_kernel/llm_gateway/errors.py``,
inheriting from plain ``Exception``). None of them migrate onto this
hierarchy as part of the Platform SDK build — that is Kernel-side work,
tracked separately (``docs/19_roadmap/feature_inventory.md`` module 44),
not a Platform SDK v1.0.0 step.
"""

from __future__ import annotations
