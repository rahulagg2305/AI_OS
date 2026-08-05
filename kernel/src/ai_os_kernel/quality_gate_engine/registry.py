"""Gate Registry (`P02-S06-M15-T05`) — the first real code this
package has ever had. Resolves a declared ``gateId`` to a real
:class:`GateDefinition`, per quality_gate_engine.md §4's first box and
this ticket's own Goal.

**Source of gate data: a pack's own real, schema-validated manifest —
no new catalog table.** ``platform_sdk/schemas/manifest.schema.json``
already declares a complete, JSON-Schema-validated top-level
``qualityGates[]`` array (``id``/``name``/``version``/``description``/
``entrypoint``/``type``/``severity``/``successCriteria``/
``timeoutSeconds``) — quality_gates_framework.md §4's own Gate Contract,
already real and enforced at manifest-load time, just never read by
any component until now. :class:`~ai_os_kernel.manifest_loader.models.
DiscoveredManifest` already keeps the full, already-validated raw
manifest dict (``.raw``) after schema validation — so this registry
needs no new persistence: :func:`derive_gate_definitions` mirrors
:mod:`ai_os_kernel.capability_manager.manifest_catalog_installer`'s own
``derive_agent_rows``/``derive_tool_rows`` shape (pure derivation from
an already-parsed manifest dict) rather than adding a
``catalog.quality_gates`` table, which would be a real, undecided
schema-authority fork this ticket's own Goal does not ask it to open.

**Gate ids are resolved raw, never derived with a ``pack_id/`` prefix
the way ``derive_agent_rows`` prefixes agent ids.** Confirmed by direct
inspection of the one real reference that exists today:
``capability_packs/software-engineering/workflows/delivery_pipeline.yaml``'s
own top-level ``qualityGates: [se.build_lint_clean, se.build_tests_pass]``
list already names gate ids in this exact, un-prefixed, dot-namespaced
shape (matching workflow-definition ids like ``se.delivery_pipeline``,
not the ``pack_id/agent_id`` shape agent/tool ids use) — so a manifest's
own future ``qualityGates[].id`` entries must resolve to that same raw
string for the reference to ever work. A real collision across two
packs is therefore a genuine ambiguity (:class:`DuplicateGateIdError`),
not resolved by picking a winner.

**No real gate content exists in the one real pack yet — proven here
against real, schema-conformant test fixtures, not fabricated data,
the identical "build the real component before anything wires it in"
precedent already established for ``KnowledgeResolver``/`MemoryResolver`
(``P02-S03-M08-T05``/``T06``) before their own later production-wiring
tickets.** Wiring this registry against the real pack's own manifest
(adding real ``qualityGates:`` entries, resolving them into
``se.delivery_pipeline``'s real quality-gate steps) is
``P02-S06-M15-T06``'s own, separate Goal — not this ticket's.

**Kernel-owned gates are deliberately out of scope.**
quality_gates_framework.md §10 documents two real owners ("Core /
platform-level gates are owned by the Kernel... Domain-specific gates
are owned by Capability Packs"), but no concrete Kernel-level gate is
named anywhere with real content to resolve — inventing one here would
be exactly the "no forced/empty work presented as real value"
violation this session's own standing discipline forbids. A disclosed
scope reduction, not a silent one.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict

from ai_os_kernel.quality_gate_engine.errors import DuplicateGateIdError, GateNotRegisteredError


class GateDefinition(BaseModel):
    """One real, manifest-declared quality gate — column-for-column per
    ``platform_sdk/schemas/manifest.schema.json``'s own ``qualityGates[]``
    entry shape. ``owner``/``failureAction`` from quality_gates_framework.md
    §4's own Gate Contract table are deliberately absent: the real,
    validated manifest schema does not declare either field yet — a
    real, disclosed doc-vs-schema gap, not silently resolved by
    inventing a value for either."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    version: str
    description: str
    entrypoint: str
    type: Literal["automated", "semi_automated", "manual"]
    severity: Literal["blocking", "warning"]
    success_criteria: str
    timeout_seconds: int | None
    pack_id: str


class GateRegistry(Protocol):
    """Resolves a declared ``gateId`` to a real :class:`GateDefinition`
    — the seam a future catalog-backed registry substitutes (ADR-0004:
    interface-driven, configuration over code), the identical shape
    :class:`~ai_os_kernel.workflow_engine.registry.AgentRegistry`
    already establishes."""

    async def resolve_gate(self, gate_id: str) -> GateDefinition: ...


class InMemoryGateRegistry:
    """The simplest implementation: a plain mapping handed in at
    construction — no pack discovery, no catalog. See
    :class:`~ai_os_kernel.workflow_engine.registry.InMemoryAgentRegistry`
    for the identical shape this mirrors."""

    def __init__(self, gates: Mapping[str, GateDefinition]) -> None:
        self._gates = dict(gates)

    async def resolve_gate(self, gate_id: str) -> GateDefinition:
        try:
            return self._gates[gate_id]
        except KeyError:
            raise GateNotRegisteredError(f"no gate registered for gateId={gate_id!r}") from None


def derive_gate_definitions(manifest: dict[str, Any], *, pack_id: str) -> list[GateDefinition]:
    """One :class:`GateDefinition` per ``manifest["qualityGates"]`` entry
    — the identical pure-derivation shape
    :func:`~ai_os_kernel.capability_manager.manifest_catalog_installer.derive_agent_rows`
    already establishes for agents, applied here to real, already
    schema-validated gate data instead. ``type`` defaults to
    ``"automated"`` when absent, matching the manifest schema's own
    declared default for this field."""
    return [
        GateDefinition(
            id=gate["id"],
            name=gate["name"],
            version=gate["version"],
            description=gate["description"],
            entrypoint=gate["entrypoint"],
            type=gate.get("type", "automated"),
            severity=gate["severity"],
            success_criteria=gate["successCriteria"],
            timeout_seconds=gate.get("timeoutSeconds"),
            pack_id=pack_id,
        )
        for gate in manifest.get("qualityGates", [])
    ]


def build_gate_registry(
    manifests: Sequence[tuple[dict[str, Any], str]],
) -> InMemoryGateRegistry:
    """Builds one real registry from every real, discovered pack's own
    manifest — ``(manifest_dict, pack_id)`` pairs, the identical shape
    a caller iterating a real
    :class:`~ai_os_kernel.manifest_loader.models.ManifestScanReport`'s
    own ``discovered`` list already has on hand
    (``(discovered.raw, discovered.metadata.id)``). Raises
    :class:`DuplicateGateIdError` the moment two real definitions claim
    the same raw ``id`` — see this module's own docstring for why gate
    ids are never pack-namespaced the way agent/tool ids are."""
    gates: dict[str, GateDefinition] = {}
    for manifest, pack_id in manifests:
        for definition in derive_gate_definitions(manifest, pack_id=pack_id):
            if definition.id in gates:
                raise DuplicateGateIdError(
                    f"gateId={definition.id!r} is declared by both "
                    f"{gates[definition.id].pack_id!r} and {pack_id!r}"
                )
            gates[definition.id] = definition
    return InMemoryGateRegistry(gates)
