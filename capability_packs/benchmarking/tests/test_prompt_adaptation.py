"""Deterministic unit tests for prompt adaptation recording — pure
string comparison, no I/O."""

from __future__ import annotations

from ai_os_pack_benchmarking.experiment_definition import ExperimentSpec, ExperimentVariant
from ai_os_pack_benchmarking.prompt_adaptation import (
    record_prompt_adaptation,
    with_recorded_prompt_adaptation,
)


def _spec() -> ExperimentSpec:
    return ExperimentSpec(
        name="compare opus vs sonnet",
        description="a real, minimal two-variant comparison",
        definition_id="se.delivery_pipeline",
        definition_version="1.9.0",
        variants=[
            ExperimentVariant(variant_key="control", model_alias="coding-strong"),
            ExperimentVariant(variant_key="treatment", model_alias="reasoning"),
        ],
        runs_per_variant=3,
        created_by="test-principal",
    )


def test_a_byte_identical_prompt_records_nothing() -> None:
    result = record_prompt_adaptation(
        variant_key="control", canonical_prompt="Do the thing.", adapted_prompt="Do the thing."
    )

    assert result is None


def test_a_genuinely_adapted_prompt_is_recorded() -> None:
    result = record_prompt_adaptation(
        variant_key="treatment",
        canonical_prompt="Do the thing.",
        adapted_prompt="Do the thing, reasoning model.",
    )

    assert result is not None
    variable_name, variable_value = result
    assert variable_name == "prompt_adaptation:treatment"
    assert variable_value == {
        "canonical_prompt": "Do the thing.",
        "adapted_prompt": "Do the thing, reasoning model.",
    }


def test_with_recorded_prompt_adaptation_leaves_an_unadapted_spec_unchanged() -> None:
    spec = _spec()

    result = with_recorded_prompt_adaptation(
        spec,
        variant_key="control",
        canonical_prompt="Do the thing.",
        adapted_prompt="Do the thing.",
    )

    assert result == spec
    assert result.variables == {}


def test_with_recorded_prompt_adaptation_folds_a_real_adaptation_into_variables() -> None:
    spec = _spec()

    result = with_recorded_prompt_adaptation(
        spec,
        variant_key="treatment",
        canonical_prompt="Do the thing.",
        adapted_prompt="Do the thing, reasoning model.",
    )

    assert result.variables == {
        "prompt_adaptation:treatment": {
            "canonical_prompt": "Do the thing.",
            "adapted_prompt": "Do the thing, reasoning model.",
        }
    }
    # The original spec is untouched — a new, distinct object.
    assert spec.variables == {}


def test_recording_two_variants_own_real_adaptations_accumulates_both() -> None:
    spec = _spec()

    spec = with_recorded_prompt_adaptation(
        spec,
        variant_key="control",
        canonical_prompt="Do the thing.",
        adapted_prompt="Do the thing, control model.",
    )
    spec = with_recorded_prompt_adaptation(
        spec,
        variant_key="treatment",
        canonical_prompt="Do the thing.",
        adapted_prompt="Do the thing, reasoning model.",
    )

    assert set(spec.variables.keys()) == {
        "prompt_adaptation:control",
        "prompt_adaptation:treatment",
    }
