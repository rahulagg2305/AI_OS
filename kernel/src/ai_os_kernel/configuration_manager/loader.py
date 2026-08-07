"""Loads and merges the layered platform configuration.

Implements the layer order in
docs/03_architecture/kernel/configuration_manager.md §4:
built-in defaults -> pack defaults -> platform config -> environment
config -> runtime overrides -> experiment overrides -> secrets.

Layers 1 (built-in defaults, via the ``PlatformConfig`` model), 2
(pack-level defaults, ``P01-S02-M01-T03``), 3 (platform config file), 4
(environment config file), 5 (runtime overrides, ``P01-S02-M01-T04``),
6 (experiment overrides, ``P01-S02-M01-T05``), and 7 (secret
resolution, ``P01-S02-M01-T06``) are all implemented at this stage.
Callers depend on ``PlatformConfig``, not on how it was assembled, so
none of layer 6's addition required changes at any existing call site.

**Layer 6, concretely** (§4: "Experiment overrides — Per-run, isolated
to that run"; ``P01-S02-M01-T05``): unlike layers 1-5, which resolve
one *process-wide* config, an experiment override applies only to the
one run belonging to that experiment — the Benchmarking Pack's own
``ExperimentDefinition``/``ExperimentSpec`` (``P04-S03-M34-T01``) never
reaches this module at all (no pack may import this Kernel package,
and this Kernel package may not import a pack — ``platform_sdk.md``
§9 item 7). ``pinned_conditions`` is therefore a plain
``Mapping[str, Any]`` parameter, the identical shape ``runtime_overrides``
already establishes — a caller (the eventual experiment-run composition)
is responsible for extracting whatever dict it needs from its own
experiment definition; this module never reaches into one. Passed
per-call, never stored on ``self``, so isolation is structural, not a
policy this module has to enforce: two concurrent ``load()`` calls with
different ``pinned_conditions`` can never observe each other's layer 6.
§4's own "experiment overrides (6) beat runtime overrides (5)"
ordering is enforced by merging it strictly after ``runtime_overrides``
in ``_merge_layers``.

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

**Layer 5, concretely** (§4: "Runtime overrides — ``PATCH
/api/v1/config``, audited"): unlike layers 2-4, §4 requires this layer
to be *audited*, so it is not a plain data merge like the others.
:class:`~ai_os_kernel.configuration_manager.runtime_overrides.
RuntimeOverrideStore` is the live, in-memory state layer 5 reads from;
its ``apply`` records a real ``governance.config_changes`` row via the
already-proven :class:`~ai_os_kernel.configuration_manager.audit.
ConfigChangeWriter` (``P01-S02-M01-T08``) *before* the override takes
effect. :meth:`ConfigurationManager.load` itself stays synchronous —
it only merges a plain snapshot (``runtime_overrides``), never talks to
the writer or the store directly, exactly as layers 2-4 merge
already-resolved input rather than discovering it themselves. Building
the ``PATCH /api/v1/config`` route itself is separate, later work (§6:
"Order is therefore: writer, then route" — the writer now exists; this
layer is what the route would call into).

**Layer 7, concretely** (§4: "Secret values — Resolved at point of use
from ``secret://`` references"; ``P01-S02-M01-T06``): resolving a
secret is real I/O (:class:`~ai_os_kernel.secrets_manager.provider.
SecretProvider` is ``async``), so it cannot be one more step inside the
synchronous :meth:`load` without breaking every existing caller — the
documented "one call site in ``ConfigurationManager.load()``" is
therefore a sibling async method, :meth:`load_with_secrets_resolved`,
reusing the exact same layer 1-6 merge via the shared
``_merge_layers`` helper. It returns a plain ``dict``, not a
``PlatformConfig`` — see :mod:`ai_os_kernel.configuration_manager.secrets`
for why a resolved, ``SecretValue``-wrapped value cannot validate into
today's model, and is not supposed to.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from ai_os_kernel.configuration_manager.errors import ConfigurationError
from ai_os_kernel.configuration_manager.models import PlatformConfig
from ai_os_kernel.configuration_manager.secrets import resolve_secret_references
from ai_os_kernel.secrets_manager.provider import SecretProvider

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
        self,
        *,
        role: str,
        pack_manifests: Sequence[Mapping[str, Any]] = (),
        runtime_overrides: Mapping[str, Any] | None = None,
        pinned_conditions: Mapping[str, Any] | None = None,
    ) -> PlatformConfig:
        """Merge layers 1-6 and return a validated, immutable ``PlatformConfig``.

        ``pack_manifests`` is every activated pack's raw manifest mapping
        (layer 2), in activation order — a pack listed later overrides an
        earlier pack's default for the same key, the same "later entry
        wins" rule every other layer already follows. Empty by default,
        so an existing caller that passes none behaves exactly as before.

        ``runtime_overrides`` is a plain snapshot of layer 5's current
        state (see :class:`~ai_os_kernel.configuration_manager.
        runtime_overrides.RuntimeOverrideStore`) — this method never
        applies or audits an override itself, only merges an
        already-applied one in above every file layer.

        ``pinned_conditions`` is layer 6 (§4: "Experiment overrides —
        Per-run, isolated to that run") — a plain snapshot of one
        experiment's own conditions to hold constant, merged in above
        ``runtime_overrides``. ``None``-default: an existing caller that
        passes none behaves exactly as before. See this module's own
        docstring for why this is a plain mapping, not a pack model.
        """
        merged = self._merge_layers(
            role=role,
            pack_manifests=pack_manifests,
            runtime_overrides=runtime_overrides,
            pinned_conditions=pinned_conditions,
        )
        try:
            return PlatformConfig.model_validate(merged)
        except ValidationError as exc:
            raise ConfigurationError(
                f"Invalid configuration after merging layers 1-6 for "
                f"{self._platform_config_path}: {exc}"
            ) from exc

    async def load_with_secrets_resolved(
        self,
        *,
        role: str,
        secret_provider: SecretProvider,
        pack_manifests: Sequence[Mapping[str, Any]] = (),
        runtime_overrides: Mapping[str, Any] | None = None,
        pinned_conditions: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Merges layers 1-6 exactly as :meth:`load` does, then resolves
        layer 7: every ``secret://`` reference surviving that merge —
        the one real value precedence already decided, never a
        lower-layer value a higher layer overrode — is resolved through
        ``secret_provider`` into a
        :class:`~ai_os_kernel.secrets_manager.value.SecretValue`.

        Returns the merged, secret-resolved ``dict`` rather than a
        ``PlatformConfig`` — see :mod:`ai_os_kernel.configuration_manager.
        secrets` for why.
        """
        merged = self._merge_layers(
            role=role,
            pack_manifests=pack_manifests,
            runtime_overrides=runtime_overrides,
            pinned_conditions=pinned_conditions,
        )
        return await resolve_secret_references(merged, secret_provider)

    def _merge_layers(
        self,
        *,
        role: str,
        pack_manifests: Sequence[Mapping[str, Any]],
        runtime_overrides: Mapping[str, Any] | None,
        pinned_conditions: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Layers 1-6, deep-merged in precedence order — the one merge
        both :meth:`load` and :meth:`load_with_secrets_resolved` share,
        so the two can never silently drift apart on ordering."""
        merged: dict[str, Any] = {}
        for manifest in pack_manifests:
            merged = _deep_merge(merged, extract_pack_defaults(manifest))
        merged = _deep_merge(merged, self._read_section(self._platform_config_path))
        env_file = self._environments_dir / f"{self._environment}.yaml"
        merged = _deep_merge(merged, self._read_section(env_file))
        merged = _deep_merge(merged, dict(runtime_overrides or {}))
        # Layer 6, §4: "experiment overrides (6) beat runtime overrides
        # (5)" — merged strictly after, never before.
        merged = _deep_merge(merged, dict(pinned_conditions or {}))

        # env/role are bootstrap identity, never file-driven — always the
        # caller-supplied values, overwriting anything a file might set.
        merged["env"] = self._environment
        merged["role"] = role
        return merged

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
