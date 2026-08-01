"""Refuses to resolve an agent/tool whose own declared permissions
exceed its pack's manifest grant — ``P02-S05-M13-T08``, closing
``ai_os_kernel.security_manager.narrowing``'s own disclosed gap: "no
code anywhere yet parses a workflow's/agent's/tool's declared
``permissions`` out of a manifest into a runtime value." That is now
true for agents/tools specifically — ``catalog.agents.
required_permissions``/``catalog.tools.required_permissions`` are real,
manifest-sourced values (``manifest_catalog_installer.derive_agent_rows``/
``derive_tool_rows`` read them straight from each agent's/tool's own
``permissions`` entry), and ``catalog.packs.manifest`` holds the pack's
own real, full manifest (written by ``SqlPackLifecycleRepository.register``),
including its top-level ``permissions`` array — the pack's own grant.

**Reuses the real narrowing primitive, does not duplicate it.** An
entrypoint's declared permissions are within its pack's grant exactly
when intersecting them against the pack's own declared permissions
changes nothing — the identical set-intersection
:func:`~ai_os_kernel.security_manager.narrowing.
intersect_declared_permissions` already computes for the principal/
workflow/agent/tool invocation chain (ADR-0023). Whatever the
intersection is missing, relative to the entrypoint's own full declared
set, is the over-grant.
"""

from __future__ import annotations

from ai_os_kernel.security_manager.narrowing import intersect_declared_permissions


def over_granted_permissions(
    *, entrypoint_permissions: frozenset[str], pack_permissions: frozenset[str]
) -> frozenset[str]:
    """Which of ``entrypoint_permissions`` exceed ``pack_permissions`` —
    empty when the entrypoint declares nothing its own pack did not
    already grant at the manifest level. Never raises; the caller (a
    registry resolving a real row) decides what "over-granted" means for
    its own error type."""
    within_grant = intersect_declared_permissions(entrypoint_permissions, pack_permissions)
    return entrypoint_permissions - within_grant
