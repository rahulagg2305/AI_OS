"""Proof that the real Kernel's ``DefaultContextManager`` satisfies the
new SDK ``ContextService`` Protocol, and that the entry-point contract
(``PackContext``/``PackRegistration``/``HealthReport``/``CapabilityPack``)
now genuinely lives in ``ai_os_sdk``, with the Kernel's own module a real
re-export rather than a second, parallel definition
(``platform_sdk_v1_scope.md`` step 7).

**Why this file lives in the root suite, not ``platform_sdk/tests/``.**
Same reason as ``test_kernel_satisfies_sdk_contracts.py``: it imports
``ai_os_kernel`` *and* a pack *and* ``ai_os_sdk`` together, an inherently
cross-boundary assertion the SDK's own dependency-floor suite must not
carry (``platform_sdk.md`` §2 rule 1).

**Nothing in the Kernel or the pack is modified by this file.** It only
observes the real relocation this step performed.
"""

from __future__ import annotations

import pytest

from ai_os_kernel.capability_manager import pack_contract as kernel_pack_contract
from ai_os_kernel.context_manager.manager import DefaultContextManager
from ai_os_pack_software_engineering.agents.architecture import ArchitectureAgentEntrypoint
from ai_os_sdk.contracts import CapabilityPack as SdkCapabilityPack
from ai_os_sdk.contracts import ContextService as SdkContextService
from ai_os_sdk.contracts import HealthReport as SdkHealthReport
from ai_os_sdk.contracts import PackContext as SdkPackContext
from ai_os_sdk.contracts import PackRegistration as SdkPackRegistration
from ai_os_sdk.models import AssembledContext, ContextItem, SourceRef, SourceType


class TestRealContextManagerSatisfiesTheSdkContextServiceProtocol:
    def test_default_context_manager_is_an_sdk_context_service(self) -> None:
        """Zero resolvers, zero I/O -- the same 'shape only, no real
        assembly exercised' precedent already used for the empty
        DispatchingLLMGateway in test_kernel_satisfies_sdk_contracts.py."""
        assert isinstance(DefaultContextManager([]), SdkContextService)


class TestContextBoundaryModelsAreReal:
    def test_an_assembled_context_round_trips_with_real_field_values(self) -> None:
        """Proves the narrowed boundary models are genuinely usable
        Pydantic models, not merely declared -- built with real,
        meaningful values matching the reconciliation decision's own
        narrowed shape (no index_generation, no query/filters)."""
        item = ContextItem(
            content="the real workflow inputs",
            provenance=SourceRef(source_type=SourceType.WORKFLOW_STATE, identifier="wf_123"),
            relevance_score=1.0,
            token_count=5,
            trust="trusted",
        )
        assembled = AssembledContext(
            items=[item],
            total_tokens=5,
            sources_queried=[SourceType.WORKFLOW_STATE],
            items_excluded_count=0,
            assembly_id="asm_1",
        )

        assert assembled.items == [item]
        assert assembled.sources_queried == [SourceType.WORKFLOW_STATE]


class TestPackContractRelocatedNotRedefined:
    def test_the_kernel_module_reexports_the_real_sdk_classes(self) -> None:
        """Not a second, parallel definition -- the exact same class
        object, so isinstance checks anywhere in the codebase (including
        real pack source, unmodified by this step) still agree."""
        assert kernel_pack_contract.PackContext is SdkPackContext
        assert kernel_pack_contract.PackRegistration is SdkPackRegistration
        assert kernel_pack_contract.HealthReport is SdkHealthReport
        assert kernel_pack_contract.CapabilityPack is SdkCapabilityPack

    def test_a_real_pack_agent_still_populates_the_relocated_pack_registration(self) -> None:
        """PackRegistration.agents is now typed against the SDK's own
        Agent Protocol, not the Kernel's internal one -- this proves a
        real pack agent still satisfies it after the relocation, the
        same real substitution `test_pack.py`'s own `activate()` call
        already exercises end to end."""
        registration = SdkPackRegistration(agents={"architecture": ArchitectureAgentEntrypoint()})
        assert "architecture" in registration.agents

    def test_capability_pack_is_deliberately_not_runtime_checkable(self) -> None:
        """Unchanged from the Kernel's own prior decision: nothing in
        this codebase yet loads and isinstance-checks an entryPoint at
        runtime, so there is no real caller to justify one."""
        with pytest.raises(TypeError):
            isinstance(object(), SdkCapabilityPack)  # type: ignore[misc]
