"""Step 3 of ``platform_sdk_v1_scope.md``: the ``Agent`` and ``Tool``
Protocols (``platform_sdk.md`` §4.2/§4.3, at their narrowed v1.0.0
shapes).

**Deliberately imports nothing from ``ai_os_kernel`` or any pack.**
``platform_sdk.md`` §2 rule 1 makes this SDK the dependency floor, and
that discipline is worth holding in its own test suite too, not only in
its source. The proof that *real, existing* Kernel and pack classes
satisfy these Protocols is inherently a cross-boundary claim, so it lives
in the root suite that already spans both:
``tests/unit/platform_sdk/test_kernel_satisfies_sdk_contracts.py``.

What this file covers instead: the Protocols' own semantics, and the
exact limits of what their ``isinstance`` check proves.
"""

from typing import Any

from ai_os_sdk.contracts import Agent, Tool, TrustTier


class _MinimalAgent:
    """Exactly the two members ``Agent`` requires, nothing more."""

    output_schema: dict[str, Any] = {"type": "object"}

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"echoed": inputs}


class _MinimalTool:
    """Exactly the three members ``Tool`` requires, nothing more."""

    trust_tier: TrustTier = TrustTier.TIER2_TRUSTED
    output_schema: dict[str, Any] = {"type": "object"}

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return {"echoed": inputs}


class TestTrustTier:
    def test_defines_exactly_the_two_schema_enum_values(self) -> None:
        """The authoritative source is manifest.schema.json's own
        tools[].trustTier enum, which both this and the Kernel's
        equivalent independently mirror."""
        assert {t.value for t in TrustTier} == {"tier1_sandboxed", "tier2_trusted"}

    def test_members_are_real_strings_carrying_their_wire_values(self) -> None:
        """A ``StrEnum``, so a tier round-trips through JSON/YAML and
        through the manifest schema without a conversion step.

        Asserted via ``.value`` and ``isinstance`` rather than
        ``member == "tier1_sandboxed"``: the direct comparison is true at
        runtime but ``mypy --strict`` rejects it as a non-overlapping
        equality check, and it *is* the less precise claim — what
        actually has to agree with the schema is the wire value.
        """
        for member, wire_value in (
            (TrustTier.TIER1_SANDBOXED, "tier1_sandboxed"),
            (TrustTier.TIER2_TRUSTED, "tier2_trusted"),
        ):
            assert isinstance(member, str)
            assert member.value == wire_value
            assert str(member) == wire_value


class TestAgentProtocol:
    def test_a_conforming_object_satisfies_it(self) -> None:
        assert isinstance(_MinimalAgent(), Agent)

    def test_an_object_missing_output_schema_does_not(self) -> None:
        """The specific attribute whose absence would make an
        AgentRequest-shaped agent unloadable — see §4.2's decision block,
        which records that this, not the execute signature, is the real
        coupling."""

        class NoSchema:
            async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
                return {}

        assert not isinstance(NoSchema(), Agent)

    def test_an_object_missing_execute_does_not(self) -> None:
        class NoExecute:
            output_schema: dict[str, Any] = {}

        assert not isinstance(NoExecute(), Agent)

    def test_isinstance_proves_presence_only_never_signatures(self) -> None:
        """The load-bearing limitation, asserted rather than assumed.

        This object's ``execute`` takes the wrong arguments entirely and
        its ``output_schema`` is not even a mapping, yet it passes — a
        runtime_checkable Protocol checks member presence and nothing
        else. Recorded in §4.2's decision block as a precision correction
        to the architecture review, and asserted here so a future reader
        cannot mistake the check for contract certification.
        """

        class WrongShapeEntirely:
            output_schema = "not a mapping at all"

            def execute(self) -> None:  # not async, takes no inputs
                return None

        assert isinstance(WrongShapeEntirely(), Agent)


class TestToolProtocol:
    def test_a_conforming_object_satisfies_it(self) -> None:
        assert isinstance(_MinimalTool(), Tool)

    def test_an_object_missing_trust_tier_does_not(self) -> None:
        """trust_tier is what distinguishes Tool from Agent structurally
        — an Agent-shaped object must not pass as a Tool, or ADR-0016's
        sandbox guard could be bypassed by a mis-registered entrypoint."""
        assert not isinstance(_MinimalAgent(), Tool)

    def test_a_tool_shaped_object_also_satisfies_agent(self) -> None:
        """Not a defect: Tool's members are a superset of Agent's, so
        structural typing makes this unavoidable. Recorded because it
        means "is this an Agent?" alone is never sufficient to reject a
        Tool — a registry must check the tier it expects, which is
        exactly what the Kernel's own tool registry already does."""
        assert isinstance(_MinimalTool(), Agent)
