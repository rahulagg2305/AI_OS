"""Real, end-to-end tests for
:func:`ai_os_kernel.document_processing.service.parse_document` — real
files on real disk (`tmp_path`), no fakes needed: there is nothing here
worth substituting (ADR-0004/ADR-0015 apply to a real collaborator with
its own I/O or non-determinism; plain local file reads have neither)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from ai_os_kernel.document_processing.errors import (
    DocumentDecodeError,
    UnsupportedDocumentFormatError,
)
from ai_os_kernel.document_processing.service import parse_document


def test_parsing_a_real_markdown_file_end_to_end(tmp_path: Path) -> None:
    path = tmp_path / "readme.md"
    path.write_text("# Hello\n\nBody text.\n", encoding="utf-8")

    result = parse_document(path)

    assert result.format == "markdown"
    assert result.text == "# Hello\n\nBody text.\n"
    assert result.source == str(path)
    assert result.metadata["headings"] == ["Hello"]
    expected_hash = f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
    assert result.content_hash == expected_hash


def test_parsing_a_real_plain_text_file_end_to_end(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("just some notes\n", encoding="utf-8")

    result = parse_document(path)

    assert result.format == "plain_text"
    assert result.metadata["line_count"] == 1


def test_parsing_a_real_python_file_end_to_end(tmp_path: Path) -> None:
    path = tmp_path / "module.py"
    path.write_text("def f() -> None:\n    return None\n", encoding="utf-8")

    result = parse_document(path)

    assert result.format == "code"
    assert result.metadata["language"] == "python"


def test_two_files_with_identical_content_get_identical_hashes(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("same content\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("same content\n", encoding="utf-8")

    result_a = parse_document(tmp_path / "a.txt")
    result_b = parse_document(tmp_path / "b.txt")

    assert result_a.content_hash == result_b.content_hash


def test_parsing_a_pdf_is_refused_with_a_disclosed_deferred_reason(tmp_path: Path) -> None:
    path = tmp_path / "spec.pdf"
    path.write_bytes(b"%PDF-1.4 not a real pdf")

    with pytest.raises(UnsupportedDocumentFormatError, match="PDF"):
        parse_document(path)


def test_crlf_line_endings_are_normalized_to_lf(tmp_path: Path) -> None:
    """A real cross-platform concern, not a hypothetical: this project's
    own CI runs on Linux while local development happens on Windows —
    a document's line endings must not change what a parser reports."""
    path = tmp_path / "windows.md"
    path.write_bytes(b"# Title\r\n\r\nBody line one.\r\nBody line two.\r\n")

    result = parse_document(path)

    assert "\r" not in result.text
    assert result.text == "# Title\n\nBody line one.\nBody line two.\n"
    assert result.metadata["headings"] == ["Title"]
    # Provenance still reflects the real, un-normalized bytes on disk.
    assert result.content_hash == f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def test_a_file_whose_content_does_not_match_its_extension_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_bytes(b"\xff\xfe\x00\x01not valid utf-8 \xff")

    with pytest.raises(DocumentDecodeError):
        parse_document(path)
