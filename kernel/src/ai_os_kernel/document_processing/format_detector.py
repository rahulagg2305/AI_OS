"""Real format detection (`document_processing.md` §4's own "Format
Detector" box) — extension-based, the only signal a bare file path
genuinely carries without reading and sniffing its content, which this
step's own three text-based formats have no reliable magic-byte
signature to sniff for anyway (unlike PDF's ``%PDF-`` header or DOCX's
ZIP signature — both irrelevant here, since neither is parsed yet; see
this package's own docstring).

**Named, documented, extensible mappings — not hardcoded magic
scattered across call sites.** Every extension this module recognizes
lives in exactly one of the three dicts below; adding a new one is a
one-line, reviewable change here, never a change to
:mod:`~ai_os_kernel.document_processing.service` or any parser.
"""

from __future__ import annotations

from pathlib import Path

from ai_os_kernel.document_processing.errors import UnsupportedDocumentFormatError

FORMAT_MARKDOWN = "markdown"
FORMAT_PLAIN_TEXT = "plain_text"
FORMAT_CODE = "code"

_MARKDOWN_EXTENSIONS = frozenset({".md", ".markdown"})
_PLAIN_TEXT_EXTENSIONS = frozenset({".txt"})

# Real, common source-file extensions this project's own toolchain and
# dependencies already touch (Python/TypeScript/JavaScript Kernel+
# Dashboard code, plus the other languages this platform's own packs
# and documentation reference) — not an exhaustive list of every
# language that exists, extended as a real need arises.
CODE_LANGUAGE_BY_EXTENSION: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".java": "java",
    ".rs": "rust",
    ".rb": "ruby",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".php": "php",
    ".sh": "shell",
    ".sql": "sql",
}

# Named specifically (not lumped into "unrecognized") so the raised
# error can honestly say *why* — a real, disclosed, dependency-gated
# deferral, not a gap indistinguishable from a typo'd extension.
_DEFERRED_BINARY_FORMATS: dict[str, str] = {
    ".pdf": "PDF",
    ".docx": "DOCX/Office",
    ".doc": "DOCX/Office",
}


def detect_format(path: Path) -> str:
    """Returns one of :data:`FORMAT_MARKDOWN`/:data:`FORMAT_PLAIN_TEXT`/
    :data:`FORMAT_CODE`, or raises :class:`UnsupportedDocumentFormatError`
    for a deferred (PDF/DOCX) or genuinely unrecognized extension.
    Case-insensitive, matching every real filesystem this project
    targets (Windows is case-insensitive by default; a caller should
    never get a different answer for ``README.MD`` than ``readme.md``)."""
    suffix = path.suffix.lower()

    if suffix in _MARKDOWN_EXTENSIONS:
        return FORMAT_MARKDOWN
    if suffix in _PLAIN_TEXT_EXTENSIONS:
        return FORMAT_PLAIN_TEXT
    if suffix in CODE_LANGUAGE_BY_EXTENSION:
        return FORMAT_CODE
    if suffix in _DEFERRED_BINARY_FORMATS:
        raise UnsupportedDocumentFormatError(
            f"{_DEFERRED_BINARY_FORMATS[suffix]} ({suffix!r}) parsing is real, disclosed, "
            "deferred work — it needs a new third-party dependency this project does not "
            "yet declare (see this package's own docstring)"
        )
    raise UnsupportedDocumentFormatError(f"{suffix!r} is not a recognized document format")


__all__ = [
    "CODE_LANGUAGE_BY_EXTENSION",
    "FORMAT_CODE",
    "FORMAT_MARKDOWN",
    "FORMAT_PLAIN_TEXT",
    "detect_format",
]
