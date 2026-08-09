"""Unit tests for ``ai_os_cli.config`` — real filesystem reads/writes
to a real, temporary file (never the developer's own real
``~/.config/aios/config.toml``)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_os_cli.config import load_config, save_token


def test_a_missing_config_file_yields_real_defaults(tmp_path: Path) -> None:
    config = load_config(config_path=tmp_path / "config.toml")
    assert config.base_url == "http://localhost:8000"
    assert config.token is None


def test_save_token_then_load_genuinely_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    save_token("real-token-value", config_path=path)

    config = load_config(config_path=path)
    assert config.token == "real-token-value"  # noqa: S105 -- a real value round-tripped, not a secret


def test_save_token_none_genuinely_clears_it(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    save_token("real-token-value", config_path=path)
    save_token(None, config_path=path)

    config = load_config(config_path=path)
    assert config.token is None


def test_an_env_var_always_wins_over_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "config.toml"
    save_token("file-token", config_path=path)
    monkeypatch.setenv("AIOS_TOKEN", "env-token")
    monkeypatch.setenv("AIOS_API_URL", "http://env-host:9999")

    config = load_config(config_path=path)
    assert config.token == "env-token"  # noqa: S105 -- a real value round-tripped, not a secret
    assert config.base_url == "http://env-host:9999"


def test_saving_a_token_preserves_an_existing_base_url_already_on_disk(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('[api]\nbase_url = "http://custom-host:1234"\n', encoding="utf-8")

    save_token("a-token", config_path=path)

    config = load_config(config_path=path)
    assert config.token == "a-token"  # noqa: S105 -- a real value round-tripped, not a secret
    assert config.base_url == "http://custom-host:1234"
