"""``SoftwareEngineeringPack`` — the manifest's own top-level
``entryPoint``, required the moment ``agents`` (or ``workflows``) gains
an entry (``platform_sdk/schemas/manifest.schema.json``'s own ``allOf``
rule; ``capability_packs/_template/manifest.yaml`` already documents
this precisely).

Implements :class:`~ai_os_kernel.capability_manager.pack_contract.CapabilityPack`
— see that module's own docstring for why it is a deliberately reduced
slice of platform_sdk.md §6/§7, and why nothing in this codebase
actually calls :meth:`activate` yet. This class is a real, correct
implementation of that reduced contract regardless — not a stub that
lies about what it does — so it is ready the moment a real pack
installer exists to call it.
"""

from __future__ import annotations

from ai_os_kernel.capability_manager.pack_contract import (
    HealthReport,
    PackContext,
    PackRegistration,
)
from ai_os_pack_software_engineering.agents.architecture import ArchitectureAgentEntrypoint

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
