"""Shared, dependency-free helpers a pack might need: id generation,
hashing, canonical JSON, time (``platform_sdk.md`` §3's one-line
description of this directory).

**Deliberately empty beyond this docstring in v1.0.0.** Checked
directly against ``capability_packs/software-engineering/src/`` (the
one real pack) before writing anything here: no agent or pack module
generates its own ULID, hashes its own content, or canonicalises its
own JSON today — the Kernel does all of that internally, and nothing
in the pack reaches for it. Building ``ids.py``/``hashing.py``/
``canonical_json.py`` now, with zero callers, would be exactly the
speculative scaffolding
``docs/21_templates/CODING_STANDARDS_AND_BEST_PRACTICES.md``'s
"Simplicity" principle rules out ("fields exist only once something
reads them").

Revisit this subpackage the moment a real pack need appears — most
likely when a pack starts constructing its own ``ArtifactRef``
(``sha256:<hex>``) or a new correlation id, neither of which any
current agent does.
"""

from __future__ import annotations
