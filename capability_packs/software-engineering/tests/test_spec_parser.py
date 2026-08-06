"""Deterministic, pure-function tests for
:mod:`ai_os_pack_software_engineering.workflows.spec_parser` — no
database, no LLM, no sandbox: this module has no I/O of any kind."""

from __future__ import annotations

import pytest

from ai_os_pack_software_engineering.workflows.spec_parser import (
    SpecificationParseError,
    parse_markdown_specification,
)


def test_a_simple_bullet_list_parses_into_ordered_items() -> None:
    text = "- First item\n- Second item\n- Third item\n"

    assert parse_markdown_specification(text) == [
        "First item",
        "Second item",
        "Third item",
    ]


def test_asterisk_markers_work_identically_to_hyphens() -> None:
    text = "* First item\n* Second item\n"

    assert parse_markdown_specification(text) == ["First item", "Second item"]


def test_a_preamble_paragraph_before_the_list_is_ignored() -> None:
    text = (
        "# Specification\n"
        "\n"
        "Some framing prose that is not itself a requirement.\n"
        "\n"
        "- The one real item\n"
    )

    assert parse_markdown_specification(text) == ["The one real item"]


def test_an_indented_continuation_line_is_folded_into_its_parent_item() -> None:
    text = "- The system must authenticate users\n  via OAuth2, not passwords.\n"

    assert parse_markdown_specification(text) == [
        "The system must authenticate users via OAuth2, not passwords."
    ]


def test_a_nested_bullet_is_folded_into_its_parent_items_text_verbatim() -> None:
    text = "- Parent item\n  - Nested item\n"

    assert parse_markdown_specification(text) == ["Parent item - Nested item"]


def test_no_bullet_items_raises_a_clear_error() -> None:
    with pytest.raises(SpecificationParseError, match="no top-level bullet item"):
        parse_markdown_specification("Just a paragraph, no list at all.\n")


def test_an_empty_bullet_raises_a_clear_error_naming_its_position() -> None:
    with pytest.raises(SpecificationParseError, match=r"position\(s\) \[2\]"):
        parse_markdown_specification("- First item\n-   \n- Third item\n")
