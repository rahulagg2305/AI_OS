"""``ObservabilitySettings`` — ``OTEL_EXPORTER_OTLP_ENDPOINT`` is a
bootstrap-minimum env var (configuration_management.md §3.3), read
directly, mirroring ``DatabaseSettings``. ``P01-S05-M04-T03``.
"""

from __future__ import annotations

import pytest

from ai_os_kernel.observability.settings import ObservabilitySettings


def test_defaults_to_none_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    assert ObservabilitySettings().otlp_endpoint is None


def test_reads_the_real_standard_otel_env_var_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector.internal:4318")

    assert ObservabilitySettings().otlp_endpoint == "http://collector.internal:4318"
