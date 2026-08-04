"""``RedisSettings`` — ``AIOS_REDIS_URL`` is a bootstrap-minimum env
var (configuration_management.md §3.3), read directly, mirroring
``DatabaseSettings``/``ObservabilitySettings``. ``P02-S07-M23-T01``.
"""

from __future__ import annotations

import pytest

from ai_os_kernel.caching.settings import RedisSettings


def test_defaults_to_none_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AIOS_REDIS_URL", raising=False)

    assert RedisSettings().redis_url is None


def test_reads_the_real_documented_env_var_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIOS_REDIS_URL", "redis://localhost:6379/0")

    assert RedisSettings().redis_url == "redis://localhost:6379/0"
