"""Unit tests for the Gate Registry (`P02-S06-M15-T05`) — pure logic,
no I/O, real schema-conformant manifest fixtures (matching
``platform_sdk/schemas/manifest.schema.json``'s own ``qualityGates[]``
shape exactly), not fabricated data."""

from __future__ import annotations

import pytest

from ai_os_kernel.quality_gate_engine.errors import DuplicateGateIdError, GateNotRegisteredError
from ai_os_kernel.quality_gate_engine.registry import (
    GateDefinition,
    InMemoryGateRegistry,
    build_gate_registry,
    derive_gate_definitions,
)

_LINT_GATE = {
    "id": "se.build_lint_clean",
    "name": "Build Lint Clean",
    "version": "1.0.0",
    "description": "Static analysis passes with zero findings.",
    "entrypoint": "ai_os_pack_software_engineering.gates:LintCleanGate",
    "severity": "blocking",
    "successCriteria": "lint exits zero",
    "timeoutSeconds": 300,
}

_TESTS_GATE = {
    "id": "se.build_tests_pass",
    "name": "Build Tests Pass",
    "version": "1.0.0",
    "description": "All unit tests pass with zero failures.",
    "entrypoint": "ai_os_pack_software_engineering.gates:TestsPassGate",
    "severity": "blocking",
    "successCriteria": "test suite exits zero",
}


def test_derive_gate_definitions_reads_every_real_field() -> None:
    manifest = {"qualityGates": [_LINT_GATE]}

    definitions = derive_gate_definitions(manifest, pack_id="software-engineering")

    assert len(definitions) == 1
    definition = definitions[0]
    assert definition.id == "se.build_lint_clean"
    assert definition.name == "Build Lint Clean"
    assert definition.version == "1.0.0"
    assert definition.entrypoint == "ai_os_pack_software_engineering.gates:LintCleanGate"
    assert definition.severity == "blocking"
    assert definition.success_criteria == "lint exits zero"
    assert definition.timeout_seconds == 300
    assert definition.pack_id == "software-engineering"


def test_type_defaults_to_automated_when_absent() -> None:
    manifest = {"qualityGates": [_TESTS_GATE]}

    definitions = derive_gate_definitions(manifest, pack_id="software-engineering")

    assert definitions[0].type == "automated"


def test_timeout_seconds_is_none_when_absent() -> None:
    manifest = {"qualityGates": [_TESTS_GATE]}

    definitions = derive_gate_definitions(manifest, pack_id="software-engineering")

    assert definitions[0].timeout_seconds is None


def test_a_manifest_declaring_no_gates_derives_nothing() -> None:
    assert derive_gate_definitions({}, pack_id="software-engineering") == []
    assert derive_gate_definitions({"qualityGates": []}, pack_id="software-engineering") == []


@pytest.mark.asyncio
async def test_resolve_gate_returns_the_real_definition() -> None:
    definition = GateDefinition(
        id="se.build_lint_clean",
        name="Build Lint Clean",
        version="1.0.0",
        description="Static analysis passes with zero findings.",
        entrypoint="ai_os_pack_software_engineering.gates:LintCleanGate",
        type="automated",
        severity="blocking",
        success_criteria="lint exits zero",
        timeout_seconds=300,
        pack_id="software-engineering",
    )
    registry = InMemoryGateRegistry({"se.build_lint_clean": definition})

    resolved = await registry.resolve_gate("se.build_lint_clean")

    assert resolved == definition


@pytest.mark.asyncio
async def test_resolve_an_unregistered_gate_raises() -> None:
    registry = InMemoryGateRegistry({})

    with pytest.raises(GateNotRegisteredError, match="se.does-not-exist"):
        await registry.resolve_gate("se.does-not-exist")


@pytest.mark.asyncio
async def test_build_gate_registry_resolves_gates_from_multiple_real_manifests() -> None:
    manifest_one = {"qualityGates": [_LINT_GATE]}
    manifest_two = {"qualityGates": [_TESTS_GATE]}

    registry = build_gate_registry(
        [(manifest_one, "software-engineering"), (manifest_two, "another-pack")]
    )

    lint_gate = await registry.resolve_gate("se.build_lint_clean")
    tests_gate = await registry.resolve_gate("se.build_tests_pass")
    assert lint_gate.pack_id == "software-engineering"
    assert tests_gate.pack_id == "another-pack"


def test_duplicate_gate_id_across_packs_is_refused() -> None:
    manifest_one = {"qualityGates": [_LINT_GATE]}
    manifest_two = {"qualityGates": [_LINT_GATE]}

    with pytest.raises(DuplicateGateIdError, match="se.build_lint_clean"):
        build_gate_registry(
            [(manifest_one, "software-engineering"), (manifest_two, "another-pack")]
        )
