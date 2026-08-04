"""Real proof of :class:`LocalFilesystemArtifactStore` against a real
filesystem (``tmp_path`` — a genuine OS directory, not an in-memory
stand-in): identical content deduplicates to the same address and
writes to disk exactly once; different content produces different
addresses; a round trip returns the exact original bytes; a miss and
a malformed id are both handled honestly.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

import pytest

from ai_os_kernel.storage_service.local_store import LocalFilesystemArtifactStore


def _all_real_files(root: Path) -> list[Path]:
    return [path for path in root.rglob("*") if path.is_file()]


def test_identical_content_deduplicates_to_the_same_address(tmp_path: Path) -> None:
    store = LocalFilesystemArtifactStore(tmp_path)
    content = b"the exact same bytes, twice"

    first = store.put(content, media_type="text/plain")
    second = store.put(content, media_type="text/plain")

    assert first.artifact_id == second.artifact_id
    assert first.uri == second.uri
    assert len(_all_real_files(tmp_path)) == 1


def test_different_content_produces_different_addresses(tmp_path: Path) -> None:
    store = LocalFilesystemArtifactStore(tmp_path)

    first = store.put(b"content A", media_type="text/plain")
    second = store.put(b"content B", media_type="text/plain")

    assert first.artifact_id != second.artifact_id
    assert len(_all_real_files(tmp_path)) == 2


def test_the_returned_artifact_id_is_the_real_sha256_of_the_content(tmp_path: Path) -> None:
    store = LocalFilesystemArtifactStore(tmp_path)
    content = b"hash me for real"

    ref = store.put(content, media_type="text/plain")

    assert ref.artifact_id == f"sha256:{hashlib.sha256(content).hexdigest()}"


def test_put_then_get_returns_the_exact_original_bytes(tmp_path: Path) -> None:
    store = LocalFilesystemArtifactStore(tmp_path)
    content = b"round trip this exact content"

    ref = store.put(content, media_type="application/octet-stream")

    assert store.get(ref.artifact_id) == content


def test_the_content_is_genuinely_on_disk_at_the_returned_uri(tmp_path: Path) -> None:
    store = LocalFilesystemArtifactStore(tmp_path)
    content = b"genuinely persisted, not just claimed"

    ref = store.put(content, media_type="text/plain")

    real_path = Path(url2pathname(urlparse(ref.uri).path))
    assert real_path.is_file()
    assert real_path.read_bytes() == content


def test_get_of_an_unknown_id_returns_none(tmp_path: Path) -> None:
    store = LocalFilesystemArtifactStore(tmp_path)

    unknown_id = "sha256:" + "0" * 64
    assert store.get(unknown_id) is None


def test_get_rejects_a_malformed_artifact_id(tmp_path: Path) -> None:
    store = LocalFilesystemArtifactStore(tmp_path)

    with pytest.raises(ValueError, match="not a well-formed artifact id"):
        store.get("not-a-real-artifact-id")


def test_size_bytes_reflects_the_real_content_length(tmp_path: Path) -> None:
    store = LocalFilesystemArtifactStore(tmp_path)
    content = b"twelve bytes"

    ref = store.put(content, media_type="text/plain")

    assert ref.size_bytes == len(content) == 12


def test_an_empty_artifact_is_real_and_addressable(tmp_path: Path) -> None:
    store = LocalFilesystemArtifactStore(tmp_path)

    ref = store.put(b"", media_type="text/plain")

    assert ref.size_bytes == 0
    assert store.get(ref.artifact_id) == b""
