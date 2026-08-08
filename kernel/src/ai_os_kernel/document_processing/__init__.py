"""Document Processing — parser adapters (`P05-S01-M26-T01`, FR-Stage E:
"Parse real document formats into text").

**Scoped to this ticket's own literal Goal/Input/Output, not
`document_processing.md`'s full framework document** (Format Detector,
5 Parser Adapters, Structure Extractor, Chunking Engine, Metadata
Enricher, Output Normalizer, Observability Hook): real format detection
plus 3 real, dependency-free parser adapters (Markdown, Plain Text,
Code-aware) — a disclosed, deliberate departure, matching this
project's established "build the real, buildable subset" precedent
(design fork resolved via `AskUserQuestion`).

**Two real, deliberate departures from `document_processing.md`'s own
full design:**

1. **Built inside the Kernel** (`ai_os_kernel.document_processing`), not
   the `platform_services/document_processing` package that document's
   own module path implies. `platform_services/` remains undocumented
   as a real `uv` workspace member (no tracked content at all) — the
   identical, already-established fork this project resolved for the
   Notification Service (`notification_service.md`'s own Implementation
   Status carries the full reasoning, unchanged here).
2. **PDF and DOCX/Office parsing are not built.** Both need a real,
   new third-party dependency (`pypdf`, `python-docx` or equivalent) —
   this project currently declares none. Markdown, Plain Text, and
   Code-aware are all genuinely parseable with zero new dependencies
   (pure text formats), so this step builds exactly those three and
   raises a clear, typed :class:`~ai_os_kernel.document_processing.
   errors.UnsupportedDocumentFormatError` naming PDF/DOCX specifically
   as deferred, rather than silently mis-detecting or crashing on them.
   Adding the two binary-format libraries is real, separate, later work
   once a caller genuinely needs them.

Chunking (`document_processing.md` §4's own "Chunking Engine" box) is
explicitly out of scope here — `P05-S01-M26-T02` (Chunking pipeline)
is its own, already-declared, dependent ticket.
"""
