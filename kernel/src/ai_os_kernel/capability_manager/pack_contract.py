"""Compatibility re-export — the real ``CapabilityPack`` entry-point
contract now lives in :mod:`ai_os_sdk.contracts.capability_pack`
(``platform_sdk_v1_scope.md`` step 7).

**Relocated, not redefined.** ``PackContext``/``PackRegistration``/
``HealthReport``/``CapabilityPack`` used to be defined here; step 7
moved their real definitions into the SDK — their real, final home per
``platform_sdk.md`` §6/§7 — additively, exactly as this module's own
docstring already promised before step 7 touched it (three service
attributes added in step 6b; no shape change since). This module now
only re-exports the same classes, so every existing import of
``ai_os_kernel.capability_manager.pack_contract`` — including real pack
source (``ai_os_pack_software_engineering.pack``) — keeps working
completely unchanged.

**Why real pack source still imports the Kernel path, not
``ai_os_sdk`` directly, even though the real definitions have moved.**
Migrating that one import statement onto ``ai_os_sdk.contracts.
capability_pack`` directly is step 14's own explicitly scoped job
(``platform_sdk_v1_scope.md``'s step table: "Migrate ``pack.py``'s entry
point onto the real SDK types"), not this step's. This shim is what
makes that safe to defer: nothing about the pack's own behavior or
import graph needs to change today for step 7's relocation to be real.

**Nothing in this codebase calls ``CapabilityPack.activate()`` yet —
a real, discovered gap, not simulated here.**
:class:`~ai_os_kernel.capability_manager.repository.SqlPackLifecycleRepository`
only ever flips ``catalog.packs.state`` and records a transition; it
does not parse a manifest's ``agents``/``tools``/``workflows`` arrays
into ``catalog.agents``/``catalog.tools`` rows, and nothing calls a
pack's own ``entryPoint`` class at all. That automated "Manifest Loader
discovers a pack -> writes catalog rows -> calls
``CapabilityPack.activate(context)``" pipeline is a distinct, larger,
future Capability Manager increment (a real pack installer). Until it
exists, ``catalog.agents``/``catalog.tools`` rows are written directly
by whatever process needs them real today (a test, or eventually that
installer) — the identical situation already true for every other
catalog table's own writer-less history in this project.
"""

from __future__ import annotations

from ai_os_sdk.contracts.capability_pack import (
    CapabilityPack,
    HealthReport,
    PackContext,
    PackRegistration,
)

__all__ = [
    "CapabilityPack",
    "HealthReport",
    "PackContext",
    "PackRegistration",
]
