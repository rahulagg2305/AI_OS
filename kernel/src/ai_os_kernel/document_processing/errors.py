"""Real errors for :mod:`ai_os_kernel.document_processing`."""

from __future__ import annotations


class DocumentProcessingError(Exception):
    """Base class for every real failure this package raises."""


class UnsupportedDocumentFormatError(DocumentProcessingError):
    """Raised for a file extension this package does not (yet, or ever)
    parse — a genuinely unrecognized extension, or one of the two
    formats (PDF, DOCX/Office) this step's own docstring discloses as
    deferred, dependency-gated work. Raised clearly rather than
    silently mis-detecting the format or letting a downstream decode
    error stand in for it."""


class DocumentDecodeError(DocumentProcessingError):
    """Raised when a file recognized as a text-based format (Markdown,
    Plain Text, Code) cannot be decoded as UTF-8 — a real, honest
    failure rather than silently substituting replacement characters
    for content this package cannot actually read."""
