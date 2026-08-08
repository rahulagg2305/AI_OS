"""The real composition root this ticket's own Input/Output describes:
"A document" in, "Extracted text plus metadata" out — reads a real file
from disk, computes its real provenance hash, detects its real format,
and dispatches to the matching real :class:`~ai_os_kernel.
document_processing.parsers.DocumentParser`.

**A plain, explicit registry — not a caller-configurable seam.** Unlike
:mod:`~ai_os_kernel.sandbox.default_executor`'s env-var-selected
backend (a genuine deployment choice), which parser handles which
format is not a configuration decision at all — it is this module's own
fixed, documented mapping (`document_processing.md` §4's own boxes).
Adding a fourth real parser later is a one-line change to
:data:`_PARSERS_BY_FORMAT`, not a new environment variable.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from ai_os_kernel.document_processing.errors import DocumentDecodeError
from ai_os_kernel.document_processing.format_detector import (
    FORMAT_CODE,
    FORMAT_MARKDOWN,
    FORMAT_PLAIN_TEXT,
    detect_format,
)
from ai_os_kernel.document_processing.models import ParsedDocument
from ai_os_kernel.document_processing.parsers import (
    CodeParser,
    DocumentParser,
    MarkdownParser,
    PlainTextParser,
)

_PARSERS_BY_FORMAT: dict[str, DocumentParser] = {
    FORMAT_MARKDOWN: MarkdownParser(),
    FORMAT_PLAIN_TEXT: PlainTextParser(),
    FORMAT_CODE: CodeParser(),
}


def parse_document(path: Path) -> ParsedDocument:
    """Real, synchronous file I/O (parsing is CPU-bound, not I/O-bound
    once the bytes are read — no ``asyncio.to_thread`` wrapper this
    package's own callers cannot already provide themselves if run from
    an async context).

    Raises :class:`~ai_os_kernel.document_processing.errors.
    UnsupportedDocumentFormatError` for a deferred or unrecognized
    extension (via :func:`detect_format`), or
    :class:`~ai_os_kernel.document_processing.errors.DocumentDecodeError`
    if the file is not valid UTF-8 — every format this step supports is
    text-based, so a decode failure means the file's real content does
    not match what its own extension claims, not a case to silently
    paper over with replacement characters.

    **Line endings are normalized to ``\\n`` in the returned ``text``**
    (`document_processing.md` §2: "Produce consistent, machine-usable
    representations") — a real, cross-platform document (checked out on
    Windows with CRLF, authored on Linux/macOS with LF) must parse
    identically regardless of which line ending its bytes happen to
    carry; ``\\r\\n``/lone ``\\r`` would otherwise leak into every
    downstream consumer's own line-counting and index-based chunking
    (`P05-S01-M26-T02`). ``content_hash`` is computed from the file's
    real, un-normalized raw bytes — provenance describes what is
    genuinely on disk, not a post-processed view of it.
    """
    document_format = detect_format(path)
    raw_bytes = path.read_bytes()
    content_hash = f"sha256:{hashlib.sha256(raw_bytes).hexdigest()}"

    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DocumentDecodeError(
            f"{path} was detected as {document_format!r} but is not valid UTF-8: {exc}"
        ) from exc
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    parser = _PARSERS_BY_FORMAT[document_format]
    return parser.parse(text=text, source=str(path), content_hash=content_hash)


__all__ = ["parse_document"]
