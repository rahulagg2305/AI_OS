"""Real tests for :mod:`ai_os_kernel.document_processing.parsers` — pure,
deterministic logic over already-decoded text, no file I/O needed."""

from __future__ import annotations

from ai_os_kernel.document_processing.parsers import CodeParser, MarkdownParser, PlainTextParser

_HASH = "sha256:test"


def test_plain_text_parser_reports_line_and_char_counts() -> None:
    result = PlainTextParser().parse(
        text="line one\nline two\n", source="notes.txt", content_hash=_HASH
    )

    assert result.format == "plain_text"
    assert result.text == "line one\nline two\n"
    assert result.source == "notes.txt"
    assert result.content_hash == _HASH
    assert result.metadata["line_count"] == 2
    assert result.metadata["char_count"] == len("line one\nline two\n")


def test_markdown_parser_extracts_atx_headings_in_order() -> None:
    text = "# Title\n\nSome intro text.\n\n## Section One\n\nBody.\n\n### Sub Section\n"

    result = MarkdownParser().parse(text=text, source="doc.md", content_hash=_HASH)

    assert result.format == "markdown"
    assert result.metadata["headings"] == ["Title", "Section One", "Sub Section"]
    assert result.metadata["heading_count"] == 3


def test_markdown_parser_ignores_a_hash_that_is_not_a_real_heading() -> None:
    """A `#` not followed by whitespace (e.g. a hex color or a hashtag
    in prose) must not be misread as a heading."""
    text = "This costs #100 not a heading.\n#nowhitespace\n"

    result = MarkdownParser().parse(text=text, source="doc.md", content_hash=_HASH)

    assert result.metadata["headings"] == []


def test_markdown_parser_with_no_headings_reports_an_empty_list() -> None:
    result = MarkdownParser().parse(
        text="just prose, no headings.\n", source="doc.md", content_hash=_HASH
    )

    assert result.metadata["headings"] == []
    assert result.metadata["heading_count"] == 0


def test_code_parser_infers_language_from_a_known_extension() -> None:
    result = CodeParser().parse(text="def f():\n    pass\n", source="module.py", content_hash=_HASH)

    assert result.format == "code"
    assert result.metadata["language"] == "python"


def test_code_parser_reports_unknown_language_for_an_unmapped_extension() -> None:
    """Reached only if a caller constructs `CodeParser` directly for an
    extension `format_detector.detect_format` would never route here in
    the first place — an honest fallback, not an unreachable branch."""
    result = CodeParser().parse(text="???", source="mystery.foo", content_hash=_HASH)

    assert result.metadata["language"] == "unknown"
