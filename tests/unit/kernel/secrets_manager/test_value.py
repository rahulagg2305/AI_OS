"""Unit tests for SecretValue: the wrapper that prevents a resolved
secret from being accidentally logged or serialised (ADR-0024 rule 2)."""

from ai_os_kernel.secrets_manager.value import SecretValue


def test_reveal_returns_the_raw_value() -> None:
    secret = SecretValue("super-secret-token")

    assert secret.reveal() == "super-secret-token"


def test_str_never_leaks_the_raw_value() -> None:
    secret = SecretValue("super-secret-token")

    assert str(secret) == "***"
    assert "super-secret-token" not in str(secret)


def test_repr_never_leaks_the_raw_value() -> None:
    secret = SecretValue("super-secret-token")

    assert "super-secret-token" not in repr(secret)


def test_fstring_interpolation_never_leaks_the_raw_value() -> None:
    secret = SecretValue("super-secret-token")

    assert f"token is {secret}" == "token is ***"
