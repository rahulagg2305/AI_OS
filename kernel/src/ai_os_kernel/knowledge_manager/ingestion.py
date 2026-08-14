"""Knowledge Ingestion (§5's own box) — the real production caller that
makes §4's "ingest knowledge from approved sources" **automatic rather
than merely callable** (`P02-S04-M09-T07`).

**What was missing.** `index_document_file` (`P05-S01-M26-T02`) was the
only caller of `IndexingService`, and it had no caller of its own
anywhere in `kernel/src` — no `bootstrap.py` wiring, no API route. The
whole chain beneath it was real and proven (format detection, three
parser adapters, chunking, the knowledge writer, and since
`P02-S04-M09-T06` in-line embedding), but nothing ever started it. This
module is that starter.

**Source: decided by documentation, not chosen here.**
`knowledge/knowledge_base_structure.md` §3 states outright that "The
Constitution, architecture documents, and ADRs live in `docs/` and are
ingested by the Knowledge Manager from there". Which directories to
scan is therefore configuration (`PlatformConfig.knowledge_source_dirs`),
not a constant in this module — and it defaults to ``None``, meaning
**no ingestion at all** unless an environment asks for it, the same
"unconfigured means the real feature does not start" shape
``notification_webhook_url``/``oidc_issuer`` already establish. Note
that the `knowledge/` tree itself is *not* ingestible today: that same
document's Implementation Status records it as absent from a fresh
clone with no tracked content.

**Trigger: a startup scan, by product-owner decision (2026-08-14).**
The real precedent is `capability_pack_dirs` — configuration-driven
filesystem-scan discovery at startup (ADR-0009, wired in `bootstrap.py`)
— rather than an HTTP route (no knowledge route is specified in any API
document, and accepting a filesystem path over HTTP is a
path-traversal surface) or a workflow step (no workflow declares
ingestion). Re-scanning on every boot is safe and cheap by
construction, not by luck: `IndexingService` already skips unchanged
content by `content_hash`, and `P02-S04-M09-T06` proved that an
unchanged re-index makes **zero** provider calls, so a reboot re-scans
without re-billing.

**Trust: structurally ``"untrusted"``, and this is a security decision
with a documented conflict behind it.** ADR-0016 control 1 states that
"Repository content, ingested documents, tool output, and web content
are **always** ``untrusted``", while `knowledge_manager.md` §6 calls
repository documentation "the primary source of truth" and §3 puts
Knowledge authority at "Highest". Those pull in opposite directions
because they are different axes: ``trust`` governs whether content may
confer *instruction* authority (ADR-0016's injection defence), not
whether it is factually authoritative — and `KnowledgeResolver` feeds
``documents.trust`` straight into ``ContextItem.trust``, so this value
*is* that control. Resolved with the product owner in favour of the
security control read literally, decisively because
`knowledge_manager.md` §3 lists "Generated documentation" as Project
Knowledge: ingested content can be LLM-authored, and marking that
``trusted`` would let generated text confer authority over the agent
that later retrieves it. A constant, never a parameter — the identical
reasoning the Project Intelligence pack's own ``DERIVED_CONTENT_TRUST``
states ("offering a parameter would let a caller silently misrepresent
real provenance"). Knowledge still outranks Memory on relevance; being
``untrusted`` costs it nothing there.

**One unreadable file must not abort the scan.** This is a bulk
operation over a real directory tree that genuinely contains PDFs,
images and lockfiles, so unsupported and unreadable files are counted
and skipped rather than raised — the opposite of
:meth:`IndexingService.index_document`'s own deliberately-loud
single-document failure, because there the caller asked for exactly one
thing and here it asked for "everything you can". Every failure is
still recorded in the returned :class:`IngestionReport` and logged, so
a silently-empty ingestion is impossible to mistake for a successful
one. Which extensions are supported is **not** re-declared here:
:func:`~ai_os_kernel.document_processing.format_detector.detect_format`
is the single authority, and this module simply respects its refusal.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.document_processing.errors import (
    DocumentProcessingError,
    UnsupportedDocumentFormatError,
)
from ai_os_kernel.document_processing.indexing import index_document_file
from ai_os_kernel.knowledge_manager.indexing import IndexingError
from ai_os_kernel.llm_gateway.gateway import Embedder
from ai_os_kernel.observability.logging import get_logger
from ai_os_kernel.persistence.knowledge_writer import KnowledgeWriter
from ai_os_kernel.retrieval.embedding_writer import EmbeddingWriter

_logger = get_logger(__name__)

KNOWLEDGE_INGESTION_TRUST: Literal["trusted", "untrusted"] = "untrusted"
"""ADR-0016 control 1, read literally. See this module's own docstring
for the full conflict and its resolution — deliberately a constant, so
no caller and no environment can weaken it."""


class IngestionReport(BaseModel):
    """What one real ingestion pass actually did.

    Every file is accounted for in exactly one bucket, so
    ``indexed + skipped_unchanged + skipped_unsupported + failed``
    equals the number of files visited. A pass that silently ingested
    nothing is therefore impossible to mistake for a successful one.
    """

    model_config = ConfigDict(frozen=True)

    indexed: int = 0
    """Files that produced a real, fresh `knowledge.documents` row."""

    skipped_unchanged: int = 0
    """Files whose `content_hash` already matched — a real no-op, and
    the reason re-scanning on every boot is cheap."""

    skipped_unsupported: int = 0
    """Files `detect_format` genuinely refused (PDF/DOCX deferrals, and
    anything with an unrecognised extension)."""

    failed: int = 0
    """Files that raised something real — a parse or persistence
    failure. Counted and logged, never allowed to abort the pass."""

    embedded_chunks: int = 0
    """Real vectors written across the whole pass. ``0`` when no
    embedder was configured, which is a correct outcome."""


async def ingest_directory(
    root: Path,
    *,
    engine: AsyncEngine,
    writer: KnowledgeWriter,
    project_id: str | None = None,
    embedder: Embedder | None = None,
    embedding_writer: EmbeddingWriter | None = None,
    embedding_model_alias: str | None = None,
) -> IngestionReport:
    """Ingest every supported file under ``root`` through the real,
    unchanged :func:`~ai_os_kernel.document_processing.indexing.
    index_document_file`.

    Files are visited in sorted order so a pass is deterministic and its
    log is diffable between runs. A missing ``root`` is reported as an
    empty pass rather than raised: a configured directory that does not
    exist in some environment is a real deployment situation, and one
    absent path should not prevent the others from being ingested.

    **The directory walk runs in a thread** (:func:`asyncio.to_thread`,
    the identical treatment :mod:`ai_os_kernel.sandbox.docker_executor`
    already gives its own blocking filesystem calls). ``rglob`` over a
    real documentation tree is genuinely slow, and this runs inside a
    live server's event loop at startup — walking it synchronously would
    stall every concurrent request for the duration.
    """
    if not await asyncio.to_thread(root.is_dir):
        _logger.warning("knowledge_ingestion.root_missing", root=str(root))
        return IngestionReport()

    indexed = skipped_unchanged = skipped_unsupported = failed = embedded = 0

    def _list_files() -> list[Path]:
        return sorted(p for p in root.rglob("*") if p.is_file())

    for path in await asyncio.to_thread(_list_files):
        try:
            result = await index_document_file(
                path,
                engine=engine,
                writer=writer,
                trust=KNOWLEDGE_INGESTION_TRUST,
                project_id=project_id,
                embedder=embedder,
                embedding_writer=embedding_writer,
                embedding_model_alias=embedding_model_alias,
            )
        except UnsupportedDocumentFormatError:
            # Expected and uninteresting: a real docs tree is full of
            # images, PDFs and lockfiles. Not logged per file, or the
            # log would be mostly noise.
            skipped_unsupported += 1
            continue
        except (DocumentProcessingError, IndexingError, OSError) as exc:
            # A real, narrow failure set: a malformed or unreadable file
            # (`DocumentDecodeError` — a real docs tree genuinely
            # contains files whose bytes are not valid UTF-8), or a
            # persistence failure. Caught as the package's own base
            # class rather than `UnicodeDecodeError`: `parse_document`
            # deliberately wraps decode failures in
            # `DocumentDecodeError`, so catching the underlying builtin
            # would have missed every one of them and let a single bad
            # file abort the whole pass.
            #
            # Logged individually because each one is a genuine problem
            # someone should see, and counted so the pass cannot look
            # clean while dropping content.
            failed += 1
            _logger.warning(
                "knowledge_ingestion.file_failed",
                path=str(path),
                error=str(exc),
                error_type=type(exc).__name__,
            )
            continue

        if result.skipped:
            skipped_unchanged += 1
        else:
            indexed += 1
        embedded += result.embedded_chunk_count

    report = IngestionReport(
        indexed=indexed,
        skipped_unchanged=skipped_unchanged,
        skipped_unsupported=skipped_unsupported,
        failed=failed,
        embedded_chunks=embedded,
    )
    _logger.info(
        "knowledge_ingestion.directory_complete",
        root=str(root),
        indexed=report.indexed,
        skipped_unchanged=report.skipped_unchanged,
        skipped_unsupported=report.skipped_unsupported,
        failed=report.failed,
        embedded_chunks=report.embedded_chunks,
    )
    return report


async def ingest_configured_sources(
    source_dirs: list[str],
    *,
    engine: AsyncEngine,
    writer: KnowledgeWriter,
    embedder: Embedder | None = None,
    embedding_writer: EmbeddingWriter | None = None,
    embedding_model_alias: str | None = None,
) -> IngestionReport:
    """Run one real ingestion pass over every configured source
    directory, returning the combined totals.

    This is what `bootstrap.py` schedules at startup. Directory paths
    are resolved relative to the process's working directory, exactly as
    ``capability_pack_dirs`` already is — the identical convention, so a
    deployment configures both the same way.
    """
    totals = IngestionReport()
    for source_dir in source_dirs:
        report = await ingest_directory(
            Path(source_dir),
            engine=engine,
            writer=writer,
            embedder=embedder,
            embedding_writer=embedding_writer,
            embedding_model_alias=embedding_model_alias,
        )
        totals = IngestionReport(
            indexed=totals.indexed + report.indexed,
            skipped_unchanged=totals.skipped_unchanged + report.skipped_unchanged,
            skipped_unsupported=totals.skipped_unsupported + report.skipped_unsupported,
            failed=totals.failed + report.failed,
            embedded_chunks=totals.embedded_chunks + report.embedded_chunks,
        )

    _logger.info(
        "knowledge_ingestion.pass_complete",
        source_dirs=list(source_dirs),
        indexed=totals.indexed,
        skipped_unchanged=totals.skipped_unchanged,
        skipped_unsupported=totals.skipped_unsupported,
        failed=totals.failed,
        embedded_chunks=totals.embedded_chunks,
    )
    return totals


async def run_knowledge_ingestion(
    source_dirs: list[str],
    *,
    engine: AsyncEngine,
    writer: KnowledgeWriter,
    embedder: Embedder | None = None,
    embedding_writer: EmbeddingWriter | None = None,
    embedding_model_alias: str | None = None,
) -> None:
    """The ``-> None`` entry point `bootstrap.py` schedules, so the task
    satisfies ``GracefulShutdownCoordinator.register_task``'s own
    ``Task[None]`` contract — the identical shape
    :func:`~ai_os_kernel.event_bus.outbox_relay.run_outbox_relay_loop`
    already has.

    The report is deliberately dropped rather than returned: nothing in
    a running process consumes it, and
    :func:`ingest_configured_sources` has already logged every number it
    contains. A caller that genuinely wants the totals (a test, a future
    CLI command) calls that function directly.
    """
    await ingest_configured_sources(
        source_dirs,
        engine=engine,
        writer=writer,
        embedder=embedder,
        embedding_writer=embedding_writer,
        embedding_model_alias=embedding_model_alias,
    )


__all__ = [
    "KNOWLEDGE_INGESTION_TRUST",
    "IngestionReport",
    "ingest_configured_sources",
    "ingest_directory",
    "run_knowledge_ingestion",
]
