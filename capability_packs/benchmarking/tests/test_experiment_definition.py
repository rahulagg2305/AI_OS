"""Deterministic unit tests for `validate_experiment_spec` — no
database, no network (ADR-0004: a scripted fake `WorkflowDefinitionExistenceCheck`
is a legitimate substitute for pure, deterministic logic).

The real, Postgres-backed proof that the real `WorkflowDefinitionExistenceCheck`
implementation (`ai_os_kernel.sdk_adapters.workflow_definition_existence_adapter`)
genuinely queries `catalog.workflow_definitions` lives in
`tests/integration/evaluation_engine/test_experiment_definition_validation.py`.
"""

from __future__ import annotations

import pytest

from ai_os_pack_benchmarking.experiment_definition import (
    ExperimentDefinition,
    ExperimentSpec,
    ExperimentValidationError,
    ExperimentVariant,
    validate_experiment_spec,
)

_REAL_DEFINITION_ID = "se.delivery_pipeline"
_REAL_DEFINITION_VERSION = "1.9.0"


class _FakeExistenceCheck:
    """Scripted by `(definition_id, version) -> bool` — a real
    Protocol implementation, deterministic and offline."""

    def __init__(self, *, known: set[tuple[str, str]]) -> None:
        self._known = known

    async def exists(self, *, definition_id: str, version: str) -> bool:
        return (definition_id, version) in self._known


def _spec(**overrides: object) -> ExperimentSpec:
    defaults: dict[str, object] = {
        "name": "compare opus vs sonnet",
        "description": "a real, minimal two-variant comparison",
        "definition_id": _REAL_DEFINITION_ID,
        "definition_version": _REAL_DEFINITION_VERSION,
        "variants": [
            ExperimentVariant(variant_key="control", model_alias="coding-strong"),
            ExperimentVariant(variant_key="treatment", model_alias="reasoning"),
        ],
        "runs_per_variant": 3,
        "created_by": "test-principal",
    }
    defaults.update(overrides)
    return ExperimentSpec(**defaults)


def _known_existence_check() -> _FakeExistenceCheck:
    return _FakeExistenceCheck(known={(_REAL_DEFINITION_ID, _REAL_DEFINITION_VERSION)})


@pytest.mark.asyncio
async def test_a_real_valid_spec_produces_a_real_definition() -> None:
    definition = await validate_experiment_spec(_spec(), existence_check=_known_existence_check())

    assert isinstance(definition, ExperimentDefinition)
    assert definition.name == "compare opus vs sonnet"
    assert len(definition.variants) == 2
    assert definition.runs_per_variant == 3


@pytest.mark.asyncio
async def test_fewer_than_three_replicates_is_rejected() -> None:
    with pytest.raises(ExperimentValidationError, match="runs_per_variant must be >= 3"):
        await validate_experiment_spec(
            _spec(runs_per_variant=2), existence_check=_known_existence_check()
        )


@pytest.mark.asyncio
async def test_fewer_than_two_variants_is_rejected() -> None:
    with pytest.raises(ExperimentValidationError, match="at least 2 variants"):
        await validate_experiment_spec(
            _spec(variants=[ExperimentVariant(variant_key="solo", model_alias="coding-strong")]),
            existence_check=_known_existence_check(),
        )


@pytest.mark.asyncio
async def test_duplicate_variant_keys_are_rejected() -> None:
    with pytest.raises(ExperimentValidationError, match="duplicate variant_key"):
        await validate_experiment_spec(
            _spec(
                variants=[
                    ExperimentVariant(variant_key="same", model_alias="coding-strong"),
                    ExperimentVariant(variant_key="same", model_alias="reasoning"),
                ]
            ),
            existence_check=_known_existence_check(),
        )


@pytest.mark.asyncio
async def test_a_declared_sampling_parameter_variable_is_rejected() -> None:
    with pytest.raises(ExperimentValidationError, match="sampling parameters"):
        await validate_experiment_spec(
            _spec(variables={"temperature": [0.0, 1.0]}),
            existence_check=_known_existence_check(),
        )


@pytest.mark.asyncio
async def test_a_pinned_workflow_that_does_not_exist_is_rejected() -> None:
    with pytest.raises(ExperimentValidationError, match="no workflow definition exists"):
        await validate_experiment_spec(
            _spec(),
            existence_check=_FakeExistenceCheck(known=set()),
        )


@pytest.mark.asyncio
async def test_multiple_real_failures_are_all_reported_together() -> None:
    with pytest.raises(ExperimentValidationError) as exc_info:
        await validate_experiment_spec(
            _spec(
                runs_per_variant=1,
                variants=[ExperimentVariant(variant_key="solo", model_alias="coding-strong")],
            ),
            existence_check=_known_existence_check(),
        )

    assert len(exc_info.value.errors) == 2
