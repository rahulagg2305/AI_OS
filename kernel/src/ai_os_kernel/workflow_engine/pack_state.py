"""The canonical Capability Pack lifecycle
(``docs/03_architecture/kernel/capability_manager.md`` §4 — "the single
authority" — mirrored by ``catalog.packs.state``'s own ``CHECK``
constraint in :mod:`ai_os_kernel.persistence.catalog_schema`).

Lives here, not in :mod:`ai_os_kernel.persistence.catalog_schema`,
mirroring exactly where :class:`~ai_os_kernel.workflow_engine.tool.
TrustTier` lives relative to ``catalog.tools.trust_tier``'s own
``CHECK`` constraint: the persistence layer never imports from
``workflow_engine`` (that dependency runs the other way), so it
duplicates the canonical values as literal strings in its own ``CHECK``
constraint rather than importing this enum, and a migration stays a
frozen historical record of what it enforced *at that time* regardless
of whether this enum's own membership ever changes later.
"""

from enum import StrEnum


class PackState(StrEnum):
    """One state in the canonical Capability Pack lifecycle. Only
    ``ACTIVATED`` is meaningful to
    :class:`~ai_os_kernel.workflow_engine.registry.SqlAgentRegistry`/
    :class:`~ai_os_kernel.workflow_engine.registry.SqlToolRegistry`
    today — the other seven exist here only so this enum is a complete,
    honest mirror of the documented lifecycle, not a partial one
    reverse-engineered from this step's own narrow need.
    """

    DISCOVERED = "discovered"
    VALIDATED = "validated"
    INSTALLED = "installed"
    CONFIGURED = "configured"
    ACTIVATED = "activated"
    DEACTIVATED = "deactivated"
    FAILED = "failed"
    UNINSTALLED = "uninstalled"
