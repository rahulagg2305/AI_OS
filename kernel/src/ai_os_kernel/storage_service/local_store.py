"""The local-filesystem content-addressed artifact store
(``P02-S07-M21-T01``): stores workflow artifacts by their real
SHA-256 content digest instead of ad hoc temp directories, and returns
the real, already-existing SDK boundary model for "an addressable,
retrievable object" — :class:`ai_os_sdk.models.common.ArtifactRef`
(``sha256:<hex>``, ``platform_sdk.md`` §4.1) — rather than inventing a
second one.

Local-filesystem backend only. A second, S3-compatible "prod" backend
is documented intent (feature_inventory.md §2.18), but no S3 client
dependency, configuration, or real endpoint exists anywhere in this
codebase to build or test against yet — a single concrete class, no
``Protocol``, mirroring
:func:`~ai_os_kernel.persistence.engine.build_engine`/
:func:`~ai_os_kernel.caching.client.build_redis_client`'s own "no
abstraction until a second real implementation exists" shape
(ADR-0004).

Not yet wired into any real caller — no Kernel component constructs
this today; workflow artifacts remain plain files in per-agent
temporary directories, unchanged by this step.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from ai_os_sdk.models.common import ArtifactRef, is_artifact_id

# Two hex characters of real fan-out directory nesting — the same
# "avoid one directory with millions of entries" convention
# content-addressed stores commonly use (e.g. git's own
# `.git/objects/` layout), not an arbitrary depth.
_FANOUT_PREFIX_LENGTH = 2


class LocalFilesystemArtifactStore:
    """The local-FS backend feature_inventory.md §2.18 names for dev.

    Deduplicates identical content: two :meth:`put` calls with the
    same bytes write to the real, identical path exactly once (the
    second call is a genuine no-op write) and return an equal
    :class:`ArtifactRef`. Two calls with different content always
    produce different paths and different ``artifact_id``\\ s — a
    SHA-256 collision is not a real possibility this store needs to
    handle.
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def put(self, content: bytes, *, media_type: str) -> ArtifactRef:
        """Store ``content``, addressed by its own real SHA-256
        digest, and return the real, retrievable reference to it."""
        digest = hashlib.sha256(content).hexdigest()
        path = self._path_for_digest(digest)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        return ArtifactRef(
            artifact_id=f"sha256:{digest}",
            media_type=media_type,
            size_bytes=len(content),
            uri=path.as_uri(),
        )

    def get(self, artifact_id: str) -> bytes | None:
        """The real, originally-stored bytes for ``artifact_id``, or
        ``None`` if nothing has ever been stored under it."""
        if not is_artifact_id(artifact_id):
            raise ValueError(f"not a well-formed artifact id: {artifact_id!r}")

        digest = artifact_id.removeprefix("sha256:")
        path = self._path_for_digest(digest)
        if not path.exists():
            return None
        return path.read_bytes()

    def _path_for_digest(self, digest: str) -> Path:
        return self._root / digest[:_FANOUT_PREFIX_LENGTH] / digest
