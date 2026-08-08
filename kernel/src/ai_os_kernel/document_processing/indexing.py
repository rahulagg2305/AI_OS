"""Real production wiring connecting Document Processing's own parsed
output to the already-real, already-tested Indexing pipeline
(:mod:`ai_os_kernel.knowledge_manager.indexing`, built at
`P02-S04-M09-T03`) — `P05-S01-M26-T02`'s own real, minimal scope, per
the resolved design fork (`AskUserQuestion`): reuse the existing, real,
versioned fixed-size chunker unchanged; build only the glue. No
parallel chunking mechanism.

**The first real production caller of `IndexingService`.** Confirmed
by search: `IndexingService`/`chunk_content` had zero real callers
anywhere in this codebase before this step — proven and tested, but
genuinely unused, the identical "proven, unused" shape already
established for the Notification Service and the WebSocket endpoint's
own producer gap.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.document_processing.format_detector import (
    FORMAT_CODE,
    FORMAT_MARKDOWN,
    FORMAT_PLAIN_TEXT,
)
from ai_os_kernel.document_processing.service import parse_document
from ai_os_kernel.knowledge_manager.indexing import IndexingService, IndexResult
from ai_os_kernel.persistence.knowledge_writer import KnowledgeWriter

# A real, documented mapping from this package's own closed format
# vocabulary to a real MIME-style `media_type` string — the identical
# convention every existing `knowledge.documents` writer/test already
# uses (`"text/markdown"`), extended here for the two formats this
# package's own parsers additionally produce. Exhaustive by
# construction: `parse_document` only ever returns one of these three
# formats or raises before reaching this module at all.
_MEDIA_TYPE_BY_FORMAT: dict[str, str] = {
    FORMAT_MARKDOWN: "text/markdown",
    FORMAT_PLAIN_TEXT: "text/plain",
    FORMAT_CODE: "text/x-source",
}


async def index_document_file(
    path: Path,
    *,
    engine: AsyncEngine,
    writer: KnowledgeWriter,
    trust: Literal["trusted", "untrusted"],
    project_id: str | None = None,
) -> IndexResult:
    """Parses ``path`` for real (:func:`~ai_os_kernel.document_processing.
    service.parse_document`) and indexes the result through the real,
    unchanged :class:`~ai_os_kernel.knowledge_manager.indexing.
    IndexingService` — the same archive-and-replace-by-content-hash
    change policy, the same versioned fixed-size chunker, applied for
    the first time to a real Document Processing input rather than
    caller-supplied raw text.

    ``trust`` is a required, caller-supplied parameter, never a default
    this function invents — whether a given file is trusted content
    depends on where it came from (a team-authored spec vs. an ingested
    repository), a real fact this function has no way to infer from
    the file itself (ADR-0016's own provenance-tagging principle)."""
    parsed = parse_document(path)
    media_type = _MEDIA_TYPE_BY_FORMAT[parsed.format]
    service = IndexingService(engine=engine, writer=writer)
    return await service.index_document(
        source_uri=parsed.source,
        content=parsed.text,
        media_type=media_type,
        trust=trust,
        project_id=project_id,
    )


__all__ = ["index_document_file"]
