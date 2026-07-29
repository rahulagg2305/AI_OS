"""``SoftwareEngineeringPack`` — the manifest's own top-level
``entryPoint``, required the moment ``agents`` (or ``workflows``) gains
an entry (``platform_sdk/schemas/manifest.schema.json``'s own ``allOf``
rule; ``capability_packs/_template/manifest.yaml`` already documents
this precisely).

**Migrated onto the real Platform SDK (``platform_sdk_v1_scope.md``
step 14) — the sixth and final module in this pack to depend on
``ai_os_kernel``, and the one that closes it out entirely.** Implements
:class:`~ai_os_sdk.contracts.CapabilityPack` directly, importing
``PackContext``/``PackRegistration``/``HealthReport`` from
``ai_os_sdk.contracts`` rather than the Kernel's own compatibility
re-export (``ai_os_kernel.capability_manager.pack_contract``). This is
a genuinely zero-behavior-change swap, not a redesign: step 7 already
relocated these four types into the SDK, additively, and made the
Kernel's own module a real re-export of the identical objects (proven
by identity, not just import success, in step 7's own record) — every
real pack agent already returned by :meth:`activate` (``qa-test``,
``requirements-analyst``, ``architecture``, ``build``, ``documentation``)
has been a real :class:`~ai_os_sdk.contracts.Agent` since step 3, so
``PackRegistration.agents``'s own SDK-typed dict field accepts them
unchanged.

**Zero `ai_os_kernel` imports remain anywhere in this pack's own source
tree.** `pack_contract_suite` check 7 (``ai_os_sdk.testing.forbidden_imports``)
now genuinely passes against this entire pack with no waiver at all —
``pack_contract_waiver.yaml`` is deleted outright, not merely emptied,
per its own documented expiry condition. See that check's own module
docstring and ``platform_sdk_v1_scope.md`` §6r for the full record.

See ``ai_os_sdk.contracts.capability_pack``'s own module docstring for
why nothing in this codebase actually calls :meth:`activate` yet — this
class remains a real, correct implementation of that reduced contract
regardless, not a stub that lies about what it does.
"""

from __future__ import annotations

from ai_os_pack_software_engineering.agents.architecture import ArchitectureAgentEntrypoint
from ai_os_sdk.contracts import HealthReport, PackContext, PackRegistration

_PACK_ID = "software-engineering"
_PACK_VERSION = "0.1.0"


class SoftwareEngineeringPack:
    """This pack's ``CapabilityPack`` entry point. See this module's
    own docstring for what ``activate``/``deactivate``/``health`` do
    and do not connect to yet."""

    pack_id: str = _PACK_ID
    version: str = _PACK_VERSION

    async def activate(self, context: PackContext) -> PackRegistration:
        return PackRegistration(agents={"architecture": ArchitectureAgentEntrypoint()})

    async def deactivate(self) -> None:
        return None

    async def health(self) -> HealthReport:
        return HealthReport(status="healthy")
