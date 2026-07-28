"""Filesystem-scan pack discovery — the development mechanism (ADR-0009).

Entry-point discovery (the production mechanism, for packs installed
from outside the repository via the ``ai_os.capability_packs`` entry-point
group) is not implemented yet — it requires real installable pack
distributions, which do not exist before Stage B/C.
"""

from collections.abc import Iterator
from pathlib import Path

_MANIFEST_FILENAME = "manifest.yaml"


def discover_manifests(pack_dirs: list[str]) -> Iterator[Path]:
    """Yield the path to each ``manifest.yaml`` found one level under
    each configured pack directory.

    A configured directory that does not exist is skipped, not raised
    on — an unconfigured or not-yet-created ``capability_packs/``
    subtree is not an error at Stage A.
    """
    for pack_dir in pack_dirs:
        root = Path(pack_dir)
        if not root.is_dir():
            continue
        for entry in sorted(root.iterdir()):
            if not entry.is_dir():
                continue
            candidate = entry / _MANIFEST_FILENAME
            if candidate.is_file():
                yield candidate
