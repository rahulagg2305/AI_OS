"""Unit tests for the Configuration Manager (layers 1, 2, 3, 4, 5)."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from ai_os_kernel.configuration_manager import (
    ConfigurationError,
    ConfigurationManager,
    extract_pack_defaults,
)


def _write_yaml(path: Path, content: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(content), encoding="utf-8")


def test_built_in_defaults_apply_when_no_config_files_exist(tmp_path: Path) -> None:
    manager = ConfigurationManager(
        environment="local",
        platform_config_path=tmp_path / "platform.yaml",
        environments_dir=tmp_path / "environments",
    )

    config = manager.load(role="api")

    assert config.env == "local"
    assert config.role == "api"
    assert config.log_level == "INFO"
    assert config.host == "127.0.0.1"


def test_platform_config_overrides_built_in_defaults(tmp_path: Path) -> None:
    _write_yaml(tmp_path / "platform.yaml", {"kernel": {"log_level": "WARNING"}})
    manager = ConfigurationManager(
        environment="local",
        platform_config_path=tmp_path / "platform.yaml",
        environments_dir=tmp_path / "environments",
    )

    config = manager.load(role="api")

    assert config.log_level == "WARNING"


def test_environment_config_overrides_platform_config(tmp_path: Path) -> None:
    _write_yaml(tmp_path / "platform.yaml", {"kernel": {"log_level": "WARNING"}})
    _write_yaml(tmp_path / "environments" / "local.yaml", {"kernel": {"log_level": "DEBUG"}})
    manager = ConfigurationManager(
        environment="local",
        platform_config_path=tmp_path / "platform.yaml",
        environments_dir=tmp_path / "environments",
    )

    config = manager.load(role="api")

    assert config.log_level == "DEBUG"


def test_env_and_role_are_always_the_caller_supplied_values(tmp_path: Path) -> None:
    # Even if a config file tries to set them, env/role come only from
    # the caller — they are bootstrap identity, never file-driven.
    _write_yaml(tmp_path / "platform.yaml", {"kernel": {"env": "production", "role": "worker"}})
    manager = ConfigurationManager(
        environment="local",
        platform_config_path=tmp_path / "platform.yaml",
        environments_dir=tmp_path / "environments",
    )

    config = manager.load(role="api")

    assert config.env == "local"
    assert config.role == "api"


def test_missing_config_files_are_not_an_error(tmp_path: Path) -> None:
    manager = ConfigurationManager(
        environment="dev",
        platform_config_path=tmp_path / "does-not-exist.yaml",
        environments_dir=tmp_path / "also-does-not-exist",
    )

    config = manager.load(role="worker")

    assert config.env == "dev"


def test_unknown_environment_fails_clearly_at_construction(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError):
        ConfigurationManager(
            environment="not-a-real-environment",
            platform_config_path=tmp_path / "platform.yaml",
            environments_dir=tmp_path / "environments",
        )


def test_non_mapping_yaml_document_fails_clearly(tmp_path: Path) -> None:
    (tmp_path / "platform.yaml").write_text("- just\n- a\n- list\n", encoding="utf-8")
    manager = ConfigurationManager(
        environment="local",
        platform_config_path=tmp_path / "platform.yaml",
        environments_dir=tmp_path / "environments",
    )

    with pytest.raises(ConfigurationError):
        manager.load(role="api")


def test_invalid_field_value_fails_clearly(tmp_path: Path) -> None:
    _write_yaml(tmp_path / "platform.yaml", {"kernel": {"port": "not-a-number"}})
    manager = ConfigurationManager(
        environment="local",
        platform_config_path=tmp_path / "platform.yaml",
        environments_dir=tmp_path / "environments",
    )

    with pytest.raises(ConfigurationError):
        manager.load(role="api")


def test_the_committed_platform_and_local_environment_config_are_valid() -> None:
    """Regression test on the real, shipped configuration files."""
    manager = ConfigurationManager(
        environment="local",
        platform_config_path=Path("config/platform.yaml"),
        environments_dir=Path("infra/environments"),
    )

    config = manager.load(role="api")

    assert config.env == "local"
    assert config.role == "api"
    assert config.log_level == "DEBUG"  # local.yaml overrides platform.yaml's INFO


@pytest.mark.parametrize("environment", ["dev", "staging", "production"])
def test_every_committed_environment_file_is_valid(environment: str) -> None:
    manager = ConfigurationManager(
        environment=environment,
        platform_config_path=Path("config/platform.yaml"),
        environments_dir=Path("infra/environments"),
    )

    config = manager.load(role="api")

    assert config.env == environment


def _pack_manifest(*, config_schema_properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "metadata": {"id": "some-pack"},
        "configSchema": {"type": "object", "properties": config_schema_properties},
    }


def test_extract_pack_defaults_pulls_the_declared_default_out_of_config_schema() -> None:
    manifest = _pack_manifest(
        config_schema_properties={"log_level": {"type": "string", "default": "DEBUG"}}
    )

    assert extract_pack_defaults(manifest) == {"log_level": "DEBUG"}


def test_extract_pack_defaults_ignores_properties_with_no_default() -> None:
    manifest = _pack_manifest(config_schema_properties={"log_level": {"type": "string"}})

    assert extract_pack_defaults(manifest) == {}


def test_extract_pack_defaults_is_empty_for_a_manifest_with_no_config_schema() -> None:
    assert extract_pack_defaults({"metadata": {"id": "some-pack"}}) == {}


def test_a_pack_default_is_honored_when_nothing_overrides_it(tmp_path: Path) -> None:
    manager = ConfigurationManager(
        environment="local",
        platform_config_path=tmp_path / "platform.yaml",
        environments_dir=tmp_path / "environments",
    )
    pack = _pack_manifest(
        config_schema_properties={"log_level": {"type": "string", "default": "DEBUG"}}
    )

    config = manager.load(role="api", pack_manifests=[pack])

    assert config.log_level == "DEBUG"


def test_platform_config_overrides_a_pack_default(tmp_path: Path) -> None:
    _write_yaml(tmp_path / "platform.yaml", {"kernel": {"log_level": "WARNING"}})
    manager = ConfigurationManager(
        environment="local",
        platform_config_path=tmp_path / "platform.yaml",
        environments_dir=tmp_path / "environments",
    )
    pack = _pack_manifest(
        config_schema_properties={"log_level": {"type": "string", "default": "DEBUG"}}
    )

    config = manager.load(role="api", pack_manifests=[pack])

    assert config.log_level == "WARNING"


def test_environment_config_overrides_a_pack_default(tmp_path: Path) -> None:
    _write_yaml(tmp_path / "environments" / "local.yaml", {"kernel": {"log_level": "ERROR"}})
    manager = ConfigurationManager(
        environment="local",
        platform_config_path=tmp_path / "platform.yaml",
        environments_dir=tmp_path / "environments",
    )
    pack = _pack_manifest(
        config_schema_properties={"log_level": {"type": "string", "default": "DEBUG"}}
    )

    config = manager.load(role="api", pack_manifests=[pack])

    assert config.log_level == "ERROR"


def test_a_later_pack_overrides_an_earlier_packs_default_for_the_same_key(
    tmp_path: Path,
) -> None:
    manager = ConfigurationManager(
        environment="local",
        platform_config_path=tmp_path / "platform.yaml",
        environments_dir=tmp_path / "environments",
    )
    first_pack = _pack_manifest(
        config_schema_properties={"log_level": {"type": "string", "default": "DEBUG"}}
    )
    second_pack = _pack_manifest(
        config_schema_properties={"log_level": {"type": "string", "default": "ERROR"}}
    )

    config = manager.load(role="api", pack_manifests=[first_pack, second_pack])

    assert config.log_level == "ERROR"


def test_a_pack_manifest_with_no_config_schema_contributes_nothing(tmp_path: Path) -> None:
    manager = ConfigurationManager(
        environment="local",
        platform_config_path=tmp_path / "platform.yaml",
        environments_dir=tmp_path / "environments",
    )
    pack_with_no_config_schema = {"metadata": {"id": "some-pack"}}

    config = manager.load(role="api", pack_manifests=[pack_with_no_config_schema])

    assert config.log_level == "INFO"  # the built-in default, layer 1, still applies


def test_a_runtime_override_wins_over_pack_default_platform_and_environment_config(
    tmp_path: Path,
) -> None:
    """The real proof this Task requires: layer 5 outranks every lower
    layer — pack defaults (2), platform config (3), and environment
    config (4) all set `log_level`, and the runtime override still
    wins."""
    _write_yaml(tmp_path / "platform.yaml", {"kernel": {"log_level": "WARNING"}})
    _write_yaml(tmp_path / "environments" / "local.yaml", {"kernel": {"log_level": "ERROR"}})
    manager = ConfigurationManager(
        environment="local",
        platform_config_path=tmp_path / "platform.yaml",
        environments_dir=tmp_path / "environments",
    )
    pack = _pack_manifest(
        config_schema_properties={"log_level": {"type": "string", "default": "DEBUG"}}
    )

    config = manager.load(
        role="api", pack_manifests=[pack], runtime_overrides={"log_level": "CRITICAL"}
    )

    assert config.log_level == "CRITICAL"


def test_no_runtime_overrides_behaves_exactly_as_before(tmp_path: Path) -> None:
    _write_yaml(tmp_path / "platform.yaml", {"kernel": {"log_level": "WARNING"}})
    manager = ConfigurationManager(
        environment="local",
        platform_config_path=tmp_path / "platform.yaml",
        environments_dir=tmp_path / "environments",
    )

    config = manager.load(role="api", runtime_overrides=None)

    assert config.log_level == "WARNING"


def test_env_and_role_cannot_be_overridden_by_a_runtime_override(tmp_path: Path) -> None:
    manager = ConfigurationManager(
        environment="local",
        platform_config_path=tmp_path / "platform.yaml",
        environments_dir=tmp_path / "environments",
    )

    config = manager.load(role="api", runtime_overrides={"env": "production", "role": "worker"})

    assert config.env == "local"
    assert config.role == "api"
