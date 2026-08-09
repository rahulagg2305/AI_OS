"""Real local CLI configuration (``cli_design.md`` §4: "``~/.config/aios/
config.toml`` plus ``AIOS_*`` environment variables").

An ``AIOS_*`` environment variable always wins over the file — the
identical "env overrides file" layering
:mod:`ai_os_kernel.configuration_manager`'s own precedence chain
already establishes elsewhere in this project, applied here at CLI
scope rather than invented fresh.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

import tomli_w

_DEFAULT_BASE_URL = "http://localhost:8000"


def _config_path() -> Path:
    return Path.home() / ".config" / "aios" / "config.toml"


@dataclass(frozen=True)
class CliConfig:
    """The two real settings this CLI needs: where the Kernel API is,
    and the bearer token to authenticate with. Neither is ever
    fabricated — an absent token means an authenticated command
    genuinely fails with a clear message, not a silently-anonymous
    request."""

    base_url: str
    token: str | None


def _read_config_file(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        return tomllib.load(handle)


def load_config(*, config_path: Path | None = None) -> CliConfig:
    path = config_path if config_path is not None else _config_path()
    data = _read_config_file(path)

    api_section = data.get("api", {})
    auth_section = data.get("auth", {})
    file_base_url = api_section.get("base_url") if isinstance(api_section, dict) else None
    file_token = auth_section.get("token") if isinstance(auth_section, dict) else None

    base_url = os.environ.get("AIOS_API_URL") or file_base_url or _DEFAULT_BASE_URL
    token = os.environ.get("AIOS_TOKEN") or file_token
    return CliConfig(base_url=base_url, token=token)


def save_token(token: str | None, *, config_path: Path | None = None) -> None:
    """Persists (or, when ``token`` is ``None``, clears) the real
    bearer token — ``auth login``/``auth logout``'s own one real
    effect. Preserves any existing ``[api]`` section already on disk
    (e.g. a previously-set ``base_url``) rather than overwriting the
    whole file."""
    path = config_path if config_path is not None else _config_path()
    data = _read_config_file(path)
    if token is None:
        data.pop("auth", None)
    else:
        data["auth"] = {"token": token}

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        tomli_w.dump(data, handle)
