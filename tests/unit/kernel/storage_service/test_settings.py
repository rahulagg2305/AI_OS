"""``StorageSettings`` — ``AIOS_STORAGE_ROOT`` mirrors
``RedisSettings``/``DatabaseSettings``'s own bootstrap-minimum,
directly-read-from-environment shape. ``P02-S07-M21-T01``.
"""

from __future__ import annotations

import pytest

from ai_os_kernel.storage_service.settings import DEFAULT_STORAGE_ROOT, StorageSettings


def test_defaults_to_the_real_documented_default_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AIOS_STORAGE_ROOT", raising=False)

    assert StorageSettings().storage_root == DEFAULT_STORAGE_ROOT


def test_reads_the_real_documented_env_var_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIOS_STORAGE_ROOT", "/var/lib/aios/artifacts")

    assert StorageSettings().storage_root == "/var/lib/aios/artifacts"
