"""Errors raised by the Capability Manager's pack lifecycle writer
(docs/03_architecture/kernel/capability_manager.md)."""


class CapabilityManagerError(Exception):
    """Base class for every Capability Manager error."""


class PackAlreadyRegisteredError(CapabilityManagerError):
    """:meth:`~ai_os_kernel.capability_manager.repository.PackLifecycleRepository.register`
    was called for a ``pack_id`` that already has a ``catalog.packs`` row.

    Registration is a one-time lifecycle event, not an idempotent
    upsert: re-registering a known pack (a new version, a repaired
    manifest, ...) is an *upgrade*, a distinct capability_manager.md §3
    responsibility ("Manage pack versions and upgrades") this step does
    not implement.
    """


class PackNotFoundError(CapabilityManagerError):
    """:meth:`~ai_os_kernel.capability_manager.repository.PackLifecycleRepository.activate`/
    :meth:`~ai_os_kernel.capability_manager.repository.PackLifecycleRepository.deactivate`
    was called for a ``pack_id`` with no ``catalog.packs`` row at all."""


class InvalidPackTransitionError(CapabilityManagerError):
    """:meth:`~ai_os_kernel.capability_manager.repository.PackLifecycleRepository.activate`/
    :meth:`~ai_os_kernel.capability_manager.repository.PackLifecycleRepository.deactivate`
    was called while the pack's current state does not allow that
    transition (capability_manager.md §4's canonical lifecycle)."""


class PackRegistrationError(CapabilityManagerError):
    """A database error occurred while writing to ``catalog.packs``/
    ``catalog.pack_state_transitions`` — never raised for a rejected
    transition or a missing pack, which get their own, more specific
    errors above."""


class InvalidPackUpgradeError(CapabilityManagerError):
    """:meth:`~ai_os_kernel.capability_manager.repository.PackLifecycleRepository.upgrade`
    was called with a ``version`` that is not strictly greater than the
    pack's current, real ``catalog.packs.version`` — a distinct failure
    mode from :class:`InvalidPackTransitionError` (which is about
    *lifecycle state*, not version ordering). Never silently proceeds:
    an upgrade that cannot prove real forward progress is refused before
    any row is touched, not accepted and left to quietly overwrite a
    pack with an equal or older version."""
