"""ADR-0023's monotonic narrowing rule — "the core of the decision":

    principal permissions
      ∩ workflow declared permissions
      ∩ agent declared permissions (manifest)
      ∩ tool declared permissions (manifest)
      = effective permissions for this tool invocation

**Closes the gap :mod:`ai_os_kernel.security_manager.models` has long
disclosed**: that module's own docstring states this chain "needs
manifest-declared permissions on workflows/agents/tools, which is
Capability Manager territory not yet built. This models only the first
term of that intersection." That data-source gap is still real — no
code anywhere yet parses a workflow's/agent's/tool's declared
``permissions`` out of a manifest into a runtime value (
:class:`~ai_os_kernel.manifest_loader.models.DiscoveredManifest` keeps
everything past ``metadata`` in an untyped ``raw`` dict). This module
does not invent that data source. It builds the other missing piece:
**the narrowing computation itself**, real and tested, so that the day
workflow/agent/tool declared permissions do become available at
invocation (Capability Manager work, not this module's), computing and
enforcing the effective set is a call to an already-correct function,
not new logic written under time pressure.

Authority only ever shrinks: a set intersection can never contain a
permission absent from any one of its operands, so a workflow, agent, or
tool declaring a permission the principal never had can never grant it
(ADR-0023: "There is no elevation path at runtime, and no LLM output can
widen the set").
"""

from __future__ import annotations

from ai_os_kernel.security_manager.models import SecurityContext


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
    return context.permissions & workflow_permissions & agent_permissions & tool_permissions


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
