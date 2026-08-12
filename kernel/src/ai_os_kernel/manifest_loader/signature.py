"""Manifest signature verification (FR-117, ``P01-S03-M28-T02``).

Signed manifests were an explicitly accepted gap until 2026-08-12, when
a product-owner decision moved them into v1 scope. Before that decision
no design existed anywhere: neither ``security_architecture.md`` §8 nor
``manifest_schema.md`` ever named a scheme, a trust anchor, or an
enforcement posture — they only recorded the absence. The three choices
below were therefore put to the product owner rather than guessed.

**Scheme: Ed25519 detached signatures.** Asymmetric, so the platform
holds only public keys and a verifying node cannot forge what it can
check — the property an HMAC shared secret cannot give, and the reason
"provenance" is meaningful here at all. It needs no new dependency:
``cryptography`` is already present through ``pyjwt[crypto]``. Sigstore
was considered and rejected — it requires network reachability and OIDC
infrastructure at verify time, contradicting this platform's
deny-by-default egress posture.

**What is signed.** The signature covers
:func:`manifest_signing_digest` — the SHA-256 of the manifest's
canonical JSON, via :func:`~ai_os_kernel.observability.audit.
canonical_json_sha256`, the one hashing primitive this codebase's
tamper-evident writers already share. Deliberately *not* the raw file
bytes: a manifest reformatted, or checked out with different line
endings, is the same manifest, and this repository demonstrably sees
CRLF/LF churn on Windows. Deliberately *not* an in-manifest field
either — that is self-referential (the field must be excluded before
hashing) and would change the schema every existing pack validates
against. The signature therefore lives beside the manifest as
``<manifest>.sig``.

**Trust anchor: a directory of PEM public keys**, its path resolved from
``PlatformConfig.manifest_trust_store_dir`` — the same shape
``capability_pack_dirs`` already establishes. A public key is not a
secret, so anchors are committed and reviewed in git: adding or rotating
a signer is a visible diff, not an environment change. The Secrets
Manager was rejected for exactly that reason — routing public material
through it would emit secret-access audit rows for data that is safe to
publish.

**Honest guarantees, not assumed ones.** This module reports what it
actually established, in the same spirit as
:class:`~ai_os_kernel.sandbox.models.SandboxGuarantees`. It never
collapses "no signature present" into "signature checked and absent",
and never collapses "a signature is present but no trust anchor exists
to check it" into either. :attr:`SignatureStatus.UNVERIFIABLE` exists
precisely so that a deployment with signatures but no configured trust
store cannot silently look like an unsigned one.
"""

from __future__ import annotations

import base64
from enum import StrEnum
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from pydantic import BaseModel, ConfigDict

from ai_os_kernel.observability import get_logger
from ai_os_kernel.observability.audit import canonical_json_sha256

_logger = get_logger(__name__)

# A detached signature sits beside the manifest it covers:
# `manifest.yaml` -> `manifest.yaml.sig`.
SIGNATURE_SUFFIX = ".sig"
# Trust anchors are PEM public keys; the file stem is the key id, so a
# reader of an audit line or a log can tell *which* signer verified.
TRUST_ANCHOR_SUFFIX = ".pub"


class SignatureStatus(StrEnum):
    """What was actually established about a manifest's signature.

    Four values, not two, because collapsing them would be dishonest:
    "unsigned" and "signed but uncheckable here" are genuinely different
    security positions, and a deployment must be able to tell them apart.
    """

    SIGNED_AND_VALID = "signed_and_valid"
    UNSIGNED = "unsigned"
    INVALID = "invalid"
    UNVERIFIABLE = "unverifiable"


class ManifestSignatureResult(BaseModel):
    """The verification outcome for one manifest — always produced, even
    when enforcement is off, so the state of the estate is observable
    before anyone turns enforcement on."""

    model_config = ConfigDict(frozen=True)

    status: SignatureStatus
    key_id: str | None = None
    detail: str

    @property
    def is_trusted(self) -> bool:
        """Only a genuinely verified signature is trusted. Deliberately
        not "not INVALID" — absence of proof is not proof."""
        return self.status is SignatureStatus.SIGNED_AND_VALID


def manifest_signing_digest(manifest: dict[str, Any]) -> str:
    """The exact string a signer must sign for this manifest.

    Published as part of the module's public API so a pack author can
    reproduce it without reading the verifier: sign the UTF-8 bytes of
    this hex digest with an Ed25519 private key, base64-encode the
    resulting 64 signature bytes, and write that to ``<manifest>.sig``.
    """
    return canonical_json_sha256(manifest)


def signature_path_for(manifest_path: Path) -> Path:
    """The detached signature file that would cover ``manifest_path``."""
    return manifest_path.with_name(manifest_path.name + SIGNATURE_SUFFIX)


class ManifestSignatureVerifier:
    """Verifies detached Ed25519 signatures against a trust store.

    Constructed with ``trust_store_dir=None`` (every environment today,
    since the feature is config-gated and off by default) it still runs
    and still reports: a manifest with no signature is honestly
    ``UNSIGNED``, and one *with* a signature is ``UNVERIFIABLE`` rather
    than being waved through.
    """

    def __init__(self, *, trust_store_dir: Path | None = None) -> None:
        self._trust_store_dir = trust_store_dir
        self._anchors: dict[str, Ed25519PublicKey] | None = None

    @property
    def verification_available(self) -> bool:
        """Whether this verifier can actually prove anything — the
        honest-guarantees question, answered rather than assumed."""
        return bool(self._load_anchors())

    def _load_anchors(self) -> dict[str, Ed25519PublicKey]:
        """Load PEM anchors once. A malformed or non-Ed25519 anchor is
        skipped rather than fatal: one bad file in the trust store must
        not disable verification for every other signer."""
        if self._anchors is not None:
            return self._anchors
        anchors: dict[str, Ed25519PublicKey] = {}
        if self._trust_store_dir is not None and self._trust_store_dir.is_dir():
            for pem_path in sorted(self._trust_store_dir.glob(f"*{TRUST_ANCHOR_SUFFIX}")):
                try:
                    key = load_pem_public_key(pem_path.read_bytes())
                except Exception as exc:  # noqa: BLE001 - a bad anchor is unusable, not fatal
                    # Logged, never silent: an operator who mis-formats a
                    # trust anchor must be able to find out why their
                    # signed pack stopped verifying.
                    _logger.error(
                        "manifest_signature.trust_anchor_unreadable",
                        anchor=str(pem_path),
                        error=str(exc),
                    )
                    continue
                if isinstance(key, Ed25519PublicKey):
                    anchors[pem_path.stem] = key
                else:
                    _logger.error(
                        "manifest_signature.trust_anchor_not_ed25519",
                        anchor=str(pem_path),
                        key_type=type(key).__name__,
                    )
        self._anchors = anchors
        return anchors

    def verify(self, manifest_path: Path, manifest: dict[str, Any]) -> ManifestSignatureResult:
        """Establish what is true about ``manifest_path``'s signature."""
        signature_file = signature_path_for(manifest_path)
        if not signature_file.is_file():
            return ManifestSignatureResult(
                status=SignatureStatus.UNSIGNED,
                detail=f"no detached signature found at {signature_file.name}",
            )

        anchors = self._load_anchors()
        if not anchors:
            return ManifestSignatureResult(
                status=SignatureStatus.UNVERIFIABLE,
                detail=(
                    f"{signature_file.name} is present but no Ed25519 trust anchor is "
                    "configured, so the signature could not be checked either way"
                ),
            )

        try:
            signature = base64.b64decode(signature_file.read_text(encoding="utf-8").strip())
        except Exception as exc:  # noqa: BLE001 - malformed input, not a crash
            return ManifestSignatureResult(
                status=SignatureStatus.INVALID,
                detail=f"{signature_file.name} is not valid base64: {exc}",
            )

        message = manifest_signing_digest(manifest).encode("utf-8")
        for key_id, public_key in anchors.items():
            try:
                public_key.verify(signature, message)
            except InvalidSignature:
                continue
            return ManifestSignatureResult(
                status=SignatureStatus.SIGNED_AND_VALID,
                key_id=key_id,
                detail=f"verified against trust anchor '{key_id}'",
            )

        return ManifestSignatureResult(
            status=SignatureStatus.INVALID,
            detail=(
                f"{signature_file.name} did not verify against any of the "
                f"{len(anchors)} configured trust anchor(s): "
                f"{', '.join(sorted(anchors))}"
            ),
        )
