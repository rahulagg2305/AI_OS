"""ADR-0023's monotonic narrowing rule — "the core of the decision":

    principal permissions
      ∩ workflow declared permissions
      ∩ agent declared permissions (manifest)
      ∩ tool declared permissions (manifest)
      = effective permissions for this tool invocation

**Closed part of the gap :mod:`ai_os_kernel.security_manager.models` has
long disclosed**: that module's own docstring states this chain "needs
manifest-declared permissions on workflows/agents/tools, which is
Capability Manager territory not yet built. This models only the first
term of that intersection." ``P02-S05-M13-T08`` closed the agent/tool
half of that data-source gap — ``catalog.agents.required_permissions``/
``catalog.tools.required_permissions`` are real, manifest-sourced values
the Capability Manager now checks at resolution time (see
:mod:`ai_os_kernel.capability_manager.permission_grant`, which reuses
:func:`intersect_declared_permissions` below rather than a bespoke
subset check). **Updated (``P03-S05-M14-T09``): the principal term is
now real too, applied at that identical resolution point** —
:func:`over_permitted_permissions` (below) is the reusable primitive;
see :mod:`ai_os_kernel.workflow_engine.registry`'s own docstring for how
a triggering principal's real, persisted permission set (captured once
at workflow-trigger time, since resolution can happen much later — a
worker-loop tick has no live bearer token to re-derive it from) reaches
that check. **Updated (``P03-S05-M14-T10``): the workflow term is now
real too**, reusing the identical :func:`over_permitted_permissions`
primitive rather than a third, parallel subset check —
``catalog.workflow_definitions.declared_permissions`` is now real,
manifest-sourced data (:func:`~ai_os_kernel.capability_manager.
manifest_catalog_installer.derive_workflow_definition_rows`), read at
resolution time via :meth:`~ai_os_kernel.workflow_engine.
definition_catalog.WorkflowDefinitionCatalog.get_declared_permissions`
(no snapshot needed — unlike the principal term, a workflow's declared
permissions are pinned to an immutable ``(definition_id, version)`` a
``WorkflowInstance`` already stores, not an ephemeral bearer token). The
agent/tool term of the four-way chain (``narrow_permissions``'s own
remaining two arguments) is still bound to the pack-grant/principal/
workflow terms checked at *resolution*, not (yet) to a genuine
per-invocation call of ``narrow_permissions`` itself.

Authority only ever shrinks: a set intersection can never contain a
permission absent from any one of its operands, so a workflow, agent, or
tool declaring a permission the principal never had can never grant it
(ADR-0023: "There is no elevation path at runtime, and no LLM output can
widen the set").
"""

from __future__ import annotations

from ai_os_kernel.security_manager.models import SecurityContext


def intersect_declared_permissions(*permission_sets: frozenset[str]) -> frozenset[str]:
    """The general n-way permission intersection ADR-0023's formula is
    one instance of. Reused wherever a broader-scope grant must bound a
    narrower-scope declaration — the principal/workflow/agent/tool
    invocation chain (:func:`narrow_permissions`) is one such case; a
    pack's own manifest grant bounding one of its agent's/tool's
    declared permissions (:mod:`ai_os_kernel.capability_manager.
    permission_grant`) is another. An empty ``permission_sets`` returns
    an empty set — there is nothing to intersect, not "everything."
    """
    if not permission_sets:
        return frozenset()
    result = permission_sets[0]
    for permissions in permission_sets[1:]:
        result = result & permissions
    return result


def narrow_permissions(
    context: SecurityContext,
    *,
    workflow_permissions: frozenset[str],
    agent_permissions: frozenset[str],
    tool_permissions: frozenset[str],
) -> frozenset[str]:
    """The effective permission set for one real tool invocation —
    ADR-0023's four-way intersection, computed exactly as documented.

    ``context.permissions`` carries the principal term (already real,
    role-derived, per :func:`~ai_os_kernel.security_manager.permissions.
    permissions_for_roles`); the other three are whatever a caller
    supplies as this invocation's workflow/agent/tool declared
    permissions — real manifest data once a caller has it, or a smaller,
    explicit set in the meantime.
    """
    return intersect_declared_permissions(
        context.permissions, workflow_permissions, agent_permissions, tool_permissions
    )


def is_permitted(
    context: SecurityContext,
    permission: str,
    *,
    workflow_permissions: frozenset[str],
    agent_permissions: frozenset[str],
    tool_permissions: frozenset[str],
) -> bool:
    """Whether ``permission`` survives the full narrowing chain — the
    real, per-invocation question FR-018 asks: "can this tool exercise
    this permission, given everything above it in the chain." A thin,
    named convenience over :func:`narrow_permissions` for a caller that
    only cares about one permission, not the whole effective set."""
    return permission in narrow_permissions(
        context,
        workflow_permissions=workflow_permissions,
        agent_permissions=agent_permissions,
        tool_permissions=tool_permissions,
    )


def over_permitted_permissions(
    *, entrypoint_permissions: frozenset[str], bounding_permissions: frozenset[str]
) -> frozenset[str]:
    """Which of ``entrypoint_permissions`` exceed what ``bounding_permissions``
    actually holds — empty when an entrypoint's own declared permissions
    are entirely within reach of ``bounding_permissions``. Originally
    built (``P03-S05-M14-T09``) for the principal term of ADR-0023's
    monotonic-narrowing chain, closing this module's own long-disclosed
    gap: "``SecurityContext`` is never threaded into resolution at all".
    **Generalized (``P03-S05-M14-T10``) to also serve the workflow
    term** — ``bounding_permissions`` is deliberately not named
    ``principal_permissions`` any more, since :mod:`ai_os_kernel.
    workflow_engine.registry`'s ``_refuse_if_over_granted`` now calls
    this same function once per single-set bounding term (principal,
    then workflow), rather than growing a second, parallel subset check
    for the new term. Applied at agent/tool *resolution*
    (:mod:`ai_os_kernel.workflow_engine.registry`) rather than only at
    :func:`narrow_permissions`'s own per-invocation call — the identical
    "refuse before loading, not a confusing failure the first time
    something calls ``.execute()``" shape
    :func:`~ai_os_kernel.capability_manager.permission_grant.
    over_granted_permissions` already establishes for the pack-grant
    term, reusing the exact same :func:`intersect_declared_permissions`
    primitive rather than a second, parallel subset check. Never raises;
    the caller (a registry resolving a real row) decides what
    "over-permitted" means for its own error type."""
    within_reach = intersect_declared_permissions(entrypoint_permissions, bounding_permissions)
    return entrypoint_permissions - within_reach
