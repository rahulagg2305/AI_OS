"""Real proof of manifest signature verification (FR-117,
``P01-S03-M28-T02``).

Every key here is generated inside the test at runtime. **No private key
is ever committed to this repository**, which is the whole point of
choosing an asymmetric scheme: the platform only ever needs the public
half, and the public half is the only thing that could safely live in
git.

The signatures are produced with the real ``cryptography`` Ed25519
implementation and verified through the real
:class:`~ai_os_kernel.manifest_loader.signature.ManifestSignatureVerifier`
— nothing here fakes the crypto, so a test that passes means a real
signature really verified.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pytest
import yaml
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from ai_os_kernel.manifest_loader.signature import (
    ManifestSignatureVerifier,
    SignatureStatus,
    manifest_signing_digest,
    signature_path_for,
)

_MANIFEST: dict[str, Any] = {
    "apiVersion": "v1",
    "kind": "CapabilityPack",
    "metadata": {"id": "se.example", "name": "Example", "version": "1.0.0"},
}


def _write_manifest(directory: Path, payload: dict[str, Any] | None = None) -> Path:
    manifest_path = directory / "manifest.yaml"
    manifest_path.write_text(yaml.safe_dump(payload or _MANIFEST), encoding="utf-8")
    return manifest_path


def _trust_store_with(directory: Path, private_key: Ed25519PrivateKey, key_id: str) -> Path:
    """Write only the PUBLIC half into a real trust store directory."""
    directory.mkdir(parents=True, exist_ok=True)
    pem = private_key.public_key().public_bytes(
        encoding=Encoding.PEM, format=PublicFormat.SubjectPublicKeyInfo
    )
    (directory / f"{key_id}.pub").write_bytes(pem)
    return directory


def _sign(manifest_path: Path, manifest: dict[str, Any], key: Ed25519PrivateKey) -> Path:
    """Produce a real detached signature exactly as a pack author would,
    following `manifest_signing_digest`'s own published recipe."""
    signature = key.sign(manifest_signing_digest(manifest).encode("utf-8"))
    sig_path = signature_path_for(manifest_path)
    sig_path.write_text(base64.b64encode(signature).decode("ascii"), encoding="utf-8")
    return sig_path


def test_a_real_signature_verifies_against_a_real_trust_anchor(tmp_path: Path) -> None:
    key = Ed25519PrivateKey.generate()
    manifest_path = _write_manifest(tmp_path)
    _sign(manifest_path, _MANIFEST, key)
    store = _trust_store_with(tmp_path / "trust", key, "aios-platform")

    result = ManifestSignatureVerifier(trust_store_dir=store).verify(manifest_path, _MANIFEST)

    assert result.status is SignatureStatus.SIGNED_AND_VALID
    assert result.is_trusted
    # The specific signer is named, not merely "valid" — an operator
    # reading a log must be able to tell *which* anchor vouched for it.
    assert result.key_id == "aios-platform"


def test_a_tampered_manifest_no_longer_verifies(tmp_path: Path) -> None:
    """The property that makes signing worth anything: sign the real
    manifest, then change one byte of meaning, and the signature must
    stop verifying."""
    key = Ed25519PrivateKey.generate()
    manifest_path = _write_manifest(tmp_path)
    _sign(manifest_path, _MANIFEST, key)
    store = _trust_store_with(tmp_path / "trust", key, "aios-platform")

    tampered = {**_MANIFEST, "metadata": {**_MANIFEST["metadata"], "id": "evil.pack"}}
    result = ManifestSignatureVerifier(trust_store_dir=store).verify(manifest_path, tampered)

    assert result.status is SignatureStatus.INVALID
    assert not result.is_trusted


def test_a_signature_from_an_untrusted_key_is_refused(tmp_path: Path) -> None:
    """A real, well-formed Ed25519 signature is still refused when its
    key is not in the trust store — trust is the anchor, not the maths."""
    trusted, attacker = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    manifest_path = _write_manifest(tmp_path)
    _sign(manifest_path, _MANIFEST, attacker)
    store = _trust_store_with(tmp_path / "trust", trusted, "aios-platform")

    result = ManifestSignatureVerifier(trust_store_dir=store).verify(manifest_path, _MANIFEST)

    assert result.status is SignatureStatus.INVALID
    assert "aios-platform" in result.detail


def test_an_unsigned_manifest_reports_unsigned_not_invalid(tmp_path: Path) -> None:
    """Zero-regression shape: the three real packs are unsigned today.
    They must report honestly as `unsigned`, never as a failure."""
    key = Ed25519PrivateKey.generate()
    manifest_path = _write_manifest(tmp_path)
    store = _trust_store_with(tmp_path / "trust", key, "aios-platform")

    result = ManifestSignatureVerifier(trust_store_dir=store).verify(manifest_path, _MANIFEST)

    assert result.status is SignatureStatus.UNSIGNED
    assert not result.is_trusted


def test_a_signature_with_no_trust_anchor_is_unverifiable_not_unsigned(tmp_path: Path) -> None:
    """The honest-guarantees case, and the reason `UNVERIFIABLE` exists.

    A deployment that *has* signatures but has configured no trust store
    has established nothing. Reporting that as `unsigned` would be a
    lie by collapse — it would look identical to a pack that never had a
    signature at all.
    """
    key = Ed25519PrivateKey.generate()
    manifest_path = _write_manifest(tmp_path)
    _sign(manifest_path, _MANIFEST, key)

    result = ManifestSignatureVerifier(trust_store_dir=None).verify(manifest_path, _MANIFEST)

    assert result.status is SignatureStatus.UNVERIFIABLE
    assert not result.is_trusted


def test_verification_availability_is_reported_not_assumed(tmp_path: Path) -> None:
    key = Ed25519PrivateKey.generate()
    assert ManifestSignatureVerifier(trust_store_dir=None).verification_available is False
    store = _trust_store_with(tmp_path / "trust", key, "aios-platform")
    assert ManifestSignatureVerifier(trust_store_dir=store).verification_available is True


def test_one_malformed_trust_anchor_does_not_disable_the_others(tmp_path: Path) -> None:
    """One unreadable file in the trust store must not silently take
    every other signer offline with it."""
    key = Ed25519PrivateKey.generate()
    manifest_path = _write_manifest(tmp_path)
    _sign(manifest_path, _MANIFEST, key)
    store = _trust_store_with(tmp_path / "trust", key, "aios-platform")
    (store / "broken.pub").write_text("not a PEM key at all", encoding="utf-8")

    result = ManifestSignatureVerifier(trust_store_dir=store).verify(manifest_path, _MANIFEST)

    assert result.status is SignatureStatus.SIGNED_AND_VALID
    assert result.key_id == "aios-platform"


def test_a_malformed_signature_file_is_invalid_never_a_crash(tmp_path: Path) -> None:
    key = Ed25519PrivateKey.generate()
    manifest_path = _write_manifest(tmp_path)
    signature_path_for(manifest_path).write_text("!!! not base64 !!!", encoding="utf-8")
    store = _trust_store_with(tmp_path / "trust", key, "aios-platform")

    result = ManifestSignatureVerifier(trust_store_dir=store).verify(manifest_path, _MANIFEST)

    assert result.status is SignatureStatus.INVALID


def test_the_digest_is_stable_across_key_order_and_formatting(tmp_path: Path) -> None:
    """Why the signature covers canonical JSON, not raw file bytes: the
    same manifest written differently is the same manifest. This is what
    makes a signature survive a reformat, or a checkout with different
    line endings — real churn this repository sees on Windows.
    """
    reordered: dict[str, Any] = {
        "metadata": {"version": "1.0.0", "name": "Example", "id": "se.example"},
        "kind": "CapabilityPack",
        "apiVersion": "v1",
    }
    assert manifest_signing_digest(_MANIFEST) == manifest_signing_digest(reordered)

    key = Ed25519PrivateKey.generate()
    manifest_path = _write_manifest(tmp_path)
    _sign(manifest_path, _MANIFEST, key)
    store = _trust_store_with(tmp_path / "trust", key, "aios-platform")

    # Signed against one ordering, verified against the other.
    result = ManifestSignatureVerifier(trust_store_dir=store).verify(manifest_path, reordered)
    assert result.status is SignatureStatus.SIGNED_AND_VALID


@pytest.mark.parametrize(
    "status",
    [SignatureStatus.UNSIGNED, SignatureStatus.INVALID, SignatureStatus.UNVERIFIABLE],
)
def test_only_a_verified_signature_is_trusted(status: SignatureStatus) -> None:
    """`is_trusted` is deliberately not "did not fail" — absence of
    proof is not proof, which is why enforcement refuses `unverifiable`
    as firmly as it refuses `invalid`."""
    from ai_os_kernel.manifest_loader.signature import ManifestSignatureResult

    assert ManifestSignatureResult(status=status, detail="x").is_trusted is False
