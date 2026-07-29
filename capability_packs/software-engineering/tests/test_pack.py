"""Deterministic tests for this pack's own entry points — no database,
no live LLM call (ADR-0004: a fake/deterministic Protocol implementation
is a legitimate substitute; the same shape this Kernel's own test suite
uses throughout).

The end-to-end proof that this pack is genuinely registered, activated,
and resolved through the real ``SqlAgentRegistry`` and dispatches a
real (or, for CI, Echo-backed) command through the real
``AgentStepExecutor`` lives under the Kernel's own
``tests/integration/workflow_engine/test_architecture_agent_pack.py`` —
this file only proves this pack's own code in isolation.

The Architecture Agent's own entrypoint-level tests (zero-arg
construction, dispatch, error handling) moved to
``test_architecture_agent.py`` in step 11, once that agent was migrated
onto the Platform SDK and stopped taking a ``service_factory``
constructor override — the identical split ``test_requirements_analyst.py``
already made from this file's own prior shape.
"""

from __future__ import annotations

import pytest

from ai_os_kernel.capability_manager.pack_contract import PackContext
from ai_os_pack_software_engineering.agents.architecture import ArchitectureAgentEntrypoint
from ai_os_pack_software_engineering.pack import SoftwareEngineeringPack


@pytest.mark.asyncio
async def test_activate_registers_the_architecture_agent() -> None:
    pack = SoftwareEngineeringPack()

    registration = await pack.activate(PackContext(pack_id=pack.pack_id, pack_version=pack.version))

    assert set(registration.agents) == {"architecture"}
    assert isinstance(registration.agents["architecture"], ArchitectureAgentEntrypoint)


@pytest.mark.asyncio
async def test_deactivate_and_health_are_real_and_honest() -> None:
    pack = SoftwareEngineeringPack()

    await pack.deactivate()
    report = await pack.health()

    assert report.status == "healthy"
