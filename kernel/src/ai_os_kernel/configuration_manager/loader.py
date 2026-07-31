"""Loads and merges the layered platform configuration.

Implements the layer order in
docs/03_architecture/kernel/configuration_manager.md §4:
built-in defaults -> pack defaults -> platform config -> environment
config -> runtime overrides -> experiment overrides -> secrets.

Layers 1 (built-in defaults, via the ``PlatformConfig`` model), 2
(pack-level defaults, ``P01-S02-M01-T03``), 3 (platform config file) and
4 (environment config file) are implemented at this stage. Runtime
overrides, experiment overrides, and secret resolution are added when
the components that produce them exist (the configuration API, the
Experiment Manager, Secrets Management) — callers depend on
``PlatformConfig``, not on how it was assembled, so none of that will
require changes here at the call site.

**Layer 2, concretely** (§4: "Pack-level defaults — Capability Pack
manifests and their ``configSchema`` defaults"): each activated pack's
manifest may declare a JSON Schema ``configSchema`` whose properties
carry a ``default`` (the same ``default`` keyword
``platform_sdk/schemas/manifest.schema.json`` already supports per
JSON Schema semantics). :func:`extract_pack_defaults` pulls those
values out; :meth:`ConfigurationManager.load` merges them in *before*
the platform/environment files, so either can still override a pack's
suggested default — exactly "layer 3 and 4 outrank layer 2." Discovering
*which* packs are activated (Manifest Loader) is a separate, later
integration; this layer takes already-discovered manifests as plain
input, matching how layers 3/4 take already-resolved file paths rather
than discovering them.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from ai_os_kernel.configuration_manager.errors import ConfigurationError
from ai_os_kernel.configuration_manager.models import PlatformConfig

# The set of valid environments is a structural constant of the platform
# (docs/11_deployment/deployment_architecture.md §4), not itself
# environment configuration — it cannot be configuration-driven without
# being circular ("which environments are valid" would need to know
# which environment it is in).
_VALID_ENVIRONMENTS = frozenset({"local", "dev", "staging", "production"})

_CONFIG_SECTION = "kernel"


class ConfigurationManager:
    """Resolves one process's :class:`PlatformConfig`.

    ``environment`` is required at construction time because it decides
    *which* environment file to read. ``role`` is only needed at
    :meth:`load` time because it does not affect which files are read —
    only the final resolved value.
    """

    def __init__(
        self,
        *,
        environment: str,
        platform_config_path: Path,
        environments_dir: Path,
    ) -> None:
        if environment not in _VALID_ENVIRONMENTS:
            raise ConfigurationError(
                f"Unknown environment '{environment}'. Expected one of: "
                f"{', '.join(sorted(_VALID_ENVIRONMENTS))}."
            )
        self._environment = environment
        self._platform_config_path = platform_config_path
        self._environments_dir = environments_dir

    def load(
        self, *, role: str, pack_manifests: Sequence[Mapping[str, Any]] = ()
    ) -> PlatformConfig:
        """Merge all layers and return a validated, immutable ``PlatformConfig``.

        ``pack_manifests`` is every activated pack's raw manifest mapping
        (layer 2), in activation order — a pack listed later overrides an
        earlier pack's default for the same key, the same "later entry
        wins" rule every other layer already follows. Empty by default,
        so an existing caller that passes none behaves exactly as before.
        """
        merged: dict[str, Any] = {}
        for manifest in pack_manifests:
            merged = _deep_merge(merged, extract_pack_defaults(manifest))
        merged = _deep_merge(merged, self._read_section(self._platform_config_path))
        env_file = self._environments_dir / f"{self._environment}.yaml"
        merged = _deep_merge(merged, self._read_section(env_file))

        # env/role are bootstrap identity, never file-driven — always the
        # caller-supplied values, overwriting anything a file might set.
        merged["env"] = self._environment
        merged["role"] = role

        try:
            return PlatformConfig.model_validate(merged)
        except ValidationError as exc:
            raise ConfigurationError(
                f"Invalid configuration after merging {self._platform_config_path} "
                f"and {env_file}: {exc}"
            ) from exc

    def _read_section(self, path: Path) -> dict[str, Any]:
        """Read the ``kernel:`` mapping from a YAML file.

        A missing file is not an error — it simply contributes nothing
        to the merge, and the layers beneath it (or the built-in
        defaults) apply.
        """
        if not path.exists():
            return {}

        try:
            with path.open("r", encoding="utf-8") as fh:
                document = yaml.safe_load(fh)
        except yaml.YAMLError as exc:
            raise ConfigurationError(f"{path}: not valid YAML: {exc}") from exc

        if document is None:
            return {}
        if not isinstance(document, dict):
            raise ConfigurationError(f"{path}: must contain a YAML mapping at the top level.")

        section = document.get(_CONFIG_SECTION, {})
        if not isinstance(section, dict):
            raise ConfigurationError(f"{path}: '{_CONFIG_SECTION}' must be a mapping.")
        return section


def extract_pack_defaults(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Pulls the declared ``default`` out of every property in a pack
    manifest's own ``configSchema`` (§4 layer 2). A manifest with no
    ``configSchema``, or a property with no ``default``, contributes
    nothing — a pack is never required to declare either."""
    config_schema = manifest.get("configSchema")
    if not isinstance(config_schema, dict):
        return {}
    properties = config_schema.get("properties")
    if not isinstance(properties, dict):
        return {}
    return {
        key: spec["default"]
        for key, spec in properties.items()
        if isinstance(spec, dict) and "default" in spec
    }


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge ``override`` onto ``base``. Nested mappings merge recursively;
    every other value type (including lists) is replaced wholesale —
    "higher layers override lower layers" means replace, not append.
    """
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
