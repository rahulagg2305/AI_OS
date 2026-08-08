"""Unit tests for :func:`ai_os_kernel.traceability_engine.ids.compute_artifact_key`
— the one real, pure-logic design decision this ticket made
(``P04-S02-M16-T01``): a deterministic key so two independent callers
naming the identical real-world artifact land on the same row."""

from ai_os_kernel.traceability_engine.ids import compute_artifact_key, new_link_id


def test_the_same_type_and_external_id_always_computes_the_identical_key() -> None:
    first = compute_artifact_key(artifact_type="requirement", external_id="FR-019")
    second = compute_artifact_key(artifact_type="requirement", external_id="FR-019")

    assert first == second == "requirement:FR-019"


def test_different_artifact_types_never_collide_for_the_identical_external_id() -> None:
    requirement_key = compute_artifact_key(artifact_type="requirement", external_id="FR-019")
    test_case_key = compute_artifact_key(artifact_type="test_case", external_id="FR-019")

    assert requirement_key != test_case_key


def test_different_external_ids_never_collide_for_the_identical_type() -> None:
    first = compute_artifact_key(artifact_type="requirement", external_id="FR-019")
    second = compute_artifact_key(artifact_type="requirement", external_id="FR-020")

    assert first != second


def test_new_link_id_is_a_real_prefixed_ulid_and_genuinely_unique() -> None:
    first = new_link_id()
    second = new_link_id()

    assert first.startswith("link_")
    assert second.startswith("link_")
    assert first != second
