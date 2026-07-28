"""Capability Manager — Capability Pack lifecycle after loading.

Owns the canonical state machine: discovered -> validated -> installed
-> configured -> activated -> deactivated | failed -> uninstalled
(docs/03_architecture/kernel/capability_manager.md). Activation of a
pack that affects platform behaviour requires human approval (ADR-0007).

Implemented so far — the smallest useful slice this step approves:

- :class:`PackLifecycleRepository` (``Protocol``) /
  :class:`SqlPackLifecycleRepository` — register/install a pack record,
  activate it, deactivate it, and record every transition in
  ``catalog.pack_state_transitions``. See
  :mod:`ai_os_kernel.capability_manager.repository` for exactly which
  transitions are supported and why.
- :class:`PackRecord` — the ``catalog.packs`` row shape a writer
  returns (:mod:`ai_os_kernel.capability_manager.models`).

This makes pack activation real: :class:`~ai_os_kernel.workflow_engine.
registry.SqlAgentRegistry`/:class:`~ai_os_kernel.workflow_engine.
registry.SqlToolRegistry` already gated agent/tool resolution on
``catalog.packs.state`` being ``activated`` (a prior step), but nothing
in this codebase could get a pack into that state except a test
seeding a row directly with raw SQL. This module is that missing
writer — tests can now register and activate a pack the same way a
real caller eventually will.

Not yet implemented: pack discovery (the Manifest Loader validates a
manifest in memory; nothing here scans a filesystem or registers what
it finds), the ``configured``/``failed``/``uninstalled`` states, a
version-upgrade path, health monitoring, a permissions matrix, sandbox
enforcement, remote/marketplace installation, and any HTTP surface —
this is a pure Python write path only, with no
``POST /api/v1/packs/...`` route yet.
"""

from ai_os_kernel.capability_manager.errors import (
    CapabilityManagerError,
    InvalidPackTransitionError,
    PackAlreadyRegisteredError,
    PackNotFoundError,
    PackRegistrationError,
)
from ai_os_kernel.capability_manager.models import PackRecord
from ai_os_kernel.capability_manager.repository import (
    PackLifecycleRepository,
    SqlPackLifecycleRepository,
)

__all__ = [
    "CapabilityManagerError",
    "InvalidPackTransitionError",
    "PackAlreadyRegisteredError",
    "PackLifecycleRepository",
    "PackNotFoundError",
    "PackRecord",
    "PackRegistrationError",
    "SqlPackLifecycleRepository",
]
