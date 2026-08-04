"""Unit tests for prompt composition and inheritance — no I/O, pure
functions layered on the already-real, unchanged render_template()."""

import pytest

from ai_os_kernel.prompt_engine.composition import (
    compose_fragments,
    compose_with_inheritance,
    render_composed,
)
from ai_os_kernel.prompt_engine.errors import (
    PromptCompositionError,
    PromptFragmentOverrideError,
    PromptVariableMissingError,
)


def test_compose_fragments_joins_in_order_with_the_default_separator() -> None:
    result = compose_fragments(["You are a helpful assistant.", "Be concise.", "Use markdown."])

    assert result == "You are a helpful assistant.\n\nBe concise.\n\nUse markdown."


def test_compose_fragments_accepts_a_real_custom_separator() -> None:
    result = compose_fragments(["first", "second"], separator=" | ")

    assert result == "first | second"


def test_compose_fragments_rejects_an_empty_sequence() -> None:
    with pytest.raises(PromptCompositionError, match="fragments must not be empty"):
        compose_fragments([])


def test_compose_with_inheritance_overrides_named_fragments_and_keeps_others() -> None:
    parent = {
        "role": "You are a {{role}} assistant.",
        "tone": "Be formal.",
        "closing": "Sign off politely.",
    }

    result = compose_with_inheritance(parent=parent, overrides={"tone": "Be casual."})

    assert result == ("You are a {{role}} assistant.\n\nBe casual.\n\nSign off politely.")


def test_compose_with_inheritance_with_no_overrides_reproduces_the_parent() -> None:
    parent = {"a": "alpha", "b": "beta"}

    assert compose_with_inheritance(parent=parent) == "alpha\n\nbeta"


def test_compose_with_inheritance_preserves_parent_order_regardless_of_override_order() -> None:
    parent = {"first": "1", "second": "2", "third": "3"}

    # Overrides dict declared out of parent order -- composition order
    # must still follow the parent's own key order, not the override's.
    result = compose_with_inheritance(parent=parent, overrides={"third": "III", "first": "I"})

    assert result == "I\n\n2\n\nIII"


def test_compose_with_inheritance_rejects_an_override_naming_an_unknown_fragment() -> None:
    parent = {"role": "assistant"}

    with pytest.raises(
        PromptFragmentOverrideError, match="fragment.*the parent does not declare: typo_name"
    ):
        compose_with_inheritance(parent=parent, overrides={"typo_name": "oops"})


def test_render_composed_produces_real_substituted_output_end_to_end() -> None:
    fragments = ["You are a {{role}} assistant.", "Always respond in {{language}}."]

    result = render_composed(fragments, {"role": "coding", "language": "English"})

    assert result == "You are a coding assistant.\n\nAlways respond in English."


def test_render_composed_with_inheritance_end_to_end() -> None:
    parent = {"role": "You are a {{role}} assistant.", "tone": "Be formal."}
    composed_template = compose_with_inheritance(parent=parent, overrides={"tone": "Be {{tone}}."})

    rendered = render_composed([composed_template], {"role": "research", "tone": "casual"})

    assert rendered == "You are a research assistant.\n\nBe casual."


def test_render_composed_still_validates_missing_variables() -> None:
    with pytest.raises(PromptVariableMissingError, match="name"):
        render_composed(["Hello, {{name}}!"], {})
