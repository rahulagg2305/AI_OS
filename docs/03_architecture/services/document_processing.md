# Document Processing Service – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Document Processing Service  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## Implementation Status (updated 2026-08-09, `P05-S01-M26-T01`)

**Built: real format detection plus 3 of 5 documented parser adapters.** `ai_os_kernel.document_processing` (built inside the Kernel, not the `platform_services/document_processing` package this document's own module path implies — `platform_services/` still has no tracked content at all and is not a real `uv` workspace member, the identical fork already resolved for the Notification Service) genuinely parses Markdown (ATX headings extracted), Plain Text, and Code (language inferred from extension) files: `service.parse_document(path)` detects format, computes a real `sha256:<hex>` provenance hash from the file's own raw bytes, decodes and normalizes line endings (`\r\n`/`\r` → `\n` — "produce consistent, machine-usable representations," §2), and dispatches to the matching real `DocumentParser` (ADR-0004 Protocol). Proven by 27 real tests (`tests/unit/kernel/document_processing/`) — real files on real disk, no fakes needed (nothing here has I/O or non-determinism worth substituting).

**Two of the five documented parser adapters are not built, disclosed rather than silently assumed:** PDF and DOCX/Office both need a real, new third-party dependency (`pypdf`, `python-docx` or equivalent) this project does not yet declare — a deliberate scope decision (design fork resolved via `AskUserQuestion`), not an oversight. `detect_format()` raises a clear, typed `UnsupportedDocumentFormatError` naming PDF/DOCX specifically as deferred, rather than mis-detecting or crashing on them. **Re-examined and formally deferred again on 2026-08-13 (product-owner decision), now on a concrete ground rather than general caution:** an `ast`-based sweep confirmed this package has **zero production importers** (risk register R-018 item 7, now machine-checked by `tests/contract/test_production_reachability.py`), so adding two supply-chain dependencies would extend the platform's licence and vulnerability surface for code no running process can reach. Routing extraction through the existing Docker sandbox was considered and declined as far larger than an adapter — it needs an image, an I/O contract, and would make parsing depend on Docker being available. `DocumentParser` remains a Protocol precisely so an adapter slots in unchanged; **revisit when a real ingestion caller exists**, at which point the dependency buys something reachable. Also not built: the Structure Extractor/Metadata Enricher/Output Normalizer/Observability Hook boxes beyond what each parser's own `metadata` dict already reports.

**Updated 2026-08-09 (`P05-S01-M26-T02`): the Chunking Engine box is real — reused, not duplicated.** Investigation found `ai_os_kernel.knowledge_manager.indexing`'s own `chunk_content()`/`IndexingService` (built earlier at `P02-S04-M09-T03`, module 9) already implements real, tested, versioned fixed-size chunking feeding `SqlKnowledgeWriter` — but had zero real production callers anywhere. Rather than build a second, parallel chunker (this project's own repeated "no parallel mechanism" discipline), `ai_os_kernel.document_processing.indexing.index_document_file()` is new, real glue: it parses a file via this package's own `parse_document()`, maps its format to a real MIME-style `media_type`, and calls the existing, unchanged `IndexingService` — becoming its first real production caller. Proven by 4 real Postgres-backed tests: a real multi-chunk Markdown write, a code file indexed with a `text/x-source` media type, an unchanged re-index genuinely skipped (the existing archive-and-replace policy, reused as-is), and a deferred PDF refused before any write. The one adjacent real component, `kernel/src/ai_os_kernel/persistence/knowledge_writer.py`, is now reachable from a real document on disk end to end. Its main intended consumer, the Project Intelligence pack, is still 0% built.

Authoritative, always-current status: the per-module completion table in `feature_inventory.md`; build history in `history/INDEX.md` (all under `docs/19_roadmap/`).

## 1. Purpose

This document defines the design of the **Document Processing Service**, a shared Platform Service in AI_OS.

The Document Processing Service is responsible for ingesting, parsing, normalising, and extracting structured information from documents (specifications, requirements, code-related docs, PDFs, Markdown, etc.) so that the rest of the platform can use them reliably.

This document is subordinate to:

1. Project Constitution  
2. System Architecture  
3. Kernel Architecture  
4. Knowledge Manager Design  
5. Context Manager Design  

---

## 2. Design Goals

The Document Processing Service must:

- Support common document formats used in software engineering
- Extract clean text and structure (headings, sections, tables, code blocks, etc.)
- Produce consistent, machine-usable representations
- Integrate with the Knowledge Manager and indexing pipelines
- Be extensible for new formats
- Be observable and robust to imperfect input

---

## 3. Core Responsibilities

- Accept documents from various sources (uploads, repositories, storage)
- Detect format and apply appropriate parsers
- Extract text, structure, and metadata
- Normalise content for downstream use
- Chunk content when required for indexing or context assembly
- Hand off processed content to Knowledge Manager / Search indexing
- Report processing status and errors

---

## 4. High-Level Structure

```text
Document Processing Service
│
├── Format Detector
├── Parser Adapters
│     ├── Markdown Parser
│     ├── Plain Text Parser
│     ├── PDF Parser
│     ├── DOCX / Office Parser (optional)
│     └── Code-aware Parser
├── Structure Extractor
├── Chunking Engine
├── Metadata Enricher
├── Output Normalizer
└── Observability Hook
```

---

## 5. Key Design Rules

- Prefer lossless extraction of useful structure over aggressive interpretation.
- Preserve provenance (original file, hash, source location).
- Chunking strategies should be configurable and suitable for both search and LLM context windows.
- The service should not invent content; it only extracts and structures what is present.
- Capability Packs should use this service rather than implementing their own ad-hoc parsers when possible.

---

## 6. Relationship with Other Components

- **Knowledge Manager** receives processed documents for long-term storage and retrieval.
- **Search & Vector Search** indexes the processed and chunked content.
- **Context Manager** uses the resulting structured content when assembling context.
- **Storage Service** holds the original and processed artifacts.
- **Workflow Engine** and Agents may trigger document processing as part of analysis or ingestion workflows.
- **Project Intelligence Pack** is a major consumer when analysing existing systems.

---

## 7. Observability Requirements

Document processing operations should record:

- Document ID / source
- Format detected
- Processing duration
- Success / failure and error details
- Number of chunks or extracted elements produced
- Correlation with Workflow ID / Trace ID when applicable

---

## 8. Current Status

This document defines the design baseline for the Document Processing Service.

Concrete parser implementations, chunking strategies, and supported format priorities will be refined during implementation.

---

## 9. Final Authority

Order of precedence:

1. Project Constitution  
2. System Architecture  
3. Kernel Architecture  
4. Document Processing Service  
5. Source Code
