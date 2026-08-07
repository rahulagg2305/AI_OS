"""Deterministic unit tests for `plan_replicates` — pure, no I/O.

The real, Postgres-backed proof that `ExperimentRunRecorder`'s real
implementation (`ai_os_kernel.sdk_adapters.experiment_run_recorder_adapter`)
genuinely writes `evaluation.experiment_runs` rows lives in
`tests/integration/evaluation_engine/test_experiment_run_recorder.py`.
"""

from __future__ import annotations

import pytest

from ai_os_pack_benchmarking.experiment_definition import ExperimentVariant
from ai_os_pack_benchmarking.replicate_management import (
    ReplicatePlan,
    ReplicateValidationError,
    plan_replicates,
)

_VARIANT = ExperimentVariant(variant_key="control", model_alias="coding-strong")


def test_plan_replicates_produces_the_real_requested_count() -> None:
    plans = plan_replicates(_VARIANT, runs_per_variant=3)

    assert len(plans) == 3
    assert all(isinstance(plan, ReplicatePlan) for plan in plans)


def test_plan_replicates_numbers_each_replicate_from_zero() -> None:
    plans = plan_replicates(_VARIANT, runs_per_variant=4)

    assert [plan.replicate_index for plan in plans] == [0, 1, 2, 3]


def test_plan_replicates_carries_the_variants_own_real_fields() -> None:
    plans = plan_replicates(_VARIANT, runs_per_variant=3)

    assert all(plan.variant_key == "control" for plan in plans)
    assert all(plan.model_alias == "coding-strong" for plan in plans)


def test_fewer_than_three_replicates_is_rejected() -> None:
    with pytest.raises(ReplicateValidationError, match="runs_per_variant must be >= 3"):
        plan_replicates(_VARIANT, runs_per_variant=2)


def test_more_than_the_minimum_is_accepted() -> None:
    plans = plan_replicates(_VARIANT, runs_per_variant=10)

    assert len(plans) == 10
