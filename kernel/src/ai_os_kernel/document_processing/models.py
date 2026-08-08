"""The real output contract this ticket's own Output names: "Extracted
text plus metadata" — plus the provenance `document_processing.md` §5
requires ("Preserve provenance: original file, hash, source location").
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ParsedDocument(BaseModel):
    """One real document, parsed. ``content_hash`` follows this
    project's own established ``sha256:<hex>`` convention
    (:mod:`ai_os_kernel.storage_service.local_store`), computed from the
    document's own raw bytes — real provenance, not a caller-supplied,
    unverified value. ``metadata`` is intentionally a plain, per-format
    dict rather than a fixed schema: each parser adapter's own real,
    honestly-different structure (Markdown's headings, Code's inferred
    language) does not force a shared shape that would leave most
    fields ``None`` for every other format."""

    model_config = ConfigDict(frozen=True)

    text: str
    format: str
    source: str
    content_hash: str
    metadata: dict[str, Any] = Field(default_factory=dict)
