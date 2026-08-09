"""Real provenance tagging for every real Tool output this pack
produces (`P05-S02-M32-T06`, FR-059: "Tag every derived item untrusted
through the whole pipeline").

**Mirrors ADR-0016's own control 1** ("Every context item carries
`trusted` or `untrusted`... Repository content, ingested documents,
tool output, and web content are always `untrusted`") **and the
Context Manager's own already-real `ContextItem.trust` field**
(`ai_os_kernel.context_manager.models`) — independently defined here,
not imported, since this pack cannot import `ai_os_kernel` at all. The
identical "two distinct types, independently mirroring the same real
shape" precedent `ai_os_sdk.models.tool.TrustTier` already establishes
for the analogous Kernel/SDK boundary (that module's own docstring:
"this SDK... cannot import the Kernel's equivalent enum... both enums
independently mirror the same [authoritative artifact], which is what
keeps them in agreement").

**Always `"untrusted"`, structurally, not a caller-configurable
parameter.** Every real Tool in this pack (`repository.ingest`,
`language.detect`, `dependency.graph`) derives its entire output from
ingested repository content — there is no code path here that could
honestly produce `"trusted"` output. Offering a parameter would let a
caller silently misrepresent real provenance; this constant is the
only value any real caller can ever receive.

**Applied once per Tool call, not per nested item.** Every item inside
one real Tool's own output (each file entry, each language/build-system
/framework finding, each graph node/edge) originates from the exact
same one ingested source in the exact same one call — there is no real
scenario where two items in the same response would ever carry a
different trust level. A single, top-level `trust` field per response
is the real, honest granularity this pack's own current design
actually has (no per-item provenance chain exists, or is needed, since
nothing here ever mixes sources within one call).
"""

from __future__ import annotations

from typing import Literal

Trust = Literal["trusted", "untrusted"]

DERIVED_CONTENT_TRUST: Trust = "untrusted"

__all__ = ["DERIVED_CONTENT_TRUST", "Trust"]
