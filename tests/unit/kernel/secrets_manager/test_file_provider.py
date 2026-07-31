"""Unit tests for FileSecretProvider: the mounted-file backend
(``P01-S02-M19-T03``). Uses pytest's own ``tmp_path`` as the secrets
root throughout — never a real mount point — so these tests cannot read
anything on the host that they did not themselves write.
"""

from pathlib import Path

import pytest

from ai_os_kernel.secrets_manager.errors import SecretResolutionError
from ai_os_kernel.secrets_manager.file_provider import FileSecretProvider


def _root(tmp_path: Path, **files: str) -> Path:
    for name, content in files.items():
        target = tmp_path / name.replace("__", "/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return tmp_path


@pytest.mark.asyncio
async def test_resolves_a_flat_name_to_that_files_contents(tmp_path: Path) -> None:
    provider = FileSecretProvider(root=_root(tmp_path, **{"database-password": "hunter2\n"}))

    secret = await provider.resolve("secret://file/database-password")

    assert secret.reveal() == "hunter2"


@pytest.mark.asyncio
async def test_resolves_a_nested_path_like_name(tmp_path: Path) -> None:
    """ADR-0024's own example name shape is nested
    (``llm/anthropic-api-key``), so a nested mount must work."""
    provider = FileSecretProvider(root=_root(tmp_path, **{"llm__anthropic-api-key": "sk-real\n"}))

    secret = await provider.resolve("secret://file/llm/anthropic-api-key")

    assert secret.reveal() == "sk-real"


@pytest.mark.asyncio
async def test_strips_exactly_one_trailing_newline_and_preserves_the_rest(
    tmp_path: Path,
) -> None:
    """A multi-line secret (a PEM key) must round-trip byte-for-byte
    apart from the single convenience newline."""
    pem = "-----BEGIN KEY-----\nabc\n\ndef\n-----END KEY-----\n"
    provider = FileSecretProvider(root=_root(tmp_path, **{"tls-key": pem}))

    secret = await provider.resolve("secret://file/tls-key")

    assert secret.reveal() == pem.removesuffix("\n")
    assert "\n\n" in secret.reveal()  # interior blank line preserved


@pytest.mark.asyncio
async def test_a_file_with_no_trailing_newline_is_read_verbatim(tmp_path: Path) -> None:
    provider = FileSecretProvider(root=_root(tmp_path, **{"token": "no-newline"}))

    assert (await provider.resolve("secret://file/token")).reveal() == "no-newline"


@pytest.mark.asyncio
async def test_rejects_a_reference_for_another_provider(tmp_path: Path) -> None:
    provider = FileSecretProvider(root=tmp_path)

    with pytest.raises(SecretResolutionError, match="only resolves 'file://' references"):
        await provider.resolve("secret://env/database-password")


@pytest.mark.asyncio
async def test_rejects_a_versioned_reference(tmp_path: Path) -> None:
    """A mounted file has exactly one current value — honouring a
    version silently would be a lie about what was returned."""
    provider = FileSecretProvider(root=_root(tmp_path, **{"token": "v1\n"}))

    with pytest.raises(SecretResolutionError, match="has no versioning"):
        await provider.resolve("secret://file/token#2")


@pytest.mark.asyncio
async def test_reports_a_missing_secret_clearly(tmp_path: Path) -> None:
    provider = FileSecretProvider(root=tmp_path)

    with pytest.raises(SecretResolutionError, match="does not exist"):
        await provider.resolve("secret://file/absent")


@pytest.mark.asyncio
async def test_refuses_to_read_outside_the_configured_root(tmp_path: Path) -> None:
    """The real security property: a traversal-shaped name is refused,
    not sanitised. `outside` genuinely exists and is genuinely readable
    — only the root check prevents it being returned."""
    outside = tmp_path / "outside.txt"
    outside.write_text("host-secret\n", encoding="utf-8")
    root = tmp_path / "mnt"
    root.mkdir()
    provider = FileSecretProvider(root=root)

    with pytest.raises(SecretResolutionError, match="outside the configured secrets root"):
        await provider.resolve("secret://file/../outside.txt")

    assert outside.read_text(encoding="utf-8") == "host-secret\n"


@pytest.mark.asyncio
async def test_reports_an_unreadable_path_without_leaking_contents(tmp_path: Path) -> None:
    """A directory where a file was expected is a real misconfiguration
    (a mount that did not populate); it must fail clearly, not crash."""
    (tmp_path / "as-a-dir").mkdir()
    provider = FileSecretProvider(root=tmp_path)

    with pytest.raises(SecretResolutionError, match="could not be read"):
        await provider.resolve("secret://file/as-a-dir")


@pytest.mark.asyncio
async def test_the_resolved_value_is_still_redacted_on_str(tmp_path: Path) -> None:
    """ADR-0024 rule 2 holds for this backend too, not just `env`."""
    provider = FileSecretProvider(root=_root(tmp_path, **{"token": "super-secret\n"}))

    secret = await provider.resolve("secret://file/token")

    assert str(secret) == "***"
    assert "super-secret" not in repr(secret)
