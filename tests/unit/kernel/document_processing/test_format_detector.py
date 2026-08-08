"""Real tests for :mod:`ai_os_kernel.document_processing.format_detector`
— pure logic over a `Path`, no real file needed to exist on disk (this
module only ever looks at the suffix)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_os_kernel.document_processing.errors import UnsupportedDocumentFormatError
from ai_os_kernel.document_processing.format_detector import (
    FORMAT_CODE,
    FORMAT_MARKDOWN,
    FORMAT_PLAIN_TEXT,
    detect_format,
)


@pytest.mark.parametrize("suffix", [".md", ".markdown", ".MD"])
def test_markdown_extensions_are_detected(suffix: str) -> None:
    assert detect_format(Path(f"readme{suffix}")) == FORMAT_MARKDOWN


def test_plain_text_extension_is_detected() -> None:
    assert detect_format(Path("notes.txt")) == FORMAT_PLAIN_TEXT


@pytest.mark.parametrize("suffix", [".py", ".ts", ".go", ".rs", ".java"])
def test_common_code_extensions_are_detected(suffix: str) -> None:
    assert detect_format(Path(f"main{suffix}")) == FORMAT_CODE


def test_detection_is_case_insensitive() -> None:
    assert detect_format(Path("MAIN.PY")) == FORMAT_CODE


def test_pdf_is_refused_with_a_disclosed_deferred_reason() -> None:
    with pytest.raises(UnsupportedDocumentFormatError, match="PDF"):
        detect_format(Path("spec.pdf"))


def test_docx_is_refused_with_a_disclosed_deferred_reason() -> None:
    with pytest.raises(UnsupportedDocumentFormatError, match="DOCX"):
        detect_format(Path("spec.docx"))


def test_a_genuinely_unknown_extension_is_refused() -> None:
    with pytest.raises(UnsupportedDocumentFormatError, match="not a recognized"):
        detect_format(Path("mystery.xyz"))


def test_a_missing_extension_is_refused() -> None:
    with pytest.raises(UnsupportedDocumentFormatError):
        detect_format(Path("no_extension_at_all"))
