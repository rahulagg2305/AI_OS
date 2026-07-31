"""Unit tests for layer 6 (feature flags / experiment overrides,
``P01-S02-M01-T07``). The real proof this Task requires: layer 6 sits
above every other layer already built — pack defaults (2) and runtime
overrides (5) — and its overrides are genuinely isolated per run, never
merged into a shared, process-wide object."""

import asyncio
from typing import Any

from ai_os_kernel.configuration_manager.feature_flags import (
    ExperimentOverrideStore,
    extract_feature_flag_defaults,
    resolve_feature_flag,
)
from ai_os_kernel.configuration_manager.runtime_overrides import RuntimeOverrideStore


class _FakeConfigChangeWriter:
    """The same fake used in test_runtime_overrides.py — the one real
    seam RuntimeOverrideStore.apply depends on, satisfied structurally."""

    async def record(
        self,
        *,
        config_key: str,
        old_value: Any,
        new_value: Any,
        changed_by: str,
        reason: str,
    ) -> None:
        pass


def _pack_manifest(*, flags: list[dict[str, Any]]) -> dict[str, Any]:
    return {"metadata": {"id": "some-pack"}, "featureFlags": flags}


def test_extract_feature_flag_defaults_reads_the_manifest_array() -> None:
    manifest = _pack_manifest(flags=[{"name": "new_ui", "default": True, "description": "New UI"}])

    assert extract_feature_flag_defaults(manifest) == {"new_ui": True}


def test_extract_feature_flag_defaults_is_empty_with_no_feature_flags_array() -> None:
    assert extract_feature_flag_defaults({"metadata": {"id": "some-pack"}}) == {}


def test_extract_feature_flag_defaults_ignores_a_malformed_entry() -> None:
    manifest = _pack_manifest(flags=[{"name": "no_default_here"}])

    assert extract_feature_flag_defaults(manifest) == {}


def test_the_caller_default_applies_when_nothing_declares_the_flag() -> None:
    store = ExperimentOverrideStore()

    value = resolve_feature_flag(
        "unknown_flag", run_id=None, experiment_overrides=store, default=True
    )

    assert value is True


def test_a_pack_default_applies_when_nothing_overrides_it() -> None:
    store = ExperimentOverrideStore()
    pack = _pack_manifest(flags=[{"name": "new_ui", "default": True}])

    value = resolve_feature_flag(
        "new_ui", run_id=None, experiment_overrides=store, pack_manifests=[pack], default=False
    )

    assert value is True


def test_a_later_pack_overrides_an_earlier_packs_default() -> None:
    store = ExperimentOverrideStore()
    first_pack = _pack_manifest(flags=[{"name": "new_ui", "default": True}])
    second_pack = _pack_manifest(flags=[{"name": "new_ui", "default": False}])

    value = resolve_feature_flag(
        "new_ui",
        run_id=None,
        experiment_overrides=store,
        pack_manifests=[first_pack, second_pack],
    )

    assert value is False


def test_a_runtime_override_wins_over_a_pack_default() -> None:
    """Layer 5 outranks layer 2, exactly as it does for every other
    config key (P01-S02-M01-T04)."""
    store = ExperimentOverrideStore()
    runtime_store = RuntimeOverrideStore()
    asyncio.run(
        runtime_store.apply(
            _FakeConfigChangeWriter(),
            config_key="new_ui",
            new_value=False,
            changed_by="oncall-1",
            reason="disable during incident",
        )
    )
    pack = _pack_manifest(flags=[{"name": "new_ui", "default": True}])

    value = resolve_feature_flag(
        "new_ui",
        run_id=None,
        experiment_overrides=store,
        runtime_overrides=runtime_store,
        pack_manifests=[pack],
    )

    assert value is False


def test_an_experiment_override_wins_over_a_runtime_override() -> None:
    """The real, documented property (configuration_manager.md §4,
    ADR-0022): "Experiment overrides (6) beat runtime overrides (5)" —
    an active experiment's pinned condition survives an operator's
    live, global change."""
    store = ExperimentOverrideStore()
    store.set_override("run-1", "new_ui", True)
    runtime_store = RuntimeOverrideStore()
    asyncio.run(
        runtime_store.apply(
            _FakeConfigChangeWriter(),
            config_key="new_ui",
            new_value=False,
            changed_by="oncall-1",
            reason="operator disabled it globally mid-experiment",
        )
    )

    value = resolve_feature_flag(
        "new_ui", run_id="run-1", experiment_overrides=store, runtime_overrides=runtime_store
    )

    assert value is True


def test_an_experiment_override_wins_over_everything_at_once() -> None:
    """The full chain in one call: experiment (6) > runtime (5) > pack
    (2) > caller default (1) — the same "wins over every lower layer"
    proof shape T04's own test used."""
    store = ExperimentOverrideStore()
    store.set_override("run-1", "new_ui", True)
    runtime_store = RuntimeOverrideStore()
    asyncio.run(
        runtime_store.apply(
            _FakeConfigChangeWriter(),
            config_key="new_ui",
            new_value=False,
            changed_by="u",
            reason="r",
        )
    )
    pack = _pack_manifest(flags=[{"name": "new_ui", "default": False}])

    value = resolve_feature_flag(
        "new_ui",
        run_id="run-1",
        experiment_overrides=store,
        runtime_overrides=runtime_store,
        pack_manifests=[pack],
        default=False,
    )

    assert value is True


def test_experiment_overrides_are_isolated_to_their_own_run() -> None:
    """§4's exact words: "never leak into concurrent workflows." A
    different run_id must never see run-1's override."""
    store = ExperimentOverrideStore()
    store.set_override("run-1", "new_ui", True)

    value_for_a_different_run = resolve_feature_flag(
        "new_ui", run_id="run-2", experiment_overrides=store, default=False
    )

    assert value_for_a_different_run is False
    assert store.snapshot("run-2") == {}
    assert store.snapshot("run-1") == {"new_ui": True}


def test_no_run_id_never_consults_experiment_overrides_at_all() -> None:
    store = ExperimentOverrideStore()
    store.set_override("run-1", "new_ui", True)

    value = resolve_feature_flag("new_ui", run_id=None, experiment_overrides=store, default=False)

    assert value is False


def test_clear_run_removes_that_runs_overrides_only() -> None:
    store = ExperimentOverrideStore()
    store.set_override("run-1", "new_ui", True)
    store.set_override("run-2", "new_ui", True)

    store.clear_run("run-1")

    assert store.snapshot("run-1") == {}
    assert store.snapshot("run-2") == {"new_ui": True}
