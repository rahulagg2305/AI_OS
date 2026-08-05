"""Unit tests for the real cache-boundary marker — no I/O, pure
functions layered on the already-real, unchanged render_template()."""

import pytest

from ai_os_kernel.prompt_engine.cache_boundary import (
    CACHE_BOUNDARY_MARKER,
    render_with_cache_boundary,
    split_at_cache_boundary,
)
from ai_os_kernel.prompt_engine.errors import PromptCacheBoundaryError, PromptVariableMissingError


def test_split_at_cache_boundary_separates_stable_from_volatile() -> None:
    template = "You are a helpful assistant.{{cache_boundary}}Task: {{task}}"

    stable, volatile = split_at_cache_boundary(template)

    assert stable == "You are a helpful assistant."
    assert volatile == "Task: {{task}}"


def test_split_at_cache_boundary_rejects_a_missing_marker() -> None:
    with pytest.raises(PromptCacheBoundaryError, match="does not contain"):
        split_at_cache_boundary("no marker here at all")


def test_split_at_cache_boundary_rejects_more_than_one_marker() -> None:
    template = f"a{CACHE_BOUNDARY_MARKER}b{CACHE_BOUNDARY_MARKER}c"

    with pytest.raises(PromptCacheBoundaryError, match="contains 2"):
        split_at_cache_boundary(template)


def test_render_with_cache_boundary_reports_the_real_rendered_index() -> None:
    template = "System: be concise.{{cache_boundary}}Task: {{task}}"

    content, boundary_index = render_with_cache_boundary(template, {"task": "summarize this"})

    assert content == "System: be concise.Task: summarize this"
    assert boundary_index == len("System: be concise.")
    assert content[:boundary_index] == "System: be concise."
    assert content[boundary_index:] == "Task: summarize this"


def test_boundary_index_reflects_real_substitution_length_changes_before_the_boundary() -> None:
    # The stable side itself contains a variable whose real substituted
    # value is a different length than its own placeholder -- proving
    # the boundary is computed on the REAL rendered text, not the raw
    # template's own marker position (which would be wrong here).
    template = "You are a {{role}} assistant.{{cache_boundary}}Task: {{task}}"

    content, boundary_index = render_with_cache_boundary(
        template, {"role": "senior software engineering", "task": "review this PR"}
    )

    expected_stable = "You are a senior software engineering assistant."
    assert content == expected_stable + "Task: review this PR"
    assert boundary_index == len(expected_stable)
    # The raw template's marker sits at a different raw offset than the
    # real, rendered boundary -- confirming this isn't just echoing the
    # template's own marker position.
    raw_marker_offset = template.index(CACHE_BOUNDARY_MARKER)
    assert boundary_index != raw_marker_offset


def test_render_with_cache_boundary_still_validates_missing_variables_on_either_side() -> None:
    template = "Hello {{name}}.{{cache_boundary}}Task: {{task}}"

    with pytest.raises(PromptVariableMissingError, match="name"):
        render_with_cache_boundary(template, {"task": "do something"})


def test_render_with_cache_boundary_handles_an_empty_stable_prefix() -> None:
    template = "{{cache_boundary}}Task: {{task}}"

    content, boundary_index = render_with_cache_boundary(template, {"task": "go"})

    assert boundary_index == 0
    assert content == "Task: go"


def test_render_with_cache_boundary_handles_an_empty_volatile_suffix() -> None:
    template = "Stable only.{{cache_boundary}}"

    content, boundary_index = render_with_cache_boundary(template, {})

    assert content == "Stable only."
    assert boundary_index == len("Stable only.")
