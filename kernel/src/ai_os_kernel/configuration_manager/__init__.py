"""Configuration Manager — the single source of runtime configuration.

Layered precedence: built-in defaults -> pack defaults -> platform
config -> environment config -> runtime overrides -> experiment
overrides -> secrets (docs/03_architecture/kernel/configuration_manager.md
§4). All 7 layers are implemented at this stage — layer 6 in two real,
deliberately separate halves (below), not one mechanism: boolean
feature flags (``P01-S02-M01-T07``) and arbitrary-value experiment
overrides (``P01-S02-M01-T05``). Investigated and kept separate, not
unified, when building the second half: :class:`ExperimentOverrideStore`
is structurally ``dict[str, dict[str, bool]]`` (booleans only, per
``run_id``) with exactly one real caller (``GET /config/flags``, which
always passes an empty, request-scoped store) — too narrow a type and
too shallow a real integration to justify reopening its own,
already-evidenced ticket just to widen it. ``pinned_conditions`` is
instead a plain, per-call ``Mapping[str, Any]`` parameter on
:meth:`ConfigurationManager.load`, achieving the identical §4 isolation
("never leak into concurrent workflows") structurally — nothing is
ever stored on ``self`` — without a live, run-keyed store at all.

**Layer 2, pack-level defaults** (added 2026-07-31, ``P01-S02-M01-T03``):
:func:`extract_pack_defaults` reads the ``default`` values declared in a
pack manifest's own ``configSchema``; :meth:`ConfigurationManager.load`'s
``pack_manifests`` argument merges them in ahead of the platform and
environment files, so either can still override a pack's suggestion.

**Layer 5, runtime overrides** (added 2026-07-31, ``P01-S02-M01-T04``):
:class:`RuntimeOverrideStore` is the live, in-memory state this layer
reads from; its ``apply`` audits the change (writing a real
``governance.config_changes`` row) before applying it.
:meth:`ConfigurationManager.load`'s ``runtime_overrides`` argument
merges a plain snapshot in above every file layer. See
:mod:`ai_os_kernel.configuration_manager.runtime_overrides`.

**Layer 7, secret resolution** (added 2026-07-31, ``P01-S02-M01-T06``):
:func:`resolve_secret_references` resolves every ``secret://``
reference surviving the layer 1-6 merge through an injected
``SecretProvider`` (the already-proven ``secrets_manager``), wrapping
each in a ``SecretValue`` (ADR-0024 rule 2 — never a raw string).
:meth:`ConfigurationManager.load_with_secrets_resolved` is the async
sibling to :meth:`ConfigurationManager.load` that wires it in — async
because resolving is real I/O, unlike every other layer here. See
:mod:`ai_os_kernel.configuration_manager.secrets`.

**Layer 6, half A — feature flags** (added 2026-07-31, ``P01-S02-M01-T07``):
unlike every file-driven layer, this one is never merged into the
shared, process-wide dict — §4 requires it "isolated to that run...
never leak into concurrent workflows." :class:`ExperimentOverrideStore`
keys boolean overrides by ``run_id``; :func:`resolve_feature_flag`
resolves one flag through, in order, a run's isolated override, a live
runtime override (layer 5, reused directly), the last pack manifest
declaring it, then a caller default — "experiment overrides (6) beat
runtime overrides (5)" (ADR-0022). See
:mod:`ai_os_kernel.configuration_manager.feature_flags`.

**Layer 6, half B — arbitrary-value experiment overrides** (added
2026-08-07, ``P01-S02-M01-T05``): "an experiment definition" ->
"overrides scoped to one run" for any config key, not only booleans —
a real, distinct need :class:`ExperimentOverrideStore`'s own boolean
type cannot hold. :meth:`ConfigurationManager.load`'s
``pinned_conditions`` argument merges a plain, per-call snapshot in
above ``runtime_overrides``, never stored on ``self`` — isolation is
structural (nothing to leak), not policy. A caller (the eventual
experiment-run composition) supplies whatever mapping it extracts from
its own experiment definition; this module never reaches into a pack's
model (no pack may import this Kernel package, and this package may
not import a pack — ``platform_sdk.md`` §9 item 7). See
:mod:`ai_os_kernel.configuration_manager.loader`'s own docstring for
why this is a second, deliberately separate mechanism rather than a
widened :class:`ExperimentOverrideStore`.

No component should read a configuration file directly — everything
goes through :class:`ConfigurationManager` and the resulting
:class:`PlatformConfig`.

**The config change-audit trail** (added 2026-07-31, ``P01-S02-M01-T08``)
writes ``governance.config_changes`` rows: :class:`SqlConfigChangeWriter`
records a digest of the old/new value (never the value itself, so a
secret reference change never leaks it — data_model.md §9.2), and
:func:`verify_config_change` recomputes a digest from a known real value
to confirm it matches what's stored. See
:mod:`ai_os_kernel.configuration_manager.audit`.

See docs/03_architecture/kernel/configuration_manager.md.
"""

from ai_os_kernel.configuration_manager.audit import (
    ConfigChangeRecord,
    ConfigChangeVerificationResult,
    ConfigChangeWriter,
    SqlConfigChangeWriter,
    compute_value_digest,
    verify_config_change,
)
from ai_os_kernel.configuration_manager.bootstrap_env import BootstrapEnv
from ai_os_kernel.configuration_manager.errors import ConfigChangeAuditError, ConfigurationError
from ai_os_kernel.configuration_manager.feature_flags import (
    ExperimentOverrideStore,
    extract_feature_flag_defaults,
    resolve_feature_flag,
)
from ai_os_kernel.configuration_manager.loader import ConfigurationManager, extract_pack_defaults
from ai_os_kernel.configuration_manager.models import PlatformConfig
from ai_os_kernel.configuration_manager.runtime_overrides import RuntimeOverrideStore
from ai_os_kernel.configuration_manager.secrets import resolve_secret_references

__all__ = [
    "BootstrapEnv",
    "ConfigChangeAuditError",
    "ConfigChangeRecord",
    "ConfigChangeVerificationResult",
    "ConfigChangeWriter",
    "ConfigurationError",
    "ConfigurationManager",
    "ExperimentOverrideStore",
    "PlatformConfig",
    "RuntimeOverrideStore",
    "SqlConfigChangeWriter",
    "compute_value_digest",
    "extract_feature_flag_defaults",
    "extract_pack_defaults",
    "resolve_feature_flag",
    "resolve_secret_references",
    "verify_config_change",
]
