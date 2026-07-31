"""Unit tests for the pure digest/verification logic in
:mod:`ai_os_kernel.configuration_manager.audit` — no database. The
real, Postgres-backed writer proof lives in
``tests/integration/configuration_manager/test_config_change_audit.py``.
"""

from datetime import UTC, datetime

from ai_os_kernel.configuration_manager.audit import (
    ConfigChangeRecord,
    compute_value_digest,
    verify_config_change,
)
from ai_os_kernel.observability.audit import canonical_json_sha256

_WHEN = datetime(2026, 7, 31, 12, 0, 0, tzinfo=UTC)


def _record(
    *, change_id: str = "chg_1", old_value: object, new_value: object
) -> ConfigChangeRecord:
    return ConfigChangeRecord(
        change_id=change_id,
        config_key="some.key",
        old_value_digest=compute_value_digest(old_value),
        new_value_digest=compute_value_digest(new_value),
        changed_by="user-1",
        reason="test change",
        changed_at=_WHEN,
    )


def test_compute_value_digest_of_none_is_none() -> None:
    assert compute_value_digest(None) is None


def test_compute_value_digest_reuses_the_shared_hashing_primitive() -> None:
    """The literal reuse this Task requires: no independent hashing
    implementation, just the same function `audit_log`'s own row_hash
    is built from."""
    assert compute_value_digest("a-value") == canonical_json_sha256("a-value")


def test_compute_value_digest_is_a_real_sha256_hex_digest() -> None:
    digest = compute_value_digest("claude-opus-4-6")
    assert digest is not None
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)


def test_compute_value_digest_never_contains_the_real_value() -> None:
    digest = compute_value_digest("super-secret-value")
    assert digest is not None
    assert "super-secret-value" not in digest


def test_compute_value_digest_is_deterministic() -> None:
    assert compute_value_digest({"a": 1, "b": 2}) == compute_value_digest({"b": 2, "a": 1})


def test_compute_value_digest_differs_for_different_values() -> None:
    assert compute_value_digest("old") != compute_value_digest("new")


def test_verify_config_change_accepts_a_genuine_update() -> None:
    record = _record(old_value="old", new_value="new")
    result = verify_config_change(record, old_value="old", new_value="new")
    assert result.valid is True
    assert result.reason is None


def test_verify_config_change_accepts_a_first_ever_value() -> None:
    record = _record(old_value=None, new_value="first")
    result = verify_config_change(record, old_value=None, new_value="first")
    assert result.valid is True


def test_verify_config_change_accepts_a_key_removal() -> None:
    record = _record(old_value="last", new_value=None)
    result = verify_config_change(record, old_value="last", new_value=None)
    assert result.valid is True


def test_verify_config_change_detects_a_tampered_old_value_digest() -> None:
    record = _record(old_value="old", new_value="new")
    tampered = record.model_copy(update={"old_value_digest": "f" * 64})

    result = verify_config_change(tampered, old_value="old", new_value="new")

    assert result.valid is False
    assert result.reason is not None
    assert "old_value_digest does not match" in result.reason
    assert "chg_1" in result.reason


def test_verify_config_change_detects_a_tampered_new_value_digest() -> None:
    record = _record(old_value="old", new_value="new")
    tampered = record.model_copy(update={"new_value_digest": "f" * 64})

    result = verify_config_change(tampered, old_value="old", new_value="new")

    assert result.valid is False
    assert result.reason is not None
    assert "new_value_digest does not match" in result.reason


def test_verify_config_change_detects_a_value_swap_even_without_touching_any_digest() -> None:
    """The other real property this design gives: since a live value
    was substituted for a different real value, recomputing against
    the (now wrong) supplied value fails, even though nobody touched
    the stored row at all."""
    record = _record(old_value="old", new_value="new")

    result = verify_config_change(record, old_value="old", new_value="a-different-new-value")

    assert result.valid is False
