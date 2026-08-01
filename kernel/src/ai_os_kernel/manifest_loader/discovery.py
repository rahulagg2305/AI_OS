"""Pack discovery — both ADR-0009 mechanisms.

**Filesystem scan** (the development mechanism): configured directories
are scanned for ``manifest.yaml``, one level down.

**Entry-point discovery** (the production mechanism, ``P01-S03-M02-T03``):
installed distributions register under the ``ai_os.capability_packs``
entry-point group. "The entry point only says where the pack is"
(ADR-0009 §"Decision") — resolved here through the *distribution* an
entry point is registered against, via its own recorded file list, to
locate that distribution's ``manifest.yaml``. **This never calls
:meth:`~importlib.metadata.EntryPoint.load` on the entry point itself**
— doing so would import and execute the pack's own Python module,
directly violating manifest_loader.md §6: "The loader itself must not
execute domain logic from the pack." Only distribution *metadata* is
read, never pack code.
"""

from collections.abc import Iterator
from importlib import metadata
from pathlib import Path

_MANIFEST_FILENAME = "manifest.yaml"

ENTRY_POINT_GROUP = "ai_os.capability_packs"
"""ADR-0009's decided entry-point group name — the one place this
string is spelled, so a caller (:class:`~ai_os_kernel.manifest_loader.
loader.ManifestLoader`, a test) never has to repeat it."""


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


def discover_entry_point_manifests(*, group: str = ENTRY_POINT_GROUP) -> Iterator[Path]:
    """Yield the path to each installed pack's ``manifest.yaml``, found
    via the ``group`` entry-point group — no filesystem scan involved,
    and no pack directory needs to be configured for this to work
    (ADR-0009's production mechanism, for a pack installed from outside
    this repository).

    An entry point whose distribution cannot be resolved, or whose
    distribution's own file list does not include ``manifest.yaml``, is
    skipped — the identical "not found here" shape
    :func:`discover_manifests` already returns for a directory with no
    ``manifest.yaml``. Discovery only ever reports candidates it can
    find; validation and failure reporting happen uniformly downstream
    in :class:`~ai_os_kernel.manifest_loader.loader.ManifestLoader`,
    exactly as ADR-0009 requires both mechanisms to be "validated
    identically."
    """
    for entry_point in metadata.entry_points(group=group):
        dist = entry_point.dist
        if dist is None or dist.files is None:
            continue
        manifest_files = [f for f in dist.files if f.name == _MANIFEST_FILENAME]
        if not manifest_files:
            continue
        yield Path(str(dist.locate_file(manifest_files[0])))
