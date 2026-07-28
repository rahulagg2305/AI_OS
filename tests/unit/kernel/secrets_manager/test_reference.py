"""Unit tests for parse_secret_reference: the ADR-0024 URI format
(``secret://<provider>/<name>[#<version>]``), pure logic, no I/O."""

import pytest

from ai_os_kernel.secrets_manager.errors import SecretResolutionError
from ai_os_kernel.secrets_manager.reference import parse_secret_reference


def test_parses_a_reference_with_a_nested_path_name() -> None:
    parsed = parse_secret_reference("secret://vault/llm/anthropic-api-key")

    assert parsed.provider == "vault"
    assert parsed.name == "llm/anthropic-api-key"
    assert parsed.version is None


def test_parses_a_reference_with_a_version_fragment() -> None:
    parsed = parse_secret_reference("secret://vault/llm/anthropic-api-key#v2")

    assert parsed.provider == "vault"
    assert parsed.name == "llm/anthropic-api-key"
    assert parsed.version == "v2"


def test_parses_a_reference_with_a_flat_single_segment_name() -> None:
    parsed = parse_secret_reference("secret://env/database-password")

    assert parsed.provider == "env"
    assert parsed.name == "database-password"
    assert parsed.version is None


@pytest.mark.parametrize(
    "reference",
    [
        "",
        "not-a-secret-reference",
        "secret://",
        "secret://vault",
        "secret://vault/",
        "secret:/vault/name",
        "secret://VAULT/name",
        "secret://vault/name#",
        "vault://vault/name",
        "secret://vault/name/",
    ],
)
def test_rejects_a_malformed_reference(reference: str) -> None:
    with pytest.raises(SecretResolutionError, match="not a valid secret reference"):
        parse_secret_reference(reference)
