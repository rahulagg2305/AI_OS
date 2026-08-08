"""The real Parser Adapters (`document_processing.md` §4) this step
builds — see this package's own docstring for which 3 of the document's
5 boxes these are, and why the other 2 (PDF, DOCX/Office) are not.

``DocumentParser`` is a Protocol precisely so a future PDF/DOCX adapter
plugs into :mod:`~ai_os_kernel.document_processing.service` unchanged
(ADR-0004: interface-driven, configuration over code) — every parser
here takes the identical, already-decoded ``text``/``source`` shape a
binary-format adapter would also need (it would simply decode its own
bytes into ``text`` before reaching this same seam).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Protocol

from ai_os_kernel.document_processing.format_detector import CODE_LANGUAGE_BY_EXTENSION
from ai_os_kernel.document_processing.models import ParsedDocument

_MARKDOWN_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")


class DocumentParser(Protocol):
    """The one real seam every parser adapter implements — ``text`` is
    already-decoded UTF-8 content (decoding, and the real, disclosed
    failure mode when it is not valid UTF-8, is
    :mod:`~ai_os_kernel.document_processing.service`'s own job, common
    to every text-based format, not repeated per adapter)."""

    def parse(self, *, text: str, source: str, content_hash: str) -> ParsedDocument: ...


def _line_and_char_counts(text: str) -> dict[str, Any]:
    """Shared, real, honest structure every text-based format can
    report identically — not invented per adapter."""
    return {"line_count": len(text.splitlines()), "char_count": len(text)}


class PlainTextParser:
    """The design document's own "Plain Text Parser" box: no structure
    to extract beyond the text itself — the real, honest minimum."""

    def parse(self, *, text: str, source: str, content_hash: str) -> ParsedDocument:
        return ParsedDocument(
            text=text,
            format="plain_text",
            source=source,
            content_hash=content_hash,
            metadata=_line_and_char_counts(text),
        )


class MarkdownParser:
    """The design document's own "Markdown Parser" box —
    §2's "Extract clean text and structure (headings, sections ...)"
    applied to the one structural element a dependency-free, line-based
    scan can genuinely extract without a full CommonMark parser: ATX
    headings (``#`` through ``######``). Setext headings (an
    underlined title on the following line) and any other Markdown
    structure are real, disclosed, unbuilt — this is a real subset, not
    a full Markdown AST."""

    def parse(self, *, text: str, source: str, content_hash: str) -> ParsedDocument:
        headings = [
            match.group(2).strip()
            for line in text.splitlines()
            if (match := _MARKDOWN_HEADING_PATTERN.match(line)) is not None
        ]
        metadata = _line_and_char_counts(text)
        metadata["headings"] = headings
        metadata["heading_count"] = len(headings)
        return ParsedDocument(
            text=text,
            format="markdown",
            source=source,
            content_hash=content_hash,
            metadata=metadata,
        )


class CodeParser:
    """The design document's own "Code-aware Parser" box — scoped
    honestly to what is genuinely dependency-free and language-agnostic:
    identifying the language from the file's own extension. Real,
    per-language structure extraction (functions, classes, imports)
    would need a real parser per language (or a dependency like
    `tree-sitter`) — disclosed, unbuilt, out of this step's scope."""

    def parse(self, *, text: str, source: str, content_hash: str) -> ParsedDocument:
        suffix = Path(source).suffix.lower()
        metadata = _line_and_char_counts(text)
        metadata["language"] = CODE_LANGUAGE_BY_EXTENSION.get(suffix, "unknown")
        return ParsedDocument(
            text=text, format="code", source=source, content_hash=content_hash, metadata=metadata
        )


__all__ = ["CodeParser", "DocumentParser", "MarkdownParser", "PlainTextParser"]
